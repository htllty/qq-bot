from nonebot import require, get_bot
from nonebot.log import logger
import random
from datetime import datetime # 引入时间处理库

# 引入定时任务组件
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from .config import ALLOWED_USERS
from .utils import call_zhipu_ai

# --- 任务 1: 每日早安 (每天 08:00) ---
@scheduler.scheduled_job("cron", hour=8, minute=0, id="morning_greet")
async def morning_greet():
    await active_chat("现在是早上8点，请主动跟主人说早安，要元气满满，提醒主人吃早餐喵！")

# --- 任务 2: 每日晚安 (每天 23:00) ---
# 这是进入静音模式前的最后一条消息
@scheduler.scheduled_job("cron", hour=23, minute=0, id="night_greet")
async def night_greet():
    await active_chat("现在是晚上11点，请催促主人快去睡觉，不要熬夜，语气要温柔但坚定喵！")

# --- 任务 3: 随机撒娇 (每 2 小时一次) ---
@scheduler.scheduled_job("interval", hours=2, id="random_care")
async def random_care():
    # 1. 获取当前系统时间 (基于 Docker 里的 Asia/Shanghai 时区)
    current_hour = datetime.now().hour
    
    # 2. 静音时间判断：23点(含)之后，或者 8点(不含)之前
    # 即：[23, 0, 1, 2, 3, 4, 5, 6, 7] 点不说话
    if current_hour >= 23 or current_hour < 8:
        logger.info(f"当前是休息时间 ({current_hour}点)，喵酱保持安静，不打扰主人休息喵。")
        return

    # 3. 概率触发 (50% 概率说话，防止太烦人)
    if random.random() < 0.5:
        return
        
    await active_chat("现在是闲暇时间，请主动找个话题跟主人聊天，或者撒个娇求摸摸喵~")

# --- 核心主动发送函数 ---
async def active_chat(prompt_instruction: str):
    try:
        bot = get_bot()
    except ValueError:
        logger.warning("喵酱还没连接上，无法主动发消息喵...")
        return

    for user_id in ALLOWED_USERS:
        # system_hint 告诉 AI 这次为什么要说话
        hint = f"【系统指令】{prompt_instruction} (直接输出对主人说的话)"
        
        # 调用 AI 生成内容 (user_msg 为 None)
        # 注意：这里调用的是 utils.py 里的函数，它会自动处理记忆
        reply = await call_zhipu_ai(user_id, user_msg=None, system_hint=hint)
        
        # 主动发送私聊消息
        try:
            await bot.send_private_msg(user_id=int(user_id), message=reply)
            logger.info(f"已向 {user_id} 发送主动消息: {reply}")
        except Exception as e:
            logger.error(f"发送失败: {e}")