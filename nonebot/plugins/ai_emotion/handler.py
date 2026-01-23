import json
import random
from nonebot_plugin_memes import send_meme
from nonebot.adapters.onebot.v11 import MessageSegment

# 情绪 -> meme 映射
EMOTION_MEMES = {
    "happy": ["happy_1", "happy_2"],
    "sad": ["sad_1"],
    "angry": ["angry_1"],
    "cute": ["nya_1"],
}

async def handle_ai_emotion(event, bot):
    """解析 AI JSON 输出，并发送文字+表情"""
    text = event.get_plaintext().strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return

    # 文字
    if "text" in data:
        await bot.send(event, data["text"])

    # 表情
    emotion = data.get("emotion")
    if emotion and emotion in EMOTION_MEMES:
        meme = random.choice(EMOTION_MEMES[emotion])
        await send_meme(event, meme)

    # 可选语音
    # voice_file = data.get("voice")
    # if voice_file:
    #     await bot.send(event, MessageSegment.record(voice_file))
