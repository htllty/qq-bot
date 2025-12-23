import httpx
import time
from .config import SYSTEM_PROMPT, API_KEY, user_memory, MAX_MEMORY

async def call_zhipu_ai(user_id: str, user_msg: str = None, system_hint: str = ""):
    """
    统一调用 AI 的接口。
    user_msg: 用户说的话（如果是主动搭讪，这里可以留空或填提示词）
    system_hint: 额外的系统提示（比如时间、场景）
    """
    
    # 1. 初始化记忆
    if user_id not in user_memory:
        user_memory[user_id] = []

    # 2. 注入时间
    current_time = time.strftime("%H:%M", time.localtime())
    full_prompt = f"{SYSTEM_PROMPT}\n(当前时间：{current_time})\n{system_hint}"

    # 3. 构建消息列表
    messages = [{"role": "system", "content": full_prompt}]
    messages.extend(user_memory[user_id]) # 加入历史记忆
    
    # --- 🛠️ 关键修复开始 ---
    # 智谱 API 要求最后一条必须是 User。
    # 如果是主动搭讪 (user_msg is None)，我们将 system_hint 包装成 User 消息发送。
    # 这样 API 会认为这是用户在发指令，但我们在第 5 步不把它存入记忆。
    if user_msg:
        messages.append({"role": "user", "content": user_msg})
    else:
        # 这里的 system_hint 就是 "现在是早上8点，请主动..."
        messages.append({"role": "user", "content": system_hint})
    # --- 🛠️ 关键修复结束 ---

    # 4. 发送请求
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "glm-4-flash",
        "messages": messages, # ✅ 这里修复了你之前代码中 messages 没用上的 Bug
        "temperature": 0.95
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=data, headers=headers)
            result = resp.json()

            if 'choices' in result:
                reply = result['choices'][0]['message']['content']
                
                # 5. 更新记忆
                # 只有当 user_msg 真实存在时，才把用户的这句话存入记忆。
                # 如果是主动搭讪（user_msg 为空），那条伪装的指令不会被存入，
                # 这样记忆里看起来就是机器人突然想起来跟你说话，非常自然。
                if user_msg:
                    user_memory[user_id].append({"role": "user", "content": user_msg})
                
                user_memory[user_id].append({"role": "assistant", "content": reply})
                
                # 截断记忆
                if len(user_memory[user_id]) > MAX_MEMORY * 2:
                    user_memory[user_id] = user_memory[user_id][-MAX_MEMORY * 2:]
                
                return reply
            else:
                return f"喵呜...大脑短路了喵: {result}"
    except Exception as e:
        return f"喵酱掉线了喵... ({str(e)})"