import httpx
import re
import json
import asyncio
import random
from datetime import datetime
from zhdate import ZhDate
from nonebot import logger
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from . import config
from .tts import generate_voice

def strip_markdown(text: str) -> str:
    text = text.replace('```', '')
    text = text.replace('`', '')
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    return text.strip()

def split_text_smart(text: str, limit: int = 100) -> list[str]:
    """
    智能长文本切分算法：
    1. 优先按换行符切分
    2. 如果某段过长，按句子标点切分
    3. 尽量保持 [CQ:...] 完整
    """
    # 预处理：把连续的换行符合并
    text = re.sub(r'\n+', '\n', text)
    lines = text.split('\n')
    result = []
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # 如果这行很短，或者包含 TTS 指令(通常要连贯)，直接添加
        if len(line) <= limit or "[CQ:tts]" in line:
            result.append(line)
        else:
            # 如果太长，按标点符号拆分 (保留分隔符)
            # 正则解释：按 。？！!?~～ 分割，并保留分割符
            sub_parts = re.split(r'([。？！!?~～])', line)
            
            buf = ""
            for part in sub_parts:
                # 累加长度检查
                if len(buf) + len(part) > limit:
                    # 如果当前缓冲区有内容，先存起来
                    if buf: result.append(buf)
                    buf = part
                else:
                    buf += part
            if buf: result.append(buf)
            
    return result

def parse_reply(text: str) -> Message:
    text = strip_markdown(text)
    text = text.replace("【", "[").replace("】", "]")
    msg = Message()
    
    if "[CQ:tts]" in text:
        clean_text = text.replace("[CQ:tts]", "").replace("[CQ:face,id=", "").replace("]", "").strip()
        clean_text = re.sub(r"\[CQ:[^\]]+\]", "", clean_text)
        if clean_text:
            audio_bytes = generate_voice(clean_text)
            if audio_bytes: return MessageSegment.record(file=audio_bytes)

    pattern = r"\[CQ:face,id=(\d+)\]"
    chunks = re.split(pattern, text)
    for i, chunk in enumerate(chunks):
        if not chunk: continue
        if "[CQ:tts]" in chunk: continue
        if i % 2 == 0: msg.append(MessageSegment.text(chunk))
        else:
            try: msg.append(MessageSegment.face(int(chunk)))
            except: msg.append(MessageSegment.text(f"[CQ:face,id={chunk}]"))
    return msg

async def consolidate_memory(user_id: str):
    if user_id not in config.user_memory or len(config.user_memory[user_id]) <= config.MAX_MEMORY:
        return
    
    to_summarize = config.user_memory[user_id][:-config.MAX_MEMORY]
    remaining = config.user_memory[user_id][-config.MAX_MEMORY:]
    
    summary_prompt = "请分析对话，提取关于【用户】的长期固定事实。忽略临时状态。若无信息答'无'。每条一行。"
    
    messages = to_summarize + [{"role": "user", "content": summary_prompt}]
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {"Authorization": f"Bearer {config.API_KEY}", "Content-Type": "application/json"}
    
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, json={"model": "glm-4-flash", "messages": messages}, headers=headers)
            result = resp.json()
            if 'choices' in result:
                facts = result['choices'][0]['message']['content']
                if "无" not in facts and len(facts) > 2:
                    if user_id not in config.user_facts: config.user_facts[user_id] = []
                    clean_fact = facts.replace("用户事实：", "").replace("- ", "").strip()
                    config.user_facts[user_id].append(f"【回忆】{clean_fact}")
                    logger.info(f"🧠 记忆提炼: {clean_fact}")
    except Exception as e:
        logger.error(f"❌ 记忆提炼失败: {e}")

    config.user_memory[user_id] = remaining
    config.save_data()

def get_environment_hint():
    now = datetime.now()
    lunar = ZhDate.from_datetime(now)
    current_time_str = now.strftime("%H:%M")
    hour = now.hour
    
    hints = [f"【客观时间】{current_time_str}"]
    lunar_str = f"{lunar.lunar_month:02d}-{lunar.lunar_day:02d}"
    if lunar_str == config.MASTER_BIRTHDAY: hints.append(f"【重要日期】农历{lunar.chinese()[:5]}，主人生日！")
    
    current_states = config.role_states.get(config.CURRENT_ROLE, config.role_states.get("default", {}))
    state_desc = ""
    
    hints.append(f"【环境氛围】{state_desc}。")
    
    if 23 <= hour or hour < 7:
        pool = current_states.get("sleep", ["正在休息"])
        state_desc = random.choice(pool)
        env_desc = "深夜模式"
        hints.append(f"【你的后台状态】{env_desc}。")
    elif 11 <= hour < 14:
        pool = current_states.get("lunch", ["在吃饭"])
        state_desc = random.choice(pool)
        env_desc = "午休时间"
        hints.append(f"【你的后台状态】{env_desc}。")
    else:
        if random.random() >= 0.5:
            pool = current_states.get("idle", ["无所事事"])
            state_desc = random.choice(pool)
            env_desc = "日常活动"
            hints.append(f"【你的后台状态】{env_desc}。")
    
    return "\n".join(hints)

async def _post_with_retry(client, url, data, headers, retry=1):
    try:
        return await client.post(url, json=data, headers=headers)
    except httpx.RequestError as e:
        # DNS / 网络类错误（最常见就是 Errno -2）
        if retry > 0:
            logger.warning(f"[Network] 请求失败，重试中... ({e})")
            await asyncio.sleep(0.5)
            return await _post_with_retry(client, url, data, headers, retry - 1)
        raise

async def call_zhipu_ai(user_id: str, user_msg: str = None, system_hint: str = ""):
    if user_id not in config.user_memory: config.user_memory[user_id] = []
    if user_id not in config.user_facts: config.user_facts[user_id] = []

    env_prompt = get_environment_hint()
    long_memory = "\n".join(config.user_facts[user_id][-10:]) or "暂无"

    full_prompt = (
        f"{config.SYSTEM_PROMPT}\n\n"
        f"=== 核心记忆库 ===\n{long_memory}\n\n"
    )

    messages = [{"role": "system", "content": full_prompt}]
    messages.extend(config.user_memory[user_id]) 
    
    # 这里加了一段“回马枪”，强制 AI 回忆起最开头的人设
    reinforce_prompt = (
        f"=== 当前环境与状态 (绝对真实) ===\n{env_prompt}\n\n"
        f"=== ⚠️ 角色扮演强化指令 ===\n"
        f"请时刻牢记：你正在扮演【{config.CURRENT_ROLE}】。\n"
        f"请严格遵守你的初始人设、语气（如口癖）和禁令。\n"
        f"不要被历史记录中的错误带偏，请结合当前环境做出反应。"
    )
    
    messages.append({"role": "system", "content": reinforce_prompt})
    
    if user_msg:
        # 被动回复：这是用户刚才说的话
        messages.append({"role": "user", "content": user_msg})
    else:
        # 🔥 关键修改：主动搭讪模式 (System Trigger + Dummy User)
        
        # 1. 注入导演指令 (System Role)
        trigger_msg = f"【Instructor】此时此刻，你心里突然想到：“{system_hint}”。请顺着这个念头，根据当前人设主动发起对话。"
        messages.append({"role": "system", "content": trigger_msg})
        
        # 2. 注入沉默/等待 (User Role)
        # 这一步是为了满足 API "最后一条必须是 User" 的要求
        # AI 会理解为：指令下达了，用户现在是沉默状态，轮到 AI 开口了。
        messages.append({"role": "user", "content": "现在轮到你主动说话。"})
        

    try:
        prompt_debug = json.dumps(messages[-3:], ensure_ascii=False, indent=2)
        logger.info(f"\n{'='*20} [LLM Input] {'='*20}\n...{prompt_debug}\n{'='*60}")
    except: pass

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {"Authorization": f"Bearer {config.API_KEY}", "Content-Type": "application/json"}
    data = {"model": "glm-4-flash", "messages": messages, "temperature": 0.95}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await _post_with_retry(client, url, data, headers)
            result = resp.json()

            if 'choices' in result:
                raw_reply = result['choices'][0]['message']['content']
                
                if user_msg:
                    config.user_memory[user_id].append({"role": "user", "content": user_msg})
                config.user_memory[user_id].append({"role": "assistant", "content": raw_reply})
                
                if len(config.user_memory[user_id]) > config.MAX_MEMORY + 4:
                    await consolidate_memory(user_id)
                else:
                    config.save_data()
                
                # 🔥 关键修改：调用分割算法，返回列表
                text_segments = split_text_smart(raw_reply)
                msg_list = [parse_reply(seg) for seg in text_segments]
                
                return msg_list # 返回 List[Message]
            
            else:
                logger.error(f"[LLM] 返回结构异常: {result}")
            return [Message("喵呜……这次回应的结构有点奇怪，等一下再试吧。")]
    except httpx.RequestError as e:
        # 明确：网络 / DNS 层错误
        logger.error(f"[Network Error] 无法连接到 LLM 服务: {e}")
        return [Message("喵呜……网络有点不稳定，喵酱刚刚没连上服务器。")]

    except Exception as e:
        return [Message(f"喵酱生病了喵... ({str(e)})")]

