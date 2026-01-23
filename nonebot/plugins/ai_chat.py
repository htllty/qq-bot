from nonebot import on_message, on_command
from nonebot.adapters.onebot.v11 import Bot, Event, Message, MessageSegment
from nonebot.params import CommandArg
from nonebot.rule import to_me
from nonebot.exception import FinishedException
from nonebot import logger

# ✅ 必须这样导入，才能使用 utils.xxx
from . import config
from . import utils 

import json
import asyncio

chat = on_message(rule=to_me(), priority=10, block=True) 

@chat.handle()
async def handle_first_receive(bot: Bot, event: Event):
    user_id = str(event.get_user_id())
    user_msg = event.get_plaintext().strip()

    # 权限与空消息检查
    if config.ALLOWED_USERS and user_id not in config.ALLOWED_USERS: return
    if not user_msg: return
    if user_msg.startswith("@"): return # 防止自触发
    if not config.API_KEY: await chat.finish("喵呜...API Key 没填喵！")

    # 获取 AI 回复
    # ✅ 这里调用 utils.call_zhipu_ai 就不会报错了
    replies = await utils.call_zhipu_ai(user_id, user_msg)
    
    # 循环处理每一条回复
    for i, item in enumerate(replies):
        text_content = item.get("text", "")
        emotion = item.get("emotion", None)
        
        # --- 1. 优先处理表情包 ---
        if emotion and emotion != "null":
            try:
                await asyncio.sleep(0.5)
                logger.info(f"🎨 正在生成表情包: {emotion}")
                meme_bytes = await utils.generate_emotion_meme(emotion, user_id)
                if meme_bytes:
                    await chat.send(MessageSegment.image(meme_bytes))
            except Exception as e:
                logger.error(f"❌ 发送表情包失败: {e}")

        # --- 2. 处理文字内容 ---
        if text_content:
            try:
                # 使用清洗函数构建消息 (防假CQ码)
                msg_obj = utils.parse_reply(text_content)
                await chat.send(msg_obj)
            except Exception as e:
                logger.error(f"❌ 发送文字消息失败: {e}")
                # 兜底：发纯文本
                safe_text = text_content.replace("[", "【").replace("]", "】")
                await chat.send(safe_text)
        
        # --- 3. 间隔 ---
        if i < len(replies) - 1:
            await asyncio.sleep(1.5)

# --- 🛠️ 系统管理指令区 ---

cmd_help = on_command("help", aliases={"帮助", "菜单", "指令"}, priority=5, block=True)
@cmd_help.handle()
async def _(event: Event):
    if config.ALLOWED_USERS and str(event.get_user_id()) not in config.ALLOWED_USERS: return
    help_msg = """✨ 喵酱指令清单 ✨
--------------------
@help / @菜单
  > 查看此列表
@查看记忆 / @添加记忆 <内容> / @删除记忆 <编号>
@查看短期记忆
@角色列表 / @切换角色 <名字>
@system / @重载人设
--------------------"""
    await cmd_help.finish(help_msg)

cmd_roles = on_command("角色列表", aliases={"人设列表"}, priority=5, block=True)
@cmd_roles.handle()
async def _(event: Event):
    if config.ALLOWED_USERS and str(event.get_user_id()) not in config.ALLOWED_USERS: return
    if not config.ROLES_FILE.exists(): await cmd_roles.finish("⚠️ 还没有 roles.json 文件喵！")
    try:
        with open(config.ROLES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        msg = "🎭 可用角色列表：\n" + "-"*15 + "\n"
        current = data.get("current", "")
        if "roles" in data:
            for key in data["roles"]:
                prefix = "✅ " if key == current else "⚪ "
                msg += f"{prefix}{key}\n"
        else:
            for key in data: msg += f"⚪ {key}\n"
        await cmd_roles.finish(msg)
    except FinishedException: raise
    except Exception as e: await cmd_roles.finish(f"读取文件出错喵: {e}")

cmd_switch = on_command("切换角色", aliases={"切换人设", "变身"}, priority=5, block=True)
@cmd_switch.handle()
async def _(event: Event, args: Message = CommandArg()):
    if config.ALLOWED_USERS and str(event.get_user_id()) not in config.ALLOWED_USERS: return
    role_name = args.extract_plain_text().strip()
    if not role_name: await cmd_switch.finish("请告诉我角色名喵")
    config.load_roles()
    if config.save_role_selection(role_name):
        config.load_roles()
        config.refresh_user_memory()
        await cmd_switch.finish(f"✅ 变身成功！当前是：{role_name}")
    else:
        await cmd_switch.finish(f"❌ 找不到角色 {role_name} 喵。")

cmd_system = on_command("system", aliases={"人设", "提示词"}, priority=1, block=True)
@cmd_system.handle()
async def _(event: Event, args: Message = CommandArg()):
    if config.ALLOWED_USERS and str(event.get_user_id()) not in config.ALLOWED_USERS: return
    new_prompt = args.extract_plain_text().strip()
    if not new_prompt:
        preview = config.SYSTEM_PROMPT[:200] + "..."
        await cmd_system.finish(f"🎭 当前完整人设：\n{preview}")
    else:
        config.SYSTEM_PROMPT = new_prompt
        await cmd_system.finish(f"✅ 人设已临时更新！(重启后失效)")

cmd_reload = on_command("重载人设", aliases={"刷新配置"}, priority=5, block=True)
@cmd_reload.handle()
async def _(event: Event):
    if config.ALLOWED_USERS and str(event.get_user_id()) not in config.ALLOWED_USERS: return
    config.load_roles()
    await cmd_reload.finish("🔄 人设文件已重新读取喵！")

cmd_view_mem = on_command("查看记忆", aliases={"记忆列表"}, priority=5, block=True)
@cmd_view_mem.handle()
async def _(event: Event):
    if config.ALLOWED_USERS and str(event.get_user_id()) not in config.ALLOWED_USERS: return
    facts = config.user_facts.get(str(event.get_user_id()), [])
    if not facts: await cmd_view_mem.finish("暂无长期记忆喵~")
    msg = "\n".join([f"[{i+1}] {f}" for i, f in enumerate(facts)])
    await cmd_view_mem.finish(f"📚 核心记忆：\n{msg}")

cmd_add_mem = on_command("添加记忆", aliases={"植入记忆"}, priority=5, block=True)
@cmd_add_mem.handle()
async def _(event: Event, args: Message = CommandArg()):
    user_id = str(event.get_user_id())
    if config.ALLOWED_USERS and user_id not in config.ALLOWED_USERS: return
    new_fact = args.extract_plain_text().strip()
    if not new_fact: await cmd_add_mem.finish("请输入内容喵")
    if user_id not in config.user_facts: config.user_facts[user_id] = []
    config.user_facts[user_id].append(f"【植入】{new_fact}")
    config.save_data()
    await cmd_add_mem.finish(f"已记住：{new_fact}")

cmd_del_mem = on_command("删除记忆", aliases={"遗忘记忆"}, priority=5, block=True)
@cmd_del_mem.handle()
async def _(event: Event, args: Message = CommandArg()):
    user_id = str(event.get_user_id())
    if config.ALLOWED_USERS and user_id not in config.ALLOWED_USERS: return
    msg = args.extract_plain_text().strip()
    if not msg.isdigit(): await cmd_del_mem.finish("请输入编号喵")
    idx = int(msg) - 1
    facts = config.user_facts.get(user_id, [])
    if 0 <= idx < len(facts):
        rem = facts.pop(idx)
        config.save_data()
        await cmd_del_mem.finish(f"已忘掉：{rem}")
    else:
        await cmd_del_mem.finish("找不到该编号喵。")

cmd_view_short = on_command("查看短期记忆", aliases={"查看对话"}, priority=5, block=True)
@cmd_view_short.handle()
async def _(event: Event):
    user_id = str(event.get_user_id())
    if config.ALLOWED_USERS and user_id not in config.ALLOWED_USERS: return
    mem = config.user_memory.get(user_id, [])[-10:]
    if not mem: await cmd_view_short.finish("暂无对话记录喵。")
    msg = "\n".join([f"{'主人' if m['role']=='user' else '喵酱'}: {m['content'][:15]}..." for m in mem])
    await cmd_view_short.finish(f"💭 最近对话：\n{msg}")