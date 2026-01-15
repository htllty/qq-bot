from nonebot import require, get_bot
from nonebot.log import logger
import random
from datetime import datetime
import asyncio
import httpx
from . import config

# 引入定时任务组件
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from .config import ALLOWED_USERS
from .utils import call_zhipu_ai

# =========================================================
# ⏰ 定时任务配置区 (通用版)
# =========================================================

# --- 任务 1: 每日早安 (每天 08:00) ---
@scheduler.scheduled_job("cron", hour=8, minute=0, id="morning_greet")
async def morning_greet():
    # 中性指令：不提“主人”，只提“对方”
    await active_chat("天亮了，新的一天开始了，根据当前人设去跟对方打个招呼。")

# --- 任务 2: 每日晚安 (每天 23:00) ---
@scheduler.scheduled_job("cron", hour=23, minute=0, id="night_greet")
async def night_greet():
    # 中性指令：让 AI 自己决定用什么语气催睡
    await active_chat("夜深了，根据当前人设提醒对方休息，熬夜对身体不好。")

# --- 任务 3: 随机关心 (每 3 小时一次) ---
@scheduler.scheduled_job("interval", hours=3, id="random_care")
async def random_care():
    # 1. 获取当前时间
    current_hour = datetime.now().hour
    
    # 2. 静音模式 (23点-8点不打扰)
    if current_hour >= 23 or current_hour < 8:
        return

    # 3. 概率触发 (70% 概率，避免太烦人)
    if random.random() > 0.3:
        return
        
    env_hint = f"当前时间：{datetime.now().strftime('%H:%M')}"
    
    topic = await generate_topic_by_time(
        role_name=config.CURRENT_ROLE,
        env_hint=env_hint
    )

    await active_chat(topic)


async def generate_topic_by_time(role_name: str, env_hint: str):
    """
    只负责生成“聊什么”，不负责说话
    """
    
    prompt = f"""
你是一个对话策划助手，不参与角色扮演。

当前信息：
- 时间与环境：{env_hint}
- AI 当前人设：{role_name}

你的任务：
根据当前时间和状态，生成一个【适合主动发起聊天的话题】。

要求：
- 使用固定格式输出
- 不要使用任何角色语气
- 不要直接生成聊天内容
- 内容应简短、客观、可供角色发挥

输出格式如下（必须严格遵守）：

【话题类型】
【时间段】
【触发原因】
【建议方向】
"""

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "glm-4-flash",
        "messages": [
            {"role": "system", "content": "你是一个冷静、理性的对话策划器。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.4  # 低温，保证稳定
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=data, headers=headers)
        result = resp.json()

    return result["choices"][0]["message"]["content"]


# =========================================================
# 🚀 核心发送逻辑
# =========================================================


async def active_chat(thought_content: str):
    try:
        bot = get_bot()
    except ValueError:
        return

    for user_id in ALLOWED_USERS:
        # 获取消息列表
        replies = await call_zhipu_ai(user_id, user_msg=None, system_hint=thought_content)
        
        try:
            # 🔥 循环发送
            for msg in replies:
                await bot.send_private_msg(user_id=int(user_id), message=msg)
                logger.info(f"✅ 主动消息发送成功")
                await asyncio.sleep(2.0) # 间隔 2 秒
        except Exception as e:
            logger.error(f"❌ 发送失败: {e}")