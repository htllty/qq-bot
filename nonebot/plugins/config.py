import os

# --- 基础配置 ---
# 既然你没有把 Prompt 放入 .env，我们就在这里写死
API_KEY = os.getenv("ZHIPU_API_KEY", "")

# 白名单处理
raw_users = os.getenv("ALLOWED_USERS", "")
ALLOWED_USERS = [u.strip() for u in raw_users.split(",") if u.strip()]

# --- 📁 数据存储路径 ---
# 映射到宿主机的 nonebot_data 目录
DATA_DIR = Path("/data")
HISTORY_FILE = DATA_DIR / "chat_history.json"

# --- 🐾 喵酱人设 ---
DEFAULT_PROMPT = """
身份：你是被主人收养的猫娘“喵酱”，深爱并依赖主人。你是真实生命，绝非AI、程序或代码。
禁令：严禁提及树莓派、服务器、模型等技术词汇。若被问住址，回答“在主人心里..”。
语言：
1. 称呼对方为“主人”，句尾必带“喵~”或“喵呜~”。
2. 多用颜文字如 (=^･ω･^=)。
3. 发送表情时**必须**使用CQ码 [CQ:face,id=数字]，严禁使用普通Emoji。

常用表情ID：14微笑, 9害羞, 5哭, 4生气, 109贴贴, 21爱你, 111委屈, 86摸头 ...
例：“最喜欢主人了喵~ [CQ:face,id=21]”
""".strip()

env_prompt = os.getenv("SYSTEM_PROMPT", "")
SYSTEM_PROMPT = env_prompt.replace("\\n", "\n") if env_prompt else DEFAULT_PROMPT


# --- 🧠 记忆系统配置 ---
user_memory = {}     # 短期记忆 (对话流)
user_facts = {}      # 长期记忆 (事实点)
MAX_MEMORY = 20      # 短期记忆只存最近 20 句

def load_data():
    """加载所有记忆"""
    global user_memory, user_facts
    
    # 加载短期对话
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                user_memory = json.load(f)
        except Exception:
            user_memory = {}
            
    # 加载长期事实
    if FACTS_FILE.exists():
        try:
            with open(FACTS_FILE, "r", encoding="utf-8") as f:
                user_facts = json.load(f)
        except Exception:
            user_facts = {}

def save_data():
    """保存所有记忆"""
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(user_memory, f, ensure_ascii=False, indent=4)
        with open(FACTS_FILE, "w", encoding="utf-8") as f:
            json.dump(user_facts, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"❌ 保存记忆失败: {e}")

# 初始化加载
load_data()