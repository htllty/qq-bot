from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot, Event
from nonebot.rule import to_me
from .config import ALLOWED_USERS, API_KEY
from .utils import call_zhipu_ai

# 注册消息响应器 (需私聊或@机器人)
chat = on_message(rule=to_me(), priority=5)

@chat.handle()
async def handle_first_receive(bot: Bot, event: Event):
    user_id = str(event.get_user_id())
    user_msg = event.get_plaintext().strip()

    # 基础检查
    if user_id not in ALLOWED_USERS or not user_msg:
        return
    
    if not API_KEY:
        await chat.finish("喵呜...API Key 没填喵！")

    # 调用工具函数
    reply = await call_zhipu_ai(user_id, user_msg)
    
    # 发送回复
    await chat.finish(reply)