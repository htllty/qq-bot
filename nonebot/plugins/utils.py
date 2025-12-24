import httpx
import time
import re
from datetime import datetime
from zhdate import ZhDate
from nonebot import logger
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from .config import API_KEY, user_memory, user_facts, MAX_MEMORY, save_data, MASTER_BIRTHDAY
from . import config
from .tts import generate_voice

def parse_reply(text: str) -> Message:
    # 🛠️ 关键修复：兼容 AI 抽风输出的中文全角符号
    # 把 【CQ:face...】 强行变成 [CQ:face...]
    text = text.replace("【", "[").replace("】", "]")

    msg = Message()
    
    # 1. 检查语音标签 [CQ:tts]
    if "[CQ:tts]" in text:
        # 清理标签，准备生成语音
        clean_text = text.replace("[CQ:tts]", "").replace("[CQ:face,id=", "").replace("]", "").strip()
        # 使用正则彻底清除所有 CQ 码内容 (包括表情ID)
        clean_text = re.sub(r"\[CQ:[^\]]+\]", "", clean_text)
        
        logger.info(f"🎤 触发语音回复: {clean_text[:10]}...")
        if clean_text:
            audio_bytes = generate_voice(clean_text)
            if audio_bytes:
                return MessageSegment.record(file=audio_bytes)
            else:
                msg.append(MessageSegment.text("（语音生成失败喵...）"))

    # 2. 解析 QQ 表情
    # 正则匹配 [CQ:face,id=数字]
    pattern = r"\[CQ:face,id=(\d+)\]"
    chunks = re.split(pattern, text)
    
    for i, chunk in enumerate(chunks):
        if not chunk: continue
        
        # 过滤掉 [CQ:tts] 标签文本，不让它显示出来
        if "[CQ:tts]" in chunk: continue
        
        # re.split 切分后，偶数位是文本，奇数位是捕获组(ID)
        if i % 2 == 0:
            msg.append(MessageSegment.text(chunk))
        else:
            try:
                # 奇数位是 ID，转为表情对象
                msg.append(MessageSegment.face(int(chunk)))
            except ValueError:
                # 万一解析失败，还原为文本
                msg.append(MessageSegment.text(f"[CQ:face,id={chunk}]"))
                
    return msg

async def consolidate_memory(user_id: str):
    """
    🧠 记忆固化：将过期的短期对话提炼成长期事实
    """
    if user_id not in config.user_memory or len(config.user_memory[user_id]) <= config.MAX_MEMORY:
        return
    
    # 提取最早的记忆进行总结
    to_summarize = config.user_memory[user_id][:-config.MAX_MEMORY]
    remaining = config.user_memory[user_id][-config.MAX_MEMORY:]
    
    # 📝 优化后的提炼指令：增加负面约束，防止记录废话和破绽
    summary_prompt = """
    请分析以上对话，提取关于【用户】的关键事实信息。
    
    ✅ 需要提取的内容：
    - 用户的称呼、自称、别名。
    - 用户的喜好、厌恶、兴趣爱好。
    - 用户的个人信息（生日、居住地、职业、作息习惯等）。
    - 用户提到过的具体经历或计划。

    ❌ 严禁提取的内容：
    - 不要记录关于“喵酱”、“AI”、“虚拟助手”的任何描述。
    - 不要记录“用户正在聊天”、“用户与助手互动”这类交互行为。
    - 不要记录临时的客套话（如“你好”、“早安”）。

    输出要求：
    - 只输出事实短句，每条一行。
    - 如果没有新的关键信息，请直接回答“无”。
    """
    
    # 构造请求消息：把要总结的对话 + 总结指令 发给 AI
    # 注意：这里 role='user' 是为了模拟用户发出总结命令
    messages = to_summarize + [{"role": "user", "content": summary_prompt}]
    
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {"Authorization": f"Bearer {config.API_KEY}", "Content-Type": "application/json"}
    
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, json={"model": "glm-4-flash", "messages": messages}, headers=headers)
            result = resp.json()
            if 'choices' in result:
                facts = result['choices'][0]['message']['content']
                if "无" not in facts and "没有" not in facts:
                    if user_id not in config.user_facts: config.user_facts[user_id] = []
                    
                    # 简单的格式清洗，防止 AI 啰嗦
                    clean_facts = facts.replace("用户事实：", "").replace("提取事实：", "").strip()
                    config.user_facts[user_id].append(f"【回忆】{clean_facts}")
                    logger.info(f"🧠 [记忆提炼] 新增: {clean_facts}")
    except Exception as e:
        logger.error(f"❌ 记忆提炼失败: {e}")

    # 更新内存并保存
    user_memory[user_id] = remaining
    save_data()

def get_environment_hint():
    now = datetime.now()
    lunar = ZhDate.from_datetime(now)
    lunar_str = f"{lunar.lunar_month:02d}-{lunar.lunar_day:02d}"
    current_time_str = now.strftime("%H:%M")
    hour = now.hour
    
    hints = [f"客观时间：{current_time_str}"]
    
    if lunar_str == MASTER_BIRTHDAY:
        hints.append(f"【重要日期】今天是农历{lunar.chinese()[:5]}，也是主人的生日。")
    
    if 23 <= hour or hour < 5:
        hints.append("【环境氛围】夜深人静，适合休息。")
    elif 5 <= hour < 9:
        hints.append("【环境氛围】清晨，新的一天。")
    
    return "\n".join(hints)

async def call_zhipu_ai(user_id: str, user_msg: str = None, system_hint: str = ""):
    if user_id not in user_memory: user_memory[user_id] = []
    if user_id not in user_facts: user_facts[user_id] = []

    env_prompt = get_environment_hint()
    long_term_memory_str = "\n".join(user_facts[user_id][-10:]) or "暂无"

    full_prompt = (
        f"{config.SYSTEM_PROMPT}\n\n"
        f"--- 当前知觉 ---\n{env_prompt}\n\n"
        f"--- 深层记忆 ---\n{long_term_memory_str}\n"
    )

    if user_msg and system_hint:
        full_prompt += f"\n--- 潜意识直觉 ---\n{system_hint}"

    messages = [{"role": "system", "content": full_prompt}]
    messages.extend(user_memory[user_id]) 
    
    if user_msg:
        messages.append({"role": "user", "content": user_msg})
    else:
        messages.append({"role": "user", "content": f"（心里突然想到：{system_hint}）"})

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    data = {"model": "glm-4-flash", "messages": messages, "temperature": 0.95}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=data, headers=headers)
            result = resp.json()

            if 'choices' in result:
                raw_reply = result['choices'][0]['message']['content']
                
                if user_msg:
                    user_memory[user_id].append({"role": "user", "content": user_msg})
                    
                user_memory[user_id].append({"role": "assistant", "content": raw_reply})
                
                if len(user_memory[user_id]) > MAX_MEMORY + 4:
                    await consolidate_memory(user_id)
                else:
                    save_data()
                
                return parse_reply(raw_reply)
            else:
                return Message(f"喵呜...脑子卡住了喵: {result}")
    except Exception as e:
        return Message(f"喵酱生病了喵... ({str(e)})")