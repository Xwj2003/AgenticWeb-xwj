"""
全局配置:从环境变量读取
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # LLM 配置
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
    LLM_MODEL = os.getenv("LLM_MODEL", "qwen-coder-8k")

    # 系统配置
    HUMAN_IN_LOOP = os.getenv("HUMAN_IN_LOOP", "false").lower() == "true"
    OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # 生成后是否自动 npm install + npm start 并打开浏览器(QA 通过时)
    AUTO_RUN = os.getenv("AUTO_RUN", "false").lower() == "true"
    RUN_PORT = int(os.getenv("RUN_PORT", "3000"))

    # LLM 调用参数
    LLM_TEMPERATURE = 0.3        # 偏确定性,代码生成不要太发散
    LLM_MAX_TOKENS = 8000
    LLM_TIMEOUT = 600
    LLM_MAX_RETRIES = 3          # JSON 解析失败时的重试次数

    @classmethod
    def validate(cls):
        if not cls.LLM_API_KEY or cls.LLM_API_KEY == "your-api-key-here":
            raise ValueError(
                "请在 .env 文件中配置 LLM_API_KEY。可参考 ..env。"
            )