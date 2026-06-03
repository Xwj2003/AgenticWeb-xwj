"""
Agent 基类:封装通用的 LLM 调用、日志记录、产物保存逻辑。
每个具体 Agent 只需实现 system_prompt 和 run 方法。
"""
import os
import json
from abc import ABC, abstractmethod
from rich.console import Console
from llm_client import LLMClient
from shared_context import SharedContext

console = Console()


class BaseAgent(ABC):
    name: str = "BaseAgent"
    role_desc: str = ""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    @abstractmethod
    def system_prompt(self) -> str:
        """每个 Agent 的人设和职责约束"""
        ...

    @abstractmethod
    def run(self, ctx: SharedContext) -> None:
        """执行 Agent 任务,把产出写入 ctx"""
        ...

    # ---- 工具方法 ----
    def log(self, ctx: SharedContext, msg: str):
        ctx.log(self.name, "info", msg)
        console.print(f"  [dim cyan]{self.name}[/]: {msg}")

    def announce_start(self):
        console.rule(f"[bold yellow]🤖 {self.name} - {self.role_desc}")

    def call_llm_json(self, user_message: str, ctx: SharedContext, artifact_name: str = "") -> dict:
        """
        统一调用入口:
        1) 落盘 prompt(可审计 AI 使用过程)
        2) 调用 LLM 拿 JSON
        3) 落盘响应
        """
        if artifact_name and ctx.artifacts_dir:
            self._save_prompt(ctx, artifact_name, user_message)

        result = self.llm.chat_json(
            system_prompt=self.system_prompt(),
            user_message=user_message,
        )

        if artifact_name and ctx.artifacts_dir:
            ctx.save_artifact(f"{artifact_name}_output.json", result)
        return result

    def _save_prompt(self, ctx: SharedContext, artifact_name: str, user_message: str):
        """保存 prompt 到产物目录,便于交付审计"""
        path = os.path.join(ctx.artifacts_dir, f"{artifact_name}_prompt.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {self.name} Prompt\n\n")
            f.write("## System Prompt\n\n")
            f.write(self.system_prompt())
            f.write("\n\n## User Message\n\n")
            f.write(user_message)
