import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

# 初始化 NoneBot
nonebot.init()

# 注册适配器
driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

# 加载内置插件 (Echo 回声插件，用于测试)
nonebot.load_builtin_plugins("echo")

# 加载自定义插件目录
# 只要把 py 文件放在 plugins 目录下，就会自动加载
nonebot.load_plugins("plugins")

if __name__ == "__main__":
    nonebot.run()
