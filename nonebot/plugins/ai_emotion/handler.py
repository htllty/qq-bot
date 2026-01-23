import json
import random
from nonebot import logger
from nonebot.adapters.onebot.v11 import MessageSegment

# 情绪 -> meme 映射 (这里只做备用，主要逻辑在 utils.py 和 ai_chat.py)
EMOTION_MEMES = {
    "happy": ["petpet", "worship", "pat"],
    "sad": ["cry", "rip"],
    "angry": ["gun", "hammer"],
    "cute": ["rub", "kiss"],
}

async def handle_ai_emotion(event, bot):
    """
    解析 AI JSON 输出
    注意：表情包的生成现在主要由 ai_chat.py 里的逻辑负责调用 utils.generate_emotion_meme
    这里主要负责兜底或者处理纯文本
    """
    text = event.get_plaintext().strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return

    # 1. 发送文字
    if "text" in data and data["text"]:
        await bot.send(event, data["text"])

    # 2. 如果你需要在这里处理表情包，请不要 import send_meme
    # 这里的逻辑其实在 ai_chat.py 里已经通过 generate_emotion_meme 实现了
    # 所以这里可以留空，或者仅做日志记录
    emotion = data.get("emotion")
    if emotion:
        logger.debug(f"检测到情绪: {emotion}，图片生成交由 ai_chat.py 处理")