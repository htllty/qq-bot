from nonebot import on_message, on_command
from nonebot.adapters.onebot.v11 import Bot, Event, Message, MessageSegment
from nonebot.params import CommandArg
from nonebot.rule import to_me
# ⚠️ 必须导入这个异常
from nonebot.exception import FinishedException
from . import config
from .utils import call_zhipu_ai, generate_emotion_meme
import json
import asyncio # 👈 新增：用于延时


chat = on_message(rule=to_me(), priority=10, block=True) 

@chat.handle()
async def handle_first_receive(bot: Bot, event: Event):
    user_id = str(event.get_user_id())
    user_msg = event.get_plaintext().strip()

    if user_id not in config.ALLOWED_USERS or not user_msg: return
    if user_msg.startswith("@"): return
    if not config.API_KEY: await chat.finish("喵呜...API Key 没填喵！")

    # 获取消息列表 (现在是 list of dict)
    replies = await call_zhipu_ai(user_id, user_msg)
    
    # 🔥 循环发送逻辑更新
    for i, item in enumerate(replies):
        text_content = item["text"]
        emotion = item["emotion"]
        
        # 1. 先发文字 (如果有 TTS 标签，utils 里的 parse_reply 逻辑如果是 Message 对象需要注意)
        # 简单起见，这里直接发文字。如果你的 utils.parse_reply 处理了 [CQ:tts]，可以在这里调用它
        # msg_obj = parse_reply(text_content) 
        # await chat.send(msg_obj)
        
        # 简单文字发送：
        if text_content:
            await chat.send(text_content)
        
        # 2. 处理表情包 (如果有 emotion 且不是最后一条，或者最后一条也可以发)
        if emotion:
            # ⏳ 生成表情包需要时间，稍微延时一点点让体验更像“发完文字随手发个表情”
            await asyncio.sleep(0.5) 
            
            meme_bytes = await generate_emotion_meme(emotion, user_id)
            if meme_bytes:
                await chat.send(MessageSegment.image(meme_bytes))
        
        # 3. 模拟人类打字间隔
        if i < len(replies) - 1:
            await asyncio.sleep(1.5)

    # 结束事件 (避免 Nonebot 继续向下传播)
    # 注意：如果上面都在用 send，这里用 finish 可能会导致最后一条没发出来就断了，或者只是用来截断。
    # 因为上面已经发完了，这里可以直接 return 或者发一个空的 finish
    # await chat.finish() 
    # 为了保险，不做任何操作直接结束函数即可，或者 raise FinishedException

# --- 🛠️ 系统管理指令区 ---
# 注意：以下所有指令均未调用记忆存储函数，因此交互过程天然不进记忆

# 1. 帮助菜单
cmd_help = on_command("help", aliases={"帮助", "菜单", "指令"}, priority=5, block=True)

@cmd_help.handle()
async def _(event: Event):
    user_id = str(event.get_user_id())
    if user_id not in config.ALLOWED_USERS: return

    help_msg = """✨ 喵酱指令清单 ✨
--------------------
@help / @菜单
  > 查看此列表

@查看记忆
  > 查看长期记忆库

@添加记忆 <内容>
  > 强行植入一条记忆

@删除记忆 <编号>
  > 删除某条记忆

@查看短期记忆
  > 查看最近对话流

@角色列表
  > 查看所有可用人设

@切换角色 <名字>
  > 变身！(例: @切换角色 catgirl)

@system / @人设
  > 查看当前人设详情
--------------------
喵呜~ 只有以 @ 开头的消息才会被当做指令哦！"""
    await cmd_help.finish(help_msg)

# 2. 角色管理
cmd_roles = on_command("角色列表", aliases={"人设列表"}, priority=5, block=True)
@cmd_roles.handle()
async def _(event: Event):
    if str(event.get_user_id()) not in config.ALLOWED_USERS: return
    
    if not config.ROLES_FILE.exists():
        await cmd_roles.finish("⚠️ 还没有 roles.json 文件喵！")

    try:
        with open(config.ROLES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        msg = "🎭 可用角色列表：\n" + "-"*15 + "\n"
        if "roles" in data:
            current = data.get("current", "")
            for key in data["roles"]:
                prefix = "✅ " if key == current else "⚪ "
                msg += f"{prefix}{key}\n"
        else:
            for key in data: msg += f"⚪ {key}\n"
                
        msg += "-"*15 + "\n发送 '@切换角色 <名字>' 即可切换喵！"
        await cmd_roles.finish(msg)
    # ⚠️ 关键修复：显式捕获并重新抛出正常结束信号
    except FinishedException:
        raise
    # 捕获其他真正的错误
    except Exception as e:
        await cmd_roles.finish(f"读取文件出错喵: {e}")

cmd_switch = on_command("切换角色", aliases={"切换人设", "变身"}, priority=5, block=True)
@cmd_switch.handle()
async def _(event: Event, args: Message = CommandArg()):
    if str(event.get_user_id()) not in config.ALLOWED_USERS: return
    role_name = args.extract_plain_text().strip()
    if not role_name: await cmd_switch.finish("请告诉我角色名喵，如：@切换角色 hacker")

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
    if str(event.get_user_id()) not in config.ALLOWED_USERS: return
    new_prompt = args.extract_plain_text().strip()
    if not new_prompt:
        preview = config.SYSTEM_PROMPT[:200] + "..."
        await cmd_system.finish(f"🎭 当前完整人设：\n{preview}")
    else:
        config.SYSTEM_PROMPT = new_prompt
        # 临时修改人设不清空记忆，方便调试
        await cmd_system.finish(f"✅ 人设已临时更新！(重启后失效)")

cmd_reload = on_command("重载人设", aliases={"刷新配置"}, priority=5, block=True)
@cmd_reload.handle()
async def _(event: Event):
    if str(event.get_user_id()) not in config.ALLOWED_USERS: return
    config.load_roles()
    await cmd_reload.finish("🔄 人设文件已重新读取喵！")

# --- 🧠 记忆管理指令区 ---

cmd_view_mem = on_command("查看记忆", aliases={"记忆列表"}, priority=5, block=True)
@cmd_view_mem.handle()
async def _(event: Event):
    if str(event.get_user_id()) not in config.ALLOWED_USERS: return
    facts = config.user_facts.get(str(event.get_user_id()), [])
    if not facts: await cmd_view_mem.finish("暂无长期记忆喵~")
    msg = "\n".join([f"[{i+1}] {f}" for i, f in enumerate(facts)])
    await cmd_view_mem.finish(f"📚 核心记忆：\n{msg}")

cmd_add_mem = on_command("添加记忆", aliases={"植入记忆"}, priority=5, block=True)
@cmd_add_mem.handle()
async def _(event: Event, args: Message = CommandArg()):
    user_id = str(event.get_user_id())
    if user_id not in config.ALLOWED_USERS: return
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
    if user_id not in config.ALLOWED_USERS: return
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
    if user_id not in config.ALLOWED_USERS: return
    mem = config.user_memory.get(user_id, [])[-10:]
    if not mem: await cmd_view_short.finish("暂无对话记录喵。")
    msg = "\n".join([f"{'主人' if m['role']=='user' else '喵酱'}: {m['content'][:15]}..." for m in mem])
    await cmd_view_short.finish(f"💭 最近对话：\n{msg}")