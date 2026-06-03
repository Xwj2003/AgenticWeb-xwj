"""
LLM 客户端:统一封装 OpenAI 兼容接口的调用。
支持 DeepSeek / 智谱 / Kimi / OpenAI 等任意兼容服务商。
"""
import json
import time
import re
from typing import Optional
from openai import OpenAI
from config import Config


class LLMClient:
    def __init__(self):
        self.client = OpenAI(
            api_key=Config.LLM_API_KEY,
            base_url=Config.LLM_BASE_URL,
            timeout=Config.LLM_TIMEOUT,
        )
        self.model = Config.LLM_MODEL

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        json_mode: bool = False,
        temperature: Optional[float] = None,
    ) -> str:
        """
        发起 LLM 对话。
        :param json_mode: 强制 JSON 输出(适用于结构化产出)
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else Config.LLM_TEMPERATURE,
            "max_tokens": Config.LLM_MAX_TOKENS,
        }
        # 部分模型支持 response_format JSON 模式,提升结构化产出可靠性
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    def chat_json(
        self,
        system_prompt: str,
        user_message: str,
        max_retries: int = None,
    ) -> dict:
        """
        调用 LLM 并强制解析为 JSON,失败自动重试。
        这是各 Agent 产出结构化内容的核心方法。

        重试策略:
        - JSONDecodeError:LLM 输出格式错,值得重试(带错误反馈)
        - 其他 Exception:API 级别错误(网络/鉴权/URL 错误),立即抛出,不重试
        """
        max_retries = max_retries or Config.LLM_MAX_RETRIES
        last_error = None

        for attempt in range(max_retries):
            try:
                raw = self.chat(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    json_mode=True,
                )
                cleaned = self._strip_code_fence(raw)
                return json.loads(cleaned)
            except json.JSONDecodeError as e:
                last_error = e
                # 重试时把错误反馈给 LLM,自我修正
                user_message = (
                    f"{user_message}\n\n"
                    f"上一次的输出无法解析为 JSON,错误:{e}。"
                    f"请重新输出严格合法的 JSON,不要任何 Markdown 代码块包装。"
                )
                time.sleep(1)
            except Exception as e:
                # API 调用本身失败(404/401/网络不通等),无需重试,直接暴露
                # 常见原因:
                #   404 → LLM_BASE_URL 配置错误(Ollama 需加 /v1)
                #   401 → LLM_API_KEY 无效
                #   连接拒绝 → 服务未启动
                raise RuntimeError(
                    f"LLM API 调用失败,请检查 .env 配置。\n"
                    f"  当前 base_url : {self.client.base_url}\n"
                    f"  当前 model    : {self.model}\n"
                    f"  错误详情      : {e}\n"
                    f"\n常见修复:\n"
                    f"  Ollama 用户请确保 LLM_BASE_URL=http://localhost:11434/v1\n"
                    f"  其他服务商请确认 base_url 和 api_key 是否正确"
                ) from e

        raise RuntimeError(
            f"LLM 调用 {max_retries} 次后仍无法产出合法 JSON。\n"
            f"最后一次 JSON 解析错误:{last_error}"
        )

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        """
        某些模型即使开启 json_mode 也可能用 ```json 包裹,这里做兜底清理。
        """
        text = text.strip()
        # 移除三反引号代码块
        m = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        return text