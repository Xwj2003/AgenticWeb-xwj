"""
Orchestrator:串联所有 Agent,实现端到端流水线。

流水线:PM → Architect → Backend → Frontend → DevOps → QA
v2.1 HITL 升级:
  - PRD、架构两个节点由原来的"满意 / 中止"升级为完整的审核-重生成循环。
  - QA 节点新增人工审核:可强制通过、继续自动修复或中止。
  - 重生成上限由 MAX_REGEN 控制(默认 3 次);QA 修复循环上限沿用 MAX_QA_ROUNDS。
  - 所有 HITL 逻辑集中在 human_review 模块,orchestrator 只负责调度。
"""
from rich.console import Console
from rich.panel import Panel

from llm_client import LLMClient
from shared_context import SharedContext
from config import Config
from runner import launch_project
from human_review import ReviewAction, review_prd, review_architecture, review_qa
from agents import (
    ProductManagerAgent,
    ArchitectAgent,
    BackendAgent,
    FrontendAgent,
    DevOpsAgent,
    QAAgent,
)

console = Console()

# QA 修复循环上限(第 1 轮是初始生成后的检查,最多再修复 MAX_QA_ROUNDS-1 次)
MAX_QA_ROUNDS = 3

# HITL 重生成上限:PRD / Architect 最多被重新生成多少次
MAX_REGEN = 3


# ─────────────────────────────────────────────────────────────────
# 主流水线
# ─────────────────────────────────────────────────────────────────

def run_pipeline(requirement: str) -> SharedContext:
    """端到端流水线:需求 → 可运行项目。"""
    console.print(Panel.fit(
        f"[bold green]🚀 启动全栈 Agent 团队[/]\n[dim]需求: {requirement}[/]",
        title="Agent Team Pipeline"
    ))

    Config.validate()
    llm = LLMClient()
    ctx = SharedContext(requirement=requirement, output_dir=Config.OUTPUT_DIR)

    # ================================================================
    # Step 1: 产品经理 + HITL 审核-重生成循环
    # ================================================================
    # 循环逻辑:
    #   - HUMAN_IN_LOOP=False → 只跑一次,直接继续
    #   - APPROVE / EDIT      → 通过,退出循环
    #   - FEEDBACK            → 存反馈,重跑(最多 MAX_REGEN 次)
    #   - ABORT               → 中止整个流水线
    # ================================================================
    for regen in range(1, MAX_REGEN + 1):
        if regen > 1:
            console.rule(f"[dim]PM 重生成(第 {regen}/{MAX_REGEN} 次)[/]")

        ProductManagerAgent(llm).run(ctx)

        if not Config.HUMAN_IN_LOOP:
            break

        result = review_prd(ctx.prd)

        if result.action == ReviewAction.ABORT:
            raise SystemExit("用户中止于 PRD 环节")

        if result.action == ReviewAction.EDIT:
            # 用户直接编辑了功能列表,将修改后的 PRD 写回黑板
            ctx.prd = result.edited_data
            _log_regen_summary("PRD", regen, "用户直接编辑功能列表后通过")
            break

        if result.approved:
            _log_regen_summary("PRD", regen, "用户批准")
            break

        # FEEDBACK:还有重生成机会就继续,否则用最新版本
        if regen == MAX_REGEN:
            console.print(f"[dim]PRD 已达最大重生成次数 ({MAX_REGEN}),以最新版本继续。[/]")
            break

        ctx.user_feedback["ProductManager"] = result.feedback
        console.print(
            f"\n[yellow]⟳  携带用户反馈重新生成 PRD "
            f"(第 {regen + 1}/{MAX_REGEN} 次)…[/]\n"
        )

    # ================================================================
    # Step 2: 架构师 + HITL 审核-重生成循环
    # ================================================================
    for regen in range(1, MAX_REGEN + 1):
        if regen > 1:
            console.rule(f"[dim]Architect 重生成(第 {regen}/{MAX_REGEN} 次)[/]")

        ArchitectAgent(llm).run(ctx)

        if not Config.HUMAN_IN_LOOP:
            break

        result = review_architecture(ctx.architecture)

        if result.action == ReviewAction.ABORT:
            raise SystemExit("用户中止于架构环节")

        if result.approved:
            _log_regen_summary("Architecture", regen, "用户批准")
            break

        if regen == MAX_REGEN:
            console.print(f"[dim]Architecture 已达最大重生成次数 ({MAX_REGEN}),以最新版本继续。[/]")
            break

        ctx.user_feedback["Architect"] = result.feedback
        console.print(
            f"\n[yellow]⟳  携带用户反馈重新设计架构 "
            f"(第 {regen + 1}/{MAX_REGEN} 次)…[/]\n"
        )

    # ================================================================
    # Step 3-5: 后端 / 前端 / DevOps(无人工审核节点,可直接串行)
    # ================================================================
    BackendAgent(llm).run(ctx)
    FrontendAgent(llm).run(ctx)
    DevOpsAgent(llm).run(ctx)

    # ================================================================
    # Step 6: QA 检查 + 自动修复循环 + HITL QA 审核
    #
    # 流程(每轮):
    #   1. 落盘所有文件
    #   2. QA Agent 运行
    #   3. HITL=True  → 调用 review_qa() 让用户决策
    #      HITL=False → 全通过则提前退出;否则继续自动修复
    #   4. 仍有失败且未达上限 → _get_failed_agents() 映射并重跑
    # ================================================================
    for round_num in range(1, MAX_QA_ROUNDS + 1):
        # 落盘(QA 的 node --check 和冒烟测试依赖磁盘文件)
        written = ctx.write_project_files()
        console.print(
            f"\n  [green]第 {round_num} 轮写入 {len(written)} 个文件到[/]"
            f" [bold]{ctx.project_dir}[/]"
        )

        console.rule(f"[bold cyan]🔍 QA 第 {round_num}/{MAX_QA_ROUNDS} 轮")
        QAAgent(llm).run(ctx)

        # ── 决策:继续 / 退出 ──────────────────────────────────────
        if Config.HUMAN_IN_LOOP:
            result = review_qa(ctx.qa_report, round_num, MAX_QA_ROUNDS)

            if result.action == ReviewAction.ABORT:
                raise SystemExit("用户中止于 QA 环节")

            if result.approved:
                # 用户批准(或强制通过),report["all_passed"] 已在 review_qa 中设为 True
                if ctx.qa_report.get("all_passed"):
                    _qa_pass_msg(ctx.qa_report)
                break
        else:
            # 非 HITL:自动判断
            if ctx.qa_report.get("all_passed"):
                console.print("[bold green]✅ 全部检查通过,提前退出修复循环[/]")
                break

        # 达到最大修复轮次
        if round_num >= MAX_QA_ROUNDS:
            console.print(
                f"[bold yellow]⚠️  已达最大修复轮次 ({MAX_QA_ROUNDS}),停止自动修复[/]"
            )
            break

        # ── 自动修复:将失败项映射到具体 Agent 并重跑 ─────────────
        failed_agents = _get_failed_agents(ctx.qa_report)
        if not failed_agents:
            console.print("[yellow]无法将失败项映射到具体 Agent,跳过自动修复[/]")
            break

        console.print(
            f"\n[bold yellow]⚡ 触发自动修复 "
            f"(第 {round_num}/{MAX_QA_ROUNDS - 1} 次修复): "
            f"重跑 → {', '.join(sorted(failed_agents))}[/]\n"
        )

        # 把失败列表存入 ctx,summary_for() 会把它注入到 Agent 的 prompt 中
        ctx.qa_failures = [
            c for c in ctx.qa_report.get("checks", []) if not c.get("passed")
        ]

        if "Backend" in failed_agents:
            BackendAgent(llm).run(ctx)
        if "Frontend" in failed_agents:
            FrontendAgent(llm).run(ctx)
        if "DevOps" in failed_agents:
            DevOpsAgent(llm).run(ctx)

        # 清空,防止过期数据污染后续正常轮次
        ctx.qa_failures = []

    # ================================================================
    # 收尾
    # ================================================================
    ctx.save_history()
    _print_final_report(ctx)

    # 仅在 QA 全通过且开启 AUTO_RUN 时自动启动
    if (ctx.qa_report or {}).get("all_passed") and Config.AUTO_RUN:
        launch_project(ctx.project_dir, port=Config.RUN_PORT)

    return ctx


# ─────────────────────────────────────────────────────────────────
# 内部工具
# ─────────────────────────────────────────────────────────────────

def _log_regen_summary(stage: str, regen: int, reason: str) -> None:
    """打印重生成循环的简要结果日志。"""
    if regen == 1:
        console.print(f"  [dim]{stage}: 首次生成后{reason}[/]")
    else:
        console.print(f"  [dim]{stage}: 经 {regen} 次生成后{reason}[/]")


def _qa_pass_msg(report: dict) -> None:
    """根据 QA 报告类型打印对应的通过消息。"""
    if "[人工强制通过]" in (report.get("summary") or ""):
        console.print("[bold yellow]⚠️  人工强制通过,跳过剩余修复轮次[/]")
    else:
        console.print("[bold green]✅ 全部检查通过[/]")


def _get_failed_agents(qa_report: dict) -> set:
    """
    根据 QA 报告的失败项,推断需要重跑的 Agent 集合。
    返回值是 {'Backend', 'Frontend', 'DevOps'} 的子集。
    """
    agents = set()
    for check in qa_report.get("checks", []):
        if check.get("passed"):
            continue
        name = check["name"]
        detail = check.get("detail", "")

        if name == "架构声明的文件全部生成":
            if any(f in detail for f in ("server.js", "db.js", "package.json")):
                agents.add("Backend")
            if any(f in detail for f in ("index.html", "app.js", "styles.css")):
                agents.add("Frontend")
            if not agents:
                agents.update({"Backend", "Frontend"})

        elif name == "package.json 存在且合法":
            agents.add("Backend")

        elif name == "后端实现了契约里的全部接口":
            agents.add("Backend")

        elif name == "前端只调用契约中已声明的接口":
            agents.add("Frontend")

        elif name == "JS 语法检查 (node --check)":
            if any(f in detail for f in ("server.js", "db.js")):
                agents.add("Backend")
            if any(f in detail for f in ("app.js", "public/app.js")):
                agents.add("Frontend")
            if not agents:
                agents.update({"Backend", "Frontend"})

        elif name == "后端托管前端静态资源 (express.static)":
            agents.add("Backend")

        elif name == "前端实现了契约里全部操作(增删改查)":
            agents.add("Frontend")

        elif name == "index.html 以合法 <!DOCTYPE html> 开头":
            agents.add("Frontend")

        elif name == "运行时冒烟测试 (npm install + 启动 + 打接口)":
            agents.add("Backend")

        elif name == "工程化文件齐全":
            agents.add("DevOps")

    return agents


def _print_final_report(ctx: SharedContext) -> None:
    report = ctx.qa_report or {}
    all_pass = report.get("all_passed", False)
    color = "green" if all_pass else "yellow"
    console.rule(f"[bold {color}]🎉 完成")
    console.print(f"项目目录: [bold]{ctx.project_dir}[/]")
    console.print(f"中间产物: [bold]{ctx.artifacts_dir}[/]")
    console.print(f"QA 报告: {report.get('summary', 'N/A')}")
    if all_pass:
        if Config.AUTO_RUN:
            console.print(f"\n[bold green]✅ QA 通过,即将自动安装依赖并启动服务……[/]")
        else:
            console.print(f"\n[bold green]下一步:[/]")
            console.print(f"  cd {ctx.project_dir}")
            console.print(f"  npm install")
            console.print(f"  npm start")
            console.print(f"  # 然后浏览器打开 http://localhost:{Config.RUN_PORT}")
            console.print(
                f"\n[dim]提示:下次加 [bold]--run[/](或设 AUTO_RUN=true)"
                f"即可生成后自动安装并启动。[/]"
            )
    else:
        console.print(
            f"\n[yellow]部分检查未通过,请查看 QA 报告。"
            f"可手动修复后再 npm start。[/]"
        )