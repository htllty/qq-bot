import httpx
from nonebot import logger
from .config import TTS_API_URL

def generate_voice(text: str) -> bytes:
    """
    调用本地/远程 Spark-TTS 接口生成语音
    """
    if not TTS_API_URL:
        logger.warning("TTS 接口地址未配置")
        return None

    try:
        # 发送 POST 请求给 Spark-TTS 服务
        resp = httpx.post(
            TTS_API_URL, 
            json={"text": text, "speaker": "default", "speed": 1.0},
            timeout=60.0 # 生成语音可能比较慢，超时设长一点
        )
        
        if resp.status_code == 200:
            logger.info(f"✅ 语音生成成功，大小: {len(resp.content)} bytes")
            return resp.content
        else:
            logger.error(f"❌ TTS 服务报错: {resp.status_code} - {resp.text}")
            return None
            
    except Exception as e:
        logger.error(f"❌ 连接 TTS 服务失败: {e}")
        return None