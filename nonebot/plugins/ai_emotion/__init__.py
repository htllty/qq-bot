from nonebot import on_message
from .handler import handle_ai_emotion

matcher = on_message(priority=99, block=False)

@matcher.handle()
async def _(event, bot):
    await handle_ai_emotion(event, bot)
