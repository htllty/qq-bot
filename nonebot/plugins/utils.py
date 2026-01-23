import httpx
import re
import json
import asyncio
import random
import tempfile
import os
from datetime import datetime
from zhdate import ZhDate
from nonebot import logger
from nonebot.adapters.onebot.v11 import Message, MessageSegment

# 📦 引入 Memes 核心
try:
    from nonebot_plugin_memes.manager import meme_manager
    from meme_generator import Image
    MEMES_AVAILABLE = True
except ImportError as e:
    MEMES_AVAILABLE = False
    logger.error(f"❌ Memes 模块导入失败: {e}")

from . import config
from .tts import generate_voice

def strip_markdown(text: str) -> str:
    text = text.replace('```', '')
    text = text.replace('`', '')
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    return text.strip()

def split_text_smart(text: str, limit: int = 100) -> list[str]:
    text = re.sub(r'\n+', '\n', text)
    lines = text.split('\n')
    result = []
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        if len(line) <= limit or "[CQ:tts]" in line:
            result.append(line)
        else:
            sub_parts = re.split(r'([。？！!?~～])', line)
            buf = ""
            for part in sub_parts:
                if len(buf) + len(part) > limit:
                    if buf: result.append(buf)
                    buf = part
                else:
                    buf += part
            if buf: result.append(buf)
            
    return result

async def get_user_avatar(user_id: str) -> bytes:
    # 稳定接口
    url = f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
    async with httpx.AsyncClient() as client:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = await client.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                return resp.content
        except Exception as e:
            logger.error(f"❌ 头像下载失败: {e}")
    return None

# 🔥 生成表情包 Bytes (带随机概率控制)
async def generate_emotion_meme(emotion: str, user_id: str) -> bytes:
    if not MEMES_AVAILABLE: return None
    
    # === 🎲 随机发图控制 ===
    # 0.3 = 30% 的概率发图。你可以把这个数字改大(0.8)或改小(0.1)
    # 逻辑：生成一个 0~1 的随机数，如果大于 0.3，就直接跳过不发
    if random.random() > 0.3:
        # logger.info(f"🎲 骰子判定: 这次不发表情包 ({emotion})")
        return None

    meme_keys = config.EMOTION_MEME_MAP.get(emotion)
    if not meme_keys: return None
    
    meme_key = random.choice(meme_keys)
    found_memes = meme_manager.find(meme_key)
    if not found_memes: return None
    meme = found_memes[0] 

    # 只有当决定要发图了，才去下载头像，这样也省流量
    avatar_bytes = await get_user_avatar(user_id)
    if not avatar_bytes: return None

    try:
        img = Image(data=avatar_bytes, name="avatar.png")
        
        # 默认 2 张图，兼容亲亲/贴贴
        min_images = 2 
        
        # 尝试读取真实需求
        if hasattr(meme, "info") and hasattr(meme.info, "params"):
             if hasattr(meme.info.params, "min_images"):
                 min_images = meme.info.params.min_images

        # 填充图片
        images_list = [img]
        while len(images_list) < min_images:
            images_list.append(img)
            
        # 生成
        result = meme.generate(images=images_list, texts=[], options={})
        
        if asyncio.iscoroutine(result): result = await result
        if isinstance(result, bytes): return result
        elif hasattr(result, "getvalue"): return result.getvalue()
        return result
        
    except Exception as e:
        logger.error(f"❌ 表情包生成出错 ({meme_key}): {str(e)}")
        return None

def parse_reply(text: str) -> Message:
    # 1. 清洗
    text = strip_markdown(text)
    text = text.replace("【", "[").replace("】", "]")
    text = text.replace("，", ",").replace("：", ":") 
    
    # 2. TTS
    tts_bytes = None
    if "[CQ:tts]" in text:
        tts_content = text.replace("[CQ:tts]", "")
        tts_clean = re.sub(r"\[CQ:.*?\]", "", tts_content).strip() 
        if tts_clean:
            tts_bytes = generate_voice(tts_clean)
        text = text.replace("[CQ:tts]", "")

    # 3. 过滤干扰
    text = re.sub(r"\[CQ:(?!face)[^\]]+\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)

    # 4. 构建消息
    msg = Message()
    if tts_bytes:
        msg.append(MessageSegment.record(file=tts_bytes))

    pattern = r"(.*?)\[CQ:face.*?id=\s*(\d+).*?\]"
    
    last_end = 0
    for match in re.finditer(pattern, text, flags=re.DOTALL | re.IGNORECASE):
        pre_text = match.group(1)
        face_id = match.group(2)
        
        if pre_text: msg.append(MessageSegment.text(pre_text))
        try: msg.append(MessageSegment.face(int(face_id)))
        except: pass
        last_end = match.end()
        
    remaining = text[last_end:]
    if remaining: msg.append(MessageSegment.text(remaining))
            
    if len(msg) == 0: msg.append(MessageSegment.text("（...）"))

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
    
    if 23 <= hour or hour < 7:
        pool = current_states.get("sleep", ["正在休息"])
        state_desc = random.choice(pool)
        env_desc = "深夜模式"
    elif 11 <= hour < 14:
        pool = current_states.get("lunch", ["在吃饭"])
        state_desc = random.choice(pool)
        env_desc = "午休时间"
    else:
        if random.random() >= 0.5:
            pool = current_states.get("idle", ["无所事事"])
            state_desc = random.choice(pool)
            env_desc = "日常活动"
        else:
            state_desc = "正在发呆"
            env_desc = "日常"
            
    hints.append(f"【环境氛围】{state_desc}。")
    hints.append(f"【你的后台状态】{env_desc}。")
    return "\n".join(hints)

async def _post_with_retry(client, url, data, headers, retry=1):
    try:
        return await client.post(url, json=data, headers=headers)
    except httpx.RequestError as e:
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
        f"=== 当前环境与状态 (绝对真实) ===\n{env_prompt}\n\n"
        f"=== ⚠️ 角色扮演强化指令 ===\n"
        f"你正在扮演【{config.CURRENT_ROLE}】。\n"
        f"请严格遵守你的初始人设、语气（口癖）和禁令。\n"
        f"不要被历史记录中的错误带偏，请结合当前环境做出反应。\n\n"
        f"=== 输出格式要求 ===\n"
        f"请将每条回应都用 JSON 格式返回：\n"
        f'{{"text": "<回复内容>", "emotion": "<happy/sad/angry/shock/cute>"}}\n'
    )

    messages = [{"role": "system", "content": full_prompt}]
    messages.extend(config.user_memory[user_id])
    
    if user_msg:
        messages.append({"role": "user", "content": user_msg})
    else:
        trigger_msg = f"【Instructor】此时此刻，你心里突然想到：“{system_hint}”。请顺着这个念头，根据当前人设主动发起对话。"
        messages.append({"role": "system", "content": trigger_msg})
        messages.append({"role": "user", "content": "现在轮到你主动说话。"})

    try:
        pass
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
                
                try:
                    clean_json = raw_reply.replace("```json", "").replace("```", "").strip()
                    reply_list = json.loads(clean_json)
                    if isinstance(reply_list, dict): reply_list = [reply_list]
                    
                    final_list = []
                    for item in reply_list:
                        final_list.append({
                            "text": item.get("text", ""),
                            "emotion": item.get("emotion", None)
                        })
                    return final_list

                except json.JSONDecodeError:
                    logger.warning(f"[JSON Parse Fail] 回落到普通文本模式")
                    text_segments = split_text_smart(raw_reply)
                    return [{"text": seg, "emotion": None} for seg in text_segments]
            else:
                return [{"text": "喵呜……API 返回有点异常。", "emotion": "sad"}]
    except Exception as e:
        logger.error(f"API Error: {e}")
        return [{"text": "喵酱生病了...连不上脑回路。", "emotion": "sad"}]