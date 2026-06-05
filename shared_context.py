"""
SharedContext:Agent 之间共享数据的"黑板"。
所有 Agent 读写的中间产物都在这里集中管理,且每次写入都会落盘,
方便事后审计、断点续跑、人工修改。

v2.1 变更:
  - 新增 user_feedback 字段,存储 HITL 节点收集到的用户反馈文本。
  - summary_for() 在重生成轮次中自动将对应 Agent 的反馈注入 prompt,
    保证 Agent 能看到"用户不满意什么、要怎么改"。
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
    共享上下文(黑板)。字段含义:
    - requirement     : 用户原始一句话需求
    - prd             : 产品需求文档(PM 产出)
    - architecture    : 技术方案 + API 契约(Architect 产出)
    - backend_files   : dict[相对路径, 文件内容](Backend 产出)
    - frontend_files  : dict[相对路径, 文件内容](Frontend 产出)
    - devops_files    : dict[相对路径, 文件内容](DevOps 产出)
    - qa_report       : 质检报告(QA 产出)
    - qa_failures     : 上一轮 QA 未通过的 check 列表(修复轮专用,用完即清空)
    - user_feedback   : HITL 收集到的用户反馈 {agent_name: feedback_text}
                        支持键: "ProductManager"、"Architect"
                        由 orchestrator 在 FEEDBACK 动作后写入;
                        summary_for() 在对应 Agent 的重生成请求中自动注入。
    - history         : 全部 Agent 活动日志
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

        # HITL 反馈:键为 Agent.name,值为用户在 HITL 节点输入的自然语言反馈。
        # orchestrator 在用户选择"提供反馈重生成"后写入,
        # summary_for() 在该 Agent 的下一次运行中自动注入。
        # 键名与各 Agent 类的 name 属性严格一致:
        #   "ProductManager"  ← ProductManagerAgent.name
        #   "Architect"       ← ArchitectAgent.name
        self.user_feedback: dict = {}

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
        """
        根据下游 Agent 的需要,只暴露它该看到的上下文字段。

        注入优先级(从高到低):
          1. 用户原始需求           —— 所有 Agent 可见
          2. PRD                    —— 架构师及以后可见
          3. 技术架构方案           —— 后端/前端/DevOps/QA 可见
          4. 用户反馈(HITL)         —— 仅注入给被重新审核的 Agent
                                       (ProductManager / Architect)
          5. QA 失败项清单          —— 仅在修复轮次中注入
        """
        parts = [f"# 用户原始需求\n{self.requirement}\n"]

        if self.prd:
            parts.append(
                f"# PRD (产品需求文档)\n"
                f"```json\n{json.dumps(self.prd, ensure_ascii=False, indent=2)}\n```\n"
            )

        if self.architecture:
            parts.append(
                f"# 技术架构方案\n"
                f"```json\n{json.dumps(self.architecture, ensure_ascii=False, indent=2)}\n```\n"
            )

        # ── HITL 用户反馈(仅注入给当前被重生成的 Agent) ──────────────────
        # user_feedback 键与 Agent.name 严格对应,其他 Agent 不会误读。
        agent_fb = self.user_feedback.get(agent_name, "").strip()
        if agent_fb:
            parts.append(
                f"# 🗣️ 用户对你上一版本产物的反馈(必须据此改进)\n"
                f"{agent_fb}\n\n"
                f"请仔细阅读以上反馈,确保本次输出完整回应每一条意见,不要遗漏。"
            )

        # ── QA 修复轮次:失败项清单 ──────────────────────────────────────
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

        return "\n".join(parts)