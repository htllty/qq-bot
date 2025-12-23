import httpx
import time
import re
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from .config import SYSTEM_PROMPT, API_KEY, user_memory, MAX_MEMORY

def parse_reply(text: str) -> Message:
    """
    智能解析 AI 回复：
    1. 提取 [CQ:face,id=123] 并转为表情对象
    2. 其他部分保留为文本
    """
    msg = Message()
    # 正则匹配 [CQ:face,id=数字]
    pattern = r"\[CQ:face,id=(\d+)\]"
    
    # 分割字符串：text 会被分成 [文本, ID, 文本, ID, ...]
    chunks = re.split(pattern, text)
    
    for i, chunk in enumerate(chunks):
        if not chunk: continue # 跳过空字符
        
        # re.split 的特性：偶数索引是文本，奇数索引是捕获组(即表情ID)
        if i % 2 == 0:
            msg.append(MessageSegment.text(chunk))
        else:
            # 这是一个表情ID
            try:
                face_id = int(chunk)
                msg.append(MessageSegment.face(face_id))
            except ValueError:
                # 万一 AI 输出了非数字 ID，当文本处理
                msg.append(MessageSegment.text(f"[CQ:face,id={chunk}]"))
                
    return msg

async def call_zhipu_ai(user_id: str, user_msg: str = None, system_hint: str = ""):
    if user_id not in user_memory:
        user_memory[user_id] = []

    current_time = time.strftime("%Y-%m-%d %H:%M", time.localtime())
    full_prompt = f"{SYSTEM_PROMPT}\n\n(当前时间：{current_time})\n{system_hint}"

    messages = [{"role": "system", "content": full_prompt}]
    messages.extend(user_memory[user_id]) 
    
    if user_msg:
        messages.append({"role": "user", "content": user_msg})
    else:
        messages.append({"role": "user", "content": system_hint})

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "glm-4-flash",
        "messages": messages,
        "temperature": 0.95
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=data, headers=headers)
            result = resp.json()

            if 'choices' in result:
                raw_reply = result['choices'][0]['message']['content']
                
                # 更新记忆 (存纯文本，方便 AI 理解上下文)
                if user_msg:
                    user_memory[user_id].append({"role": "user", "content": user_msg})
                user_memory[user_id].append({"role": "assistant", "content": raw_reply})
                
                if len(user_memory[user_id]) > MAX_MEMORY * 2:
                    user_memory[user_id] = user_memory[user_id][-MAX_MEMORY * 2:]
                
                # ⚠️ 关键修改：使用自定义解析器处理 CQ 码
                return parse_reply(raw_reply)
            else:
                return Message(f"喵呜...脑子卡住了喵: {result}")
    except Exception as e:
        return Message(f"喵酱生病了喵... ({str(e)})")