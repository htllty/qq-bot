from nonebot import require, get_bot
from nonebot.log import logger
import random
from datetime import datetime

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

    # 3. 概率触发 (30% 概率，避免太烦人)
    if random.random() > 0.3:
        return
        
    # 随机选择一个“中性念头”，适配所有角色
    # 不再包含“撒娇”、“主人”等特定词汇
    thoughts = [
        "突然有点想找对方说话，不知道现在方便吗。",
        "感觉现在的气氛很适合聊聊天。",
        "想根据当前的人设风格，去和对方互动一下。",
        "好久没发消息了，去刷一下存在感吧。",
        "观察一下时间，看看是不是该提醒对方注意休息或者喝水了。"
    ]
    await active_chat(random.choice(thoughts))

# =========================================================
# 🚀 核心发送逻辑
# =========================================================

async def active_chat(thought_content: str):
    """
    主动发起对话
    thought_content: 此时此刻 AI 脑子里的“念头”
    """
    try:
        bot = get_bot()
    except ValueError:
        logger.warning("⚠️ 机器人尚未连接，无法主动发送消息")
        return

    for user_id in ALLOWED_USERS:
        # 我们把这个中性念头传给 utils.py
        # utils.py 会把它包装成: （心里突然想到：天亮了，去打个招呼...）
        # AI 会结合当前人设（比如黑客），输出：“检测到时间已到0800，Admin早安。”
        reply = await call_zhipu_ai(user_id, user_msg=None, system_hint=thought_content)
        
        # 发送消息
        try:
            # 这里的 reply 已经是处理好的 Message 对象（包含表情/语音）
            await bot.send_private_msg(user_id=int(user_id), message=reply)
            logger.info(f"✅ 已向 {user_id} 发送主动消息")
        except Exception as e:
            logger.error(f"❌ 发送失败: {e}")