import httpx
import time
import re
from nonebot import logger
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from .config import SYSTEM_PROMPT, API_KEY, user_memory, user_facts, MAX_MEMORY, save_data

def parse_reply(text: str) -> Message:
    """解析 CQ 码表情"""
    msg = Message()
    pattern = r"\[CQ:face,id=(\d+)\]"
    chunks = re.split(pattern, text)
    for i, chunk in enumerate(chunks):
        if not chunk: continue
        if i % 2 == 0:
            msg.append(MessageSegment.text(chunk))
        else:
            try:
                msg.append(MessageSegment.face(int(chunk)))
            except ValueError:
                msg.append(MessageSegment.text(f"[CQ:face,id={chunk}]"))
    return msg

async def consolidate_memory(user_id: str):
    """
    🧠 记忆固化：将过期的短期对话提炼成长期事实
    """
    if user_id not in user_memory or len(user_memory[user_id]) <= MAX_MEMORY:
        return

    # 1. 切片：取出最早的对话作为“待提炼内容” (保留最近的 MAX_MEMORY 条在短期记忆)
    # 我们提炼那些即将被遗忘的记忆
    to_summarize = user_memory[user_id][:-MAX_MEMORY]
    # 剩下的保留在短期记忆
    remaining = user_memory[user_id][-MAX_MEMORY:]
    
    # 2. 构造提炼请求
    summary_prompt = "请阅读以上对话，提取关于用户的关键事实（如称呼、喜好、居住地、人际关系等）。如果没有关键信息，请回答'无'。不要包含聊天客套话，只输出事实，每条事实一行。"
    
    messages = to_summarize + [{"role": "user", "content": summary_prompt}]
    
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, json={"model": "glm-4-flash", "messages": messages}, headers=headers)
            result = resp.json()
            
            if 'choices' in result:
                facts = result['choices'][0]['message']['content']
                if "无" not in facts:
                    # 3. 将新提取的事实追加到长期记忆列表
                    if user_id not in user_facts:
                        user_facts[user_id] = []
                    # 简单的去重添加
                    user_facts[user_id].append(f"【回忆】{facts}")
                    logger.info(f"🧠 [记忆提炼] 用户 {user_id} 新增记忆: {facts}")
    except Exception as e:
        logger.error(f"❌ 记忆提炼失败: {e}")

    # 4. 更新内存并保存
    user_memory[user_id] = remaining
    save_data()

async def call_zhipu_ai(user_id: str, user_msg: str = None, system_hint: str = ""):
    """调用 AI，包含长短期记忆融合"""
    
    # 1. 初始化
    if user_id not in user_memory: user_memory[user_id] = []
    if user_id not in user_facts: user_facts[user_id] = []

    # 2. 注入时间与长期记忆
    current_time = time.strftime("%Y-%m-%d %H:%M", time.localtime())
    
    # 将长期记忆拼接成文本
    long_term_memory_str = "\n".join(user_facts[user_id][-10:]) # 只取最近10条长期记忆，防止太长
    if not long_term_memory_str:
        long_term_memory_str = "暂无"

    # 构建更强的 System Prompt
    full_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"⏰ 当前时间：{current_time}\n"
        f"📚 关于主人的长期记忆（必须参考）：\n{long_term_memory_str}\n\n"
        f"{system_hint}"
    )

    # 3. 构建消息列表 (System + Short Term Memory + User Input)
    messages = [{"role": "system", "content": full_prompt}]
    messages.extend(user_memory[user_id]) 
    
    if user_msg:
        messages.append({"role": "user", "content": user_msg})
    else:
        messages.append({"role": "user", "content": system_hint})

    # 4. 请求 API
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json={"model": "glm-4-flash", "messages": messages, "temperature": 0.95}, headers=headers)
            result = resp.json()

            if 'choices' in result:
                raw_reply = result['choices'][0]['message']['content']
                
                # 5. 更新短期记忆
                if user_msg:
                    user_memory[user_id].append({"role": "user", "content": user_msg})
                user_memory[user_id].append({"role": "assistant", "content": raw_reply})
                
                # 6. 触发记忆整理 (如果太长了，就提炼事实并截断)
                if len(user_memory[user_id]) > MAX_MEMORY + 4: # 给一点缓冲空间
                    await consolidate_memory(user_id)
                else:
                    save_data() # 没触发提炼也要保存
                
                return parse_reply(raw_reply)
            else:
                return Message(f"喵呜...脑子卡住了喵: {result}")
    except Exception as e:
        return Message(f"喵酱生病了喵... ({str(e)})")