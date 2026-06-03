"""
Orchestrator:串联所有 Agent,实现端到端流水线。

流水线:PM → Architect → Backend → Frontend → DevOps → QA
关键节点支持人工介入(HUMAN_IN_LOOP)。
"""
import json
from rich.console import Console
from rich.prompt import Confirm
from rich.panel import Panel
from rich.syntax import Syntax

from llm_client import LLMClient
from shared_context import SharedContext
from config import Config
from runner import launch_project, npm_available
from agents import (
    ProductManagerAgent,
    ArchitectAgent,
    BackendAgent,
    FrontendAgent,
    DevOpsAgent,
    QAAgent,
)

console = Console()

# QA 修复循环上限:第 1 轮是初始生成后的检查,最多再修复 (MAX_QA_ROUNDS-1) 次
MAX_QA_ROUNDS = 3


def _human_review(stage: str, payload: dict) -> bool:
    """关键决策点的人工介入。返回 True 表示继续,False 表示中止"""
    if not Config.HUMAN_IN_LOOP:
        return True
    console.print(Panel.fit(f"[bold yellow]🧑‍💼 人工审核: {stage}[/]"))
    console.print(Syntax(json.dumps(payload, ensure_ascii=False, indent=2), "json"))
    return Confirm.ask(f"是否对 [{stage}] 的产出满意,继续下一步?", default=True)


def run_pipeline(requirement: str) -> SharedContext:
    """完整流水线"""
    console.print(Panel.fit(
        f"[bold green]🚀 启动全栈 Agent 团队[/]\n[dim]需求: {requirement}[/]",
        title="Agent Team Pipeline"
    ))

    Config.validate()
    llm = LLMClient()
    ctx = SharedContext(requirement=requirement, output_dir=Config.OUTPUT_DIR)

    # ===== Step 1: 产品经理 =====
    ProductManagerAgent(llm).run(ctx)
    if not _human_review("PRD", ctx.prd):
        raise SystemExit("用户中止于 PRD 环节")

    # ===== Step 2: 架构师 =====
    ArchitectAgent(llm).run(ctx)
    if not _human_review("Architecture", ctx.architecture):
        raise SystemExit("用户中止于架构环节")

    # ===== Step 3: 后端 =====
    BackendAgent(llm).run(ctx)

    # ===== Step 4: 前端 =====
    FrontendAgent(llm).run(ctx)

    # ===== Step 5: DevOps =====
    DevOpsAgent(llm).run(ctx)

    # ===== Step 6: QA 检查 + 自动修复循环(最多 MAX_QA_ROUNDS 轮) =====
    for round_num in range(1, MAX_QA_ROUNDS + 1):
        # 把当前所有文件落盘(QA 的语法检查依赖磁盘文件)
        written = ctx.write_project_files()
        console.print(
            f"\n  [green]第 {round_num} 轮写入 {len(written)} 个文件到[/] [bold]{ctx.project_dir}[/]"
        )

        console.rule(f"[bold cyan]🔍 QA 第 {round_num}/{MAX_QA_ROUNDS} 轮")
        QAAgent(llm).run(ctx)

        if ctx.qa_report.get("all_passed"):
            console.print("[bold green]✅ 全部检查通过,提前退出修复循环[/]")
            break

        if round_num >= MAX_QA_ROUNDS:
            console.print(
                f"[bold yellow]⚠️  已达最大修复轮次 ({MAX_QA_ROUNDS}),停止自动修复[/]"
            )
            break

        # 根据失败项决定重跑哪些 Agent
        failed_agents = _get_failed_agents(ctx.qa_report)
        if not failed_agents:
            console.print("[yellow]无法将失败项映射到具体 Agent,跳过自动修复[/]")
            break

        console.print(
            f"\n[bold yellow]⚡ 触发自动修复 (第 {round_num}/{MAX_QA_ROUNDS - 1} 次修复): "
            f"重跑 → {', '.join(sorted(failed_agents))}[/]\n"
        )

        # 把失败列表存入 ctx,summary_for() 会把它注入到 Agent 的 prompt 中
        ctx.qa_failures = [c for c in ctx.qa_report.get("checks", []) if not c.get("passed")]

        if "Backend" in failed_agents:
            BackendAgent(llm).run(ctx)
        if "Frontend" in failed_agents:
            FrontendAgent(llm).run(ctx)
        if "DevOps" in failed_agents:
            DevOpsAgent(llm).run(ctx)

        # 下一轮 QA 开始前清空,防止过期数据污染后续正常轮次
        ctx.qa_failures = []

    # ===== 保存历史 =====
    ctx.save_history()

    # ===== 最终汇报 =====
    _print_final_report(ctx)

    # ===== 自动启动(可选)=====
    # 仅在 QA 全通过且开启 AUTO_RUN(--run)时自动 npm install + npm start。
    # 没通过就不自动跑,避免拿一个跑不起来的项目去启动。
    if (ctx.qa_report or {}).get("all_passed") and Config.AUTO_RUN:
        launch_project(ctx.project_dir, port=Config.RUN_PORT)

    return ctx


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
            # 根据缺失文件名推断是后端还是前端的锅
            if any(f in detail for f in ("server.js", "db.js", "package.json")):
                agents.add("Backend")
            if any(f in detail for f in ("index.html", "app.js", "styles.css")):
                agents.add("Frontend")
            if not agents:  # 实在判断不了就全重跑
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
            # 启动失败/静态缺失/写库报错基本都是后端的锅
            agents.add("Backend")

        elif name == "工程化文件齐全":
            agents.add("DevOps")

    return agents


def _print_final_report(ctx: SharedContext):
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
                f"\n[dim]提示:下次加 [bold]--run[/](或设 AUTO_RUN=true)即可生成后自动安装并启动。[/]"
            )
    else:
        console.print(f"\n[yellow]部分检查未通过,请查看 QA 报告。可手动修复后再 npm start。[/]")