"""
SharedContext:Agent 之间共享数据的"黑板"。
所有 Agent 读写的中间产物都在这里集中管理,且每次写入都会落盘,
方便事后审计、断点续跑、人工修改。
"""
import os
import json
import time
from typing import Any, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class AgentLog:
    """一次 Agent 活动的记录(用于审计)"""
    agent: str
    action: str
    timestamp: float
    detail: Optional[str] = None


class SharedContext:
    """
    共享上下文。字段含义:
    - requirement: 用户原始一句话需求
    - prd: 产品需求文档(PM 产出)
    - architecture: 技术方案 + API 契约(Architect 产出)
    - backend_files: dict[相对路径, 文件内容](Backend 产出)
    - frontend_files: dict[相对路径, 文件内容](Frontend 产出)
    - devops_files: dict[相对路径, 文件内容](DevOps 产出)
    - qa_report: 质检报告(QA 产出)
    - history: 全部 Agent 活动日志
    """

    def __init__(self, requirement: str, output_dir: str):
        self.requirement: str = requirement
        self.output_dir: str = output_dir            # 整体 output 根目录
        self.project_dir: str = ""                   # 当前项目最终代码输出目录
        self.artifacts_dir: str = ""                 # 中间产物目录

        self.prd: Optional[dict] = None
        self.architecture: Optional[dict] = None
        self.backend_files: dict = {}
        self.frontend_files: dict = {}
        self.devops_files: dict = {}
        self.qa_report: Optional[dict] = None

        # 修复轮次专用:存放上一轮 QA 未通过的 check 列表,
        # summary_for() 会把它们注入进 prompt,让 Agent 定向修复
        self.qa_failures: list = []

        self.history: list[AgentLog] = []

    # ---- 路径初始化 ----
    def init_paths(self, project_name: str):
        """根据项目名初始化产出目录"""
        base = os.path.join(self.output_dir, project_name)
        self.project_dir = base
        self.artifacts_dir = os.path.join(base, "_agent_artifacts")
        os.makedirs(self.project_dir, exist_ok=True)
        os.makedirs(self.artifacts_dir, exist_ok=True)

    # ---- 活动记录 ----
    def log(self, agent: str, action: str, detail: str = ""):
        self.history.append(
            AgentLog(agent=agent, action=action, timestamp=time.time(), detail=detail)
        )

    # ---- 中间产物落盘 ----
    def save_artifact(self, filename: str, content: Any):
        """把任意 Agent 中间产物(JSON/文本)保存到 _agent_artifacts 目录"""
        if not self.artifacts_dir:
            return
        path = os.path.join(self.artifacts_dir, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if isinstance(content, (dict, list)):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(content, f, ensure_ascii=False, indent=2)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(str(content))

    def save_history(self):
        """把整个活动历史落盘,用于交付时回顾"""
        if not self.artifacts_dir:
            return
        path = os.path.join(self.artifacts_dir, "agent_history.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump([asdict(h) for h in self.history], f, ensure_ascii=False, indent=2)

    # ---- 写文件到最终项目目录 ----
    def write_project_files(self):
        """把所有 Agent 产出的代码文件写入项目目录"""
        all_files = {}
        all_files.update(self.backend_files)
        all_files.update(self.frontend_files)
        all_files.update(self.devops_files)

        for rel_path, content in all_files.items():
            full_path = os.path.join(self.project_dir, rel_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
        return list(all_files.keys())

    # ---- 摘要(给下游 Agent 当 prompt 输入) ----
    def summary_for(self, agent_name: str) -> str:
        """根据下游 Agent 的需要,只暴露它需要看到的上下文字段"""
        parts = [f"# 用户原始需求\n{self.requirement}\n"]
        if self.prd:
            parts.append(f"# PRD (产品需求文档)\n```json\n{json.dumps(self.prd, ensure_ascii=False, indent=2)}\n```\n")
        if self.architecture:
            parts.append(f"# 技术架构方案\n```json\n{json.dumps(self.architecture, ensure_ascii=False, indent=2)}\n```\n")

        # 修复轮次:把上一轮 QA 失败项注入 prompt,要求 Agent 逐一修复
        if self.qa_failures:
            failures_text = "\n".join(
                f"  - [{c['name']}]: {c['detail']}"
                for c in self.qa_failures
            )
            parts.append(
                f"# ⚠️ 上一轮 QA 检查失败项(本次输出必须逐一修复)\n"
                f"{failures_text}\n\n"
                f"请仔细阅读以上失败项,确保你的输出完整解决每一条问题,不要遗漏任何接口或文件。"
            )

        # 后端/前端 agent 可能需要彼此的接口契约,这部分已在 architecture 中
        return "\n".join(parts)