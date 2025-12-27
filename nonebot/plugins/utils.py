import httpx
import time
import re
import json
import random
from datetime import datetime
from zhdate import ZhDate
from nonebot import logger
from nonebot.adapters.onebot.v11 import Message, MessageSegment
# 导入 config 模块以便访问最新变量
from . import config
from .tts import generate_voice

def strip_markdown(text: str) -> str:
    """去除 Markdown 格式"""
    # 去除代码块框，保留内容
    text = text.replace('```', '')
    text = text.replace('`', '')
    # 去除加粗
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    # 去除标题 #
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    return text.strip()

def parse_reply(text: str) -> Message:
    # 0. 清洗 Markdown 和全角符号
    text = strip_markdown(text)
    text = text.replace("【", "[").replace("】", "]")
    
    msg = Message()
    
    # 1. 语音处理
    if "[CQ:tts]" in text:
        clean_text = text.replace("[CQ:tts]", "").replace("[CQ:face,id=", "").replace("]", "").strip()
        clean_text = re.sub(r"\[CQ:[^\]]+\]", "", clean_text)
        
        logger.info(f"🎤 触发语音: {clean_text[:10]}...")
        if clean_text:
            audio_bytes = generate_voice(clean_text)
            if audio_bytes:
                return MessageSegment.record(file=audio_bytes)
            else:
                msg.append(MessageSegment.text("（语音生成失败喵...）"))

    # 2. 表情处理
    pattern = r"\[CQ:face,id=(\d+)\]"
    chunks = re.split(pattern, text)
    for i, chunk in enumerate(chunks):
        if not chunk: continue
        if "[CQ:tts]" in chunk: continue
        
        if i % 2 == 0:
            msg.append(MessageSegment.text(chunk))
        else:
            try:
                msg.append(MessageSegment.face(int(chunk)))
            except:
                msg.append(MessageSegment.text(f"[CQ:face,id={chunk}]"))
    return msg

async def consolidate_memory(user_id: str):
    if user_id not in config.user_memory or len(config.user_memory[user_id]) <= config.MAX_MEMORY:
        return
    
    to_summarize = config.user_memory[user_id][:-config.MAX_MEMORY]
    remaining = config.user_memory[user_id][-config.MAX_MEMORY:]
    
    summary_prompt = "请分析对话，提取关于【用户】的长期固定事实（喜好、习惯、身份）。忽略临时状态（饿了、困了）和闲聊。若无信息答'无'。每条一行。"
    
    messages = to_summarize + [{"role": "user", "content": summary_prompt}]
    url = "[https://open.bigmodel.cn/api/paas/v4/chat/completions](https://open.bigmodel.cn/api/paas/v4/chat/completions)"
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
    """生成环境感知 (包含角色专属生活状态)"""
    now = datetime.now()
    lunar = ZhDate.from_datetime(now)
    current_time_str = now.strftime("%H:%M")
    hour = now.hour
    
    # 1. 客观时间
    hints = [f"【客观时间】{current_time_str}"]
    
    # 2. 农历/节日
    lunar_str = f"{lunar.lunar_month:02d}-{lunar.lunar_day:02d}"
    if lunar_str == config.MASTER_BIRTHDAY:
        hints.append(f"【重要日期】今天是农历{lunar.chinese()[:5]}，也是主人的生日。")
    
    # 3. 动态获取【当前角色】的状态库
    # 优先取当前角色，取不到则取 default，再取不到则用保底列表
    current_states = config.role_states.get(config.CURRENT_ROLE, config.role_states.get("default", {}))
    
    state_desc = ""
    env_desc = ""

    if 23 <= hour or hour < 7:
        pool = current_states.get("sleep", ["正在休息"])
        state_desc = random.choice(pool)
        env_desc = "深夜模式，适合休息。"
    elif 11 <= hour < 14:
        pool = current_states.get("lunch", ["在吃饭"])
        state_desc = random.choice(pool)
        env_desc = "午休时间。"
    else:
        pool = current_states.get("idle", ["无所事事"])
        state_desc = random.choice(pool)
        env_desc = "日常活动时间。"

    hints.append(f"【环境氛围】{env_desc}")
    hints.append(f"【你的当前状态】{state_desc}。")
    
    return "\n".join(hints)

async def call_zhipu_ai(user_id: str, user_msg: str = None, system_hint: str = ""):
    if user_id not in config.user_memory: config.user_memory[user_id] = []
    if user_id not in config.user_facts: config.user_facts[user_id] = []

    # 1. 组装 System Prompt (人设 + 环境 + 长期记忆)
    env_prompt = get_environment_hint()
    long_memory = "\n".join(config.user_facts[user_id][-10:]) or "暂无"

    full_system_prompt = (
        f"{config.SYSTEM_PROMPT}\n\n"
        f"=== 当前环境与状态 (绝对真实) ===\n{env_prompt}\n\n"
        f"=== 核心记忆库 ===\n{long_memory}\n"
    )

    messages = [{"role": "system", "content": full_system_prompt}]
    
    # 2. 放入短期记忆 (纯净对话)
    messages.extend(config.user_memory[user_id]) 
    
    # 3. 放入当前消息
    if user_msg:
        messages.append({"role": "user", "content": user_msg})
    else:
        # 主动搭讪
        messages.append({"role": "user", "content": f"（心里突然想到：{system_hint}）"})

    try:
        # 调试日志
        prompt_debug = json.dumps(messages[-2:], ensure_ascii=False, indent=2)
        logger.info(f"\n{'='*20} [LLM Input] {'='*20}\n...{prompt_debug}\n{'='*60}")
    except: pass

    url = "[https://open.bigmodel.cn/api/paas/v4/chat/completions](https://open.bigmodel.cn/api/paas/v4/chat/completions)"
    headers = {"Authorization": f"Bearer {config.API_KEY}", "Content-Type": "application/json"}
    data = {"model": "glm-4-flash", "messages": messages, "temperature": 0.95}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=data, headers=headers)
            result = resp.json()

            if 'choices' in result:
                raw_reply = result['choices'][0]['message']['content']
                
                # 4. 更新记忆 (存纯净版)
                if user_msg:
                    config.user_memory[user_id].append({"role": "user", "content": user_msg})
                
                config.user_memory[user_id].append({"role": "assistant", "content": raw_reply})
                
                if len(config.user_memory[user_id]) > config.MAX_MEMORY + 4:
                    await consolidate_memory(user_id)
                else:
                    config.save_data()
                
                return parse_reply(raw_reply)
            else:
                return Message(f"喵呜...脑子卡住了喵: {result}")
    except Exception as e:
        return Message(f"喵酱生病了喵... ({str(e)})")