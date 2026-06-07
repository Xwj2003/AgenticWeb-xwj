"""
Web UI 后端 API (改进版):
- 更好地集成现有 orchestrator
- 支持实时日志推送
- 完整的人工审核流程支持
"""
import json
import threading
import queue
import time
import uuid
from typing import Optional, Dict, Any
from flask import Flask, request, jsonify, Response
from io import StringIO
import sys

from config import Config
from shared_context import SharedContext
from llm_client import LLMClient
from agents import (
    ProductManagerAgent,
    ArchitectAgent,
    BackendAgent,
    FrontendAgent,
    DevOpsAgent,
    QAAgent,
)
from human_review import ReviewAction, review_prd, review_architecture, review_qa
from runner import launch_project

app = Flask(__name__)


# ─────────────────────────────────────────────────────────────────
# 全局状态管理
# ─────────────────────────────────────────────────────────────────

class LogCapture:
    """捕获所有日志,推送给前端。"""

    def __init__(self):
        self.logs = []
        self.lock = threading.Lock()

    def append(self, level: str, stage: str, message: str):
        with self.lock:
            entry = {
                "timestamp": time.time(),
                "level": level,
                "stage": stage,
                "message": message,
            }
            self.logs.append(entry)

    def get_recent(self, n: int = 50) -> list:
        with self.lock:
            return list(self.logs[-n:])


class PipelineState:
    def __init__(self):
        self.requirement = ""
        self.status = "idle"  # idle / running / waiting_review / completed / error
        self.current_stage = ""
        self.error = ""
        self.result = None
        self.review_data = None  # 待审核的数据
        self.review_type = None  # "prd" / "architecture" / "qa"
        self.review_regen_count = 0
        self.max_regen = 3
        self.logs = LogCapture()


# 全局变量
state = PipelineState()
review_feedback_queue = queue.Queue()
MAX_QA_ROUNDS = 3


# ─────────────────────────────────────────────────────────────────
# API 端点
# ─────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    """提供前端 HTML。"""
    with open("web_ui.html", "r", encoding="utf-8") as f:
        return f.read(), 200, {"Content-Type": "text/html"}


@app.route("/api/status", methods=["GET"])
def get_status():
    """获取当前流水线状态。"""
    return jsonify({
        "status": state.status,
        "requirement": state.requirement,
        "current_stage": state.current_stage,
        "logs": state.logs.get_recent(50),
        "error": state.error,
        "review_pending": state.status == "waiting_review",
        "review_type": state.review_type,
        "review_data": state.review_data,
    })


@app.route("/api/start", methods=["POST"])
def start_pipeline():
    """启动流水线。"""
    global state

    if state.status in ("running", "waiting_review"):
        return jsonify({"error": "流水线正在运行"}), 400

    data = request.json or {}
    requirement = data.get("requirement", "").strip()
    interactive = data.get("interactive", False)

    if not requirement:
        return jsonify({"error": "需求不能为空"}), 400

    # 重置状态
    state = PipelineState()
    state.requirement = requirement
    state.status = "running"
    Config.HUMAN_IN_LOOP = interactive

    # 在后台线程运行
    thread = threading.Thread(target=_run_pipeline_bg)
    thread.daemon = True
    thread.start()

    return jsonify({"message": "流水线已启动", "requirement": requirement})


@app.route("/api/logs", methods=["GET"])
def get_logs():
    """Server-Sent Events:实时推送日志。"""

    def log_stream():
        last_count = 0
        while state.status in ("running", "waiting_review"):
            current_logs = state.logs.get_recent()
            if len(current_logs) > last_count:
                new_logs = current_logs[last_count:]
                for log in new_logs:
                    yield f"data: {json.dumps(log)}\n\n"
                last_count = len(current_logs)
            time.sleep(0.2)

        # 流结束时发送最终状态
        yield f"data: {json.dumps({'type': 'final', 'status': state.status})}\n\n"

    return Response(log_stream(), mimetype="text/event-stream")


@app.route("/api/feedback", methods=["POST"])
def submit_feedback():
    """提交人工审核反馈。"""
    if state.status != "waiting_review":
        return jsonify({"error": "当前不在审核状态"}), 400

    data = request.json or {}
    action = data.get("action", "approve")
    feedback = data.get("feedback", "").strip()

    # 通过队列传给流水线线程
    review_feedback_queue.put({
        "action": action,
        "feedback": feedback,
    })

    state.status = "running"
    state.review_type = None
    state.review_data = None

    return jsonify({"message": "反馈已提交,流水线继续运行"})


@app.route("/api/result", methods=["GET"])
def get_result():
    """获取最终结果。"""
    if state.status not in ("completed", "error"):
        return jsonify({"error": "流水线未完成"}), 400

    return jsonify({
        "status": state.status,
        "error": state.error,
        "result": state.result,
    })


# ─────────────────────────────────────────────────────────────────
# 后台流水线执行
# ─────────────────────────────────────────────────────────────────

def _run_pipeline_bg():
    """在后台线程中运行完整的流水线。"""
    global state

    try:
        Config.validate()
        llm = LLMClient()
        ctx = SharedContext(
            requirement=state.requirement,
            output_dir=Config.OUTPUT_DIR
        )

        _log("info", "Pipeline", "启动全栈 Agent 团队")

        # ════════════════════════════════════════════════════════════
        # Step 1: 产品经理 + HITL
        # ════════════════════════════════════════════════════════════
        for regen in range(1, MAX_REGEN := 3 + 1):
            if regen > 1:
                _log("info", "ProductManager", f"重生成 (第 {regen}/{MAX_REGEN} 次)")

            ProductManagerAgent(llm).run(ctx)

            if not Config.HUMAN_IN_LOOP:
                break

            # 等待人工审核
            feedback = _wait_for_review("prd", ctx.prd)

            if feedback["action"] == "abort":
                raise SystemExit("用户中止于 PRD 环节")

            if feedback["action"] == "approve":
                _log("info", "ProductManager", f"用户批准 PRD")
                break

            if regen == MAX_REGEN:
                _log("warning", "ProductManager", f"已达最大重生成次数,以最新版本继续")
                break

            # 反馈重生成
            ctx.user_feedback["ProductManager"] = feedback["feedback"]
            _log("info", "ProductManager", f"携带用户反馈重新生成...")

        # ════════════════════════════════════════════════════════════
        # Step 2: 架构师 + HITL
        # ════════════════════════════════════════════════════════════
        for regen in range(1, MAX_REGEN + 1):
            if regen > 1:
                _log("info", "Architect", f"重生成 (第 {regen}/{MAX_REGEN} 次)")

            ArchitectAgent(llm).run(ctx)

            if not Config.HUMAN_IN_LOOP:
                break

            feedback = _wait_for_review("architecture", ctx.architecture)

            if feedback["action"] == "abort":
                raise SystemExit("用户中止于架构环节")

            if feedback["action"] == "approve":
                _log("info", "Architect", "用户批准架构")
                break

            if regen == MAX_REGEN:
                _log("warning", "Architect", f"已达最大重生成次数,以最新版本继续")
                break

            ctx.user_feedback["Architect"] = feedback["feedback"]
            _log("info", "Architect", f"携带用户反馈重新设计...")

        # ════════════════════════════════════════════════════════════
        # Step 3-5: 后端 / 前端 / DevOps
        # ════════════════════════════════════════════════════════════
        _log("info", "Backend", "开始生成后端代码")
        BackendAgent(llm).run(ctx)

        _log("info", "Frontend", "开始生成前端代码")
        FrontendAgent(llm).run(ctx)

        _log("info", "DevOps", "开始生成部署文件")
        DevOpsAgent(llm).run(ctx)

        # ════════════════════════════════════════════════════════════
        # Step 6: QA 检查 + 修复循环
        # ════════════════════════════════════════════════════════════
        for round_num in range(1, MAX_QA_ROUNDS + 1):
            written = ctx.write_project_files()
            _log("success", "Pipeline", f"第 {round_num} 轮:写入 {len(written)} 个文件")

            _log("info", "QA", f"开始第 {round_num}/{MAX_QA_ROUNDS} 轮检查")
            QAAgent(llm).run(ctx)

            if Config.HUMAN_IN_LOOP and round_num > 0:
                feedback = _wait_for_review("qa", ctx.qa_report)
                if feedback["action"] == "abort":
                    raise SystemExit("用户中止于 QA 环节")
                if feedback["action"] == "approve":
                    ctx.qa_report["all_passed"] = True
                    _log("success", "QA", "用户批准,流水线完成")
                    break

            if ctx.qa_report.get("all_passed"):
                _log("success", "QA", "全部检查通过!")
                break

            if round_num >= MAX_QA_ROUNDS:
                _log("warning", "QA", f"已达最大修复轮次")
                break

            # 自动修复:重跑失败的 Agent
            _log("info", "QA", f"触发自动修复,重跑相关 Agent...")
            ctx.qa_failures = [c for c in ctx.qa_report.get("checks", []) if not c.get("passed")]

            # 简单策略:全部重跑
            BackendAgent(llm).run(ctx)
            FrontendAgent(llm).run(ctx)
            DevOpsAgent(llm).run(ctx)

            ctx.qa_failures = []

        # ════════════════════════════════════════════════════════════
        # 收尾
        # ════════════════════════════════════════════════════════════
        ctx.save_history()

        state.status = "completed"
        state.result = {
            "project_dir": ctx.project_dir,
            "artifacts_dir": ctx.artifacts_dir,
            "qa_report": ctx.qa_report,
        }

        _log("success", "Pipeline", "流水线完成!")

        # 自动启动(可选)
        if (ctx.qa_report or {}).get("all_passed") and Config.AUTO_RUN:
            _log("info", "Pipeline", "自动启动服务...")
            launch_project(ctx.project_dir, port=Config.RUN_PORT)

    except SystemExit as e:
        state.status = "completed"
        state.error = str(e)
        _log("error", "Pipeline", str(e))

    except Exception as e:
        state.status = "error"
        state.error = str(e)
        _log("error", "Pipeline", str(e))
        import traceback
        traceback.print_exc()


def _wait_for_review(review_type: str, review_data: Any) -> dict:
    """
    暂停流水线,等待前端提交的审核反馈。
    """
    global state

    state.status = "waiting_review"
    state.review_type = review_type
    state.review_data = review_data

    _log("info", "Review", f"等待人工审核 ({review_type})...")

    # 阻塞等待反馈
    while True:
        try:
            feedback = review_feedback_queue.get(timeout=1)
            return feedback
        except queue.Empty:
            # 定期检查状态(防止死等)
            if state.status != "waiting_review":
                # 如果外部改了状态,就返回默认批准
                return {"action": "approve", "feedback": ""}
            continue


def _log(level: str, stage: str, message: str):
    """记录日志,推送给前端。"""
    state.logs.append(level, stage, message)
    state.current_stage = stage

    # 控制台也输出
    prefix = {
        "info": "ℹ️",
        "success": "✅",
        "warning": "⚠️",
        "error": "❌",
    }.get(level, "•")
    print(f"[{stage}] {prefix} {message}")


# ─────────────────────────────────────────────────────────────────
# 启动
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os

    # 确保 web_ui.html 存在
    if not os.path.exists("web_ui.html"):
        print("❌ 错误:找不到 web_ui.html")
        print("请确保 web_ui.html 与 api.py 在同一目录")
        sys.exit(1)

    print("🚀 启动 Web UI 服务器...")
    print("📱 访问: http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)