"""
human_review.py — 人工介入(Human-in-the-Loop)模块。

在三个关键决策节点暂停流水线,向用户呈现结构化产物,并等待决策:
  • PRD 审核:Approve / 直接编辑功能列表 / 提供反馈重生成 / Abort
  • 架构审核:Approve / 提供反馈重设计 / Abort
  • QA 审核 :强制通过 / 继续自动修复 / Abort

调用方(orchestrator.py)负责:
  - 检查 Config.HUMAN_IN_LOOP,决定是否调用本模块。
  - 根据返回的 ReviewResult 决定下一步行为(循环重生成 / 继续 / 中止)。
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table

console = Console()

# ─────────────────────────────────────────────────────────────────
# 数据类型
# ─────────────────────────────────────────────────────────────────

class ReviewAction(Enum):
    APPROVE  = "approve"   # 通过,继续流水线
    EDIT     = "edit"      # 原地编辑后通过(仅 PRD)
    FEEDBACK = "feedback"  # 带反馈重新生成当前 Agent 产物
    ABORT    = "abort"     # 中止整个流水线


@dataclass
class ReviewResult:
    action: ReviewAction
    feedback: str = ""                  # FEEDBACK 时携带的自然语言修改意见
    edited_data: Optional[dict] = None  # EDIT 时携带修改后的完整数据

    @property
    def approved(self) -> bool:
        """APPROVE 或 EDIT 均视为通过,可继续流水线下一步。"""
        return self.action in (ReviewAction.APPROVE, ReviewAction.EDIT)

    @property
    def needs_regen(self) -> bool:
        """是否需要携带反馈重新生成当前 Agent 产物。"""
        return self.action == ReviewAction.FEEDBACK


# ─────────────────────────────────────────────────────────────────
# 通用 UI 工具
# ─────────────────────────────────────────────────────────────────

def _section(title: str) -> None:
    """打印二级节标题。"""
    console.print(f"\n  [bold dim]▸ {title}[/]")


def _menu(options: list[tuple[str, str]]) -> str:
    """
    显示带编号的选项菜单,返回用户选择的 key。
    options: [(key, label_rich_text), ...]
    """
    console.print()
    for key, label in options:
        console.print(f"    [bold yellow][{key}][/]  {label}")
    console.print()
    valid_keys = [k for k, _ in options]
    while True:
        choice = Prompt.ask("  请选择", choices=valid_keys, show_choices=False)
        if choice in valid_keys:
            return choice


def _collect_feedback(hint: str = "请输入你的反馈") -> str:
    """
    多行反馈输入:
      - 每行 Enter 换行
      - 空行结束输入(需先有至少一行内容)
      - Ctrl+C / Ctrl+D → 放弃反馈,返回空字符串
    """
    console.print(f"\n  [dim italic]{hint}[/]")
    console.print("  [dim](空行结束输入;Ctrl+C 取消反馈)[/]\n")
    lines: list[str] = []
    try:
        while True:
            try:
                line = input("  ‣ ")
            except EOFError:
                break
            if line == "" and lines:
                break           # 有内容后遇到空行 → 结束
            if line == "" and not lines:
                continue        # 第一行是空行 → 忽略,等用户真正开始输入
            lines.append(line)
    except KeyboardInterrupt:
        console.print("\n  [dim]反馈已取消[/]")
        return ""
    return "\n".join(lines).strip()


def _view_raw_json(data: dict) -> None:
    """在终端打印完整 JSON(供高级用户核查原始产物)。"""
    console.print(
        Panel(
            Syntax(json.dumps(data, ensure_ascii=False, indent=2), "json", theme="monokai"),
            title="[dim]原始 JSON[/]",
            border_style="dim",
        )
    )


# ─────────────────────────────────────────────────────────────────
# PRD 审核
# ─────────────────────────────────────────────────────────────────

def _render_prd(prd: dict) -> None:
    """将 PRD JSON 渲染为可读的终端界面。"""
    name = prd.get("project_name", "未命名")
    desc = prd.get("description", "")
    console.print(
        Panel.fit(
            f"[bold white]{name}[/]  —  {desc}",
            title="[bold green]📋 PRD 预览",
            border_style="green",
        )
    )

    # 核心功能
    features = prd.get("core_features", [])
    _section(f"核心功能 ({len(features)} 项)")
    if features:
        for i, feat in enumerate(features, 1):
            console.print(f"    [green]{i}.[/] {feat}")
    else:
        console.print("    [dim](无)[/]")

    # 用户故事
    stories = prd.get("user_stories", [])
    if stories:
        _section("用户故事")
        t = Table(box=box.SIMPLE, show_header=True, header_style="bold dim", padding=(0, 2))
        t.add_column("角色", style="cyan", width=10)
        t.add_column("行为", style="white")
        t.add_column("目的", style="dim")
        for s in stories:
            t.add_row(s.get("role", ""), s.get("action", ""), s.get("benefit", ""))
        console.print(t)

    # 不做的事
    oos = prd.get("out_of_scope", [])
    if oos:
        _section("明确不做")
        for item in oos:
            console.print(f"    [red]✗[/] {item}")

    # UI 要求
    ui = prd.get("ui_requirements", {})
    _section("UI 要求")
    console.print(
        f"    深色模式 {'[green]✅[/]' if ui.get('dark_mode') else '[dim]❌[/]'}  │  "
        f"响应式 {'[green]✅[/]' if ui.get('responsive') else '[dim]❌[/]'}  │  "
        f"页面: {', '.join(ui.get('key_pages', []))}"
    )


def _edit_prd_interactively(prd: dict) -> dict:
    """
    交互式编辑 PRD 核心功能列表。
    支持:添加功能 / 删除功能 / 完成编辑。
    返回修改后的 PRD 深拷贝。
    """
    prd = copy.deepcopy(prd)
    features: list[str] = prd.get("core_features", [])

    console.print("\n  [bold]✏️  编辑核心功能列表[/]")
    console.print(
        "  指令: [yellow]a[/] 添加 | [yellow]d <编号>[/] 删除 | "
        "[yellow]json[/] 查看原始 JSON | [yellow]done[/] 完成\n"
    )

    while True:
        console.print("  [dim]当前功能:[/]")
        if features:
            for i, f in enumerate(features, 1):
                console.print(f"    [green]{i}.[/] {f}")
        else:
            console.print("    [dim](列表为空)[/]")
        console.print()

        cmd = Prompt.ask("  操作").strip()

        if not cmd or cmd.lower() == "done":
            break
        elif cmd.lower() == "a":
            new_feat = Prompt.ask("  新功能描述").strip()
            if new_feat:
                features.append(new_feat)
                console.print(f"  [green]✓ 已添加:[/] {new_feat}")
        elif cmd.lower().startswith("d "):
            try:
                idx = int(cmd.split()[1]) - 1
                if 0 <= idx < len(features):
                    removed = features.pop(idx)
                    console.print(f"  [red]✓ 已删除:[/] {removed}")
                else:
                    console.print("  [red]编号超出范围,请重试[/]")
            except (ValueError, IndexError):
                console.print("  [red]格式错误,示例: d 2[/]")
        elif cmd.lower() == "json":
            _view_raw_json(prd)
        else:
            console.print(
                "  [dim]未识别指令。可用: a | d <编号> | json | done[/]"
            )

    prd["core_features"] = features
    return prd


def review_prd(prd: dict) -> ReviewResult:
    """
    PRD 审核入口,供 orchestrator 在 PM 产出后调用。

    决策选项:
      1 - 批准 → 进入架构设计
      2 - 编辑功能列表 → 直接增删核心功能后继续
      3 - 提供反馈 → PM 携带反馈重新生成(触发重生成循环)
      v - 查看原始 JSON(不做决策,看完再选)
      4 - 中止 → 终止整个流程
    """
    console.rule("[bold yellow]👤 人工审核节点 — PRD")
    _render_prd(prd)

    while True:
        choice = _menu([
            ("1", "[green]批准[/] — 进入架构设计"),
            ("2", "[yellow]编辑功能列表[/] — 直接增删核心功能"),
            ("3", "[blue]提供反馈[/] — 让 PM 重新生成"),
            ("v", "[dim]查看原始 JSON[/]"),
            ("4", "[red]中止[/] — 终止本次生成"),
        ])

        if choice == "1":
            console.print("\n  [green]✓ PRD 已批准,进入架构设计[/]")
            return ReviewResult(ReviewAction.APPROVE)

        elif choice == "2":
            edited = _edit_prd_interactively(prd)
            console.print("\n  [green]✓ 功能列表已更新,继续架构设计[/]")
            return ReviewResult(ReviewAction.EDIT, edited_data=edited)

        elif choice == "3":
            fb = _collect_feedback(
                "告诉 PM 哪里需要改 (如:加某功能、删某功能、改项目描述)"
            )
            if not fb:
                console.print("  [dim]反馈为空,视为批准[/]")
                return ReviewResult(ReviewAction.APPROVE)
            return ReviewResult(ReviewAction.FEEDBACK, feedback=fb)

        elif choice == "v":
            _view_raw_json(prd)
            # 看完后回到菜单,不退出循环

        else:  # "4"
            console.print("\n  [red]流水线已中止[/]")
            return ReviewResult(ReviewAction.ABORT)


# ─────────────────────────────────────────────────────────────────
# 架构方案审核
# ─────────────────────────────────────────────────────────────────

def _render_architecture(arch: dict) -> None:
    """将架构 JSON 渲染为终端可读格式。"""
    ts = arch.get("tech_stack", {})
    console.print(
        Panel.fit(
            f"[bold]后端[/] {ts.get('backend_language','')} + {ts.get('backend_framework','')}  │  "
            f"[bold]存储[/] {ts.get('storage','')}  │  "
            f"[bold]前端[/] {ts.get('frontend','')}",
            title="[bold green]🏗️  架构方案预览",
            border_style="green",
        )
    )

    # 数据模型
    models = arch.get("data_models", [])
    _section(f"数据模型 ({len(models)} 个集合)")
    for model in models:
        console.print(f"\n    [bold cyan]{model['collection']}[/]")
        t = Table(box=box.SIMPLE, show_header=True, header_style="bold dim", padding=(0, 1))
        t.add_column("字段", style="white", width=16)
        t.add_column("类型", style="yellow", width=10)
        t.add_column("备注", style="dim")
        for fld in model.get("fields", []):
            t.add_row(fld.get("name", ""), fld.get("type", ""), fld.get("note", ""))
        console.print(t)

    # API 契约
    endpoints = arch.get("api_contract", [])
    _section(f"API 契约 ({len(endpoints)} 个接口)")
    _method_colors = {
        "GET": "green", "POST": "blue",
        "PUT": "yellow", "PATCH": "yellow", "DELETE": "red",
    }
    t = Table(box=box.SIMPLE, show_header=True, header_style="bold", padding=(0, 1))
    t.add_column("#", style="dim", width=3)
    t.add_column("Method", width=8)
    t.add_column("Path", style="cyan")
    t.add_column("描述", style="white")
    for i, ep in enumerate(endpoints, 1):
        method = ep.get("method", "")
        color = _method_colors.get(method, "white")
        t.add_row(str(i), f"[{color}]{method}[/]", ep.get("path", ""), ep.get("description", ""))
    console.print(t)

    # 文件结构
    _section("文件结构")
    for cat, files in arch.get("file_layout", {}).items():
        console.print(f"    [bold dim]{cat}:[/] {', '.join(files)}")

    # 启动命令
    cmd = arch.get("startup_command", "")
    if cmd:
        _section("启动命令")
        console.print(f"    [dim]$ {cmd}[/]")


def review_architecture(arch: dict) -> ReviewResult:
    """
    架构方案审核入口,供 orchestrator 在 Architect 产出后调用。

    决策选项:
      1 - 批准 → 开始生成代码
      2 - 提供反馈 → 架构师携带反馈重新设计
      v - 查看原始 JSON
      3 - 中止
    """
    console.rule("[bold yellow]👤 人工审核节点 — 技术架构")
    _render_architecture(arch)

    while True:
        choice = _menu([
            ("1", "[green]批准[/] — 开始生成代码"),
            ("2", "[blue]提供反馈[/] — 让架构师重新设计"),
            ("v", "[dim]查看原始 JSON[/]"),
            ("3", "[red]中止[/] — 终止本次生成"),
        ])

        if choice == "1":
            console.print("\n  [green]✓ 架构方案已批准,开始生成代码[/]")
            return ReviewResult(ReviewAction.APPROVE)

        elif choice == "2":
            fb = _collect_feedback(
                "告诉架构师哪里需要改 "
                "(如:增加某 API、修改字段、拆分接口、调整文件结构)"
            )
            if not fb:
                console.print("  [dim]反馈为空,视为批准[/]")
                return ReviewResult(ReviewAction.APPROVE)
            return ReviewResult(ReviewAction.FEEDBACK, feedback=fb)

        elif choice == "v":
            _view_raw_json(arch)

        else:  # "3"
            console.print("\n  [red]流水线已中止[/]")
            return ReviewResult(ReviewAction.ABORT)


# ─────────────────────────────────────────────────────────────────
# QA 报告审核
# ─────────────────────────────────────────────────────────────────

def _render_qa_report(report: dict) -> None:
    """将 QA 报告渲染为带颜色的终端表格。"""
    all_pass = report.get("all_passed", False)
    summary = report.get("summary", "")
    color = "green" if all_pass else "red"
    icon = "✅" if all_pass else "❌"

    console.print(
        Panel.fit(
            f"{icon}  {summary}",
            title=f"[bold {color}]🔍 QA 报告",
            border_style=color,
        )
    )

    checks = report.get("checks", [])
    if not checks:
        return

    t = Table(box=box.SIMPLE, show_header=True, header_style="bold", padding=(0, 1))
    t.add_column("", width=4)
    t.add_column("检查项", style="white", min_width=26)
    t.add_column("详情", style="dim", max_width=56)

    for check in checks:
        passed = check.get("passed", False)
        status = "[green]✅[/]" if passed else "[red]❌[/]"
        detail = check.get("detail", "")
        if len(detail) > 100:
            detail = detail[:97] + "…"
        t.add_row(status, check.get("name", ""), detail)

    console.print(t)


def review_qa(report: dict, round_num: int, max_rounds: int) -> ReviewResult:
    """
    QA 报告审核入口。
    在 QA Agent 运行完毕、存在失败项(或全通过)时调用。

    全部通过时:
      1 - 确认完成
      0 - 中止(极少见,但支持)

    有失败项时:
      1 - 强制通过(人工覆盖 QA 结果,以当前状态交付)
      2 - 继续自动修复(若还有修复轮次)
      0 - 中止

    force-通过会就地修改 report["all_passed"] = True,
    orchestrator 通过 result.approved 检测到这一变化并退出 QA 循环。
    """
    console.rule(
        f"[bold yellow]👤 人工审核节点 — QA 报告  (第 {round_num}/{max_rounds} 轮)"
    )
    _render_qa_report(report)

    all_pass = report.get("all_passed", False)
    remaining = max_rounds - round_num  # 还剩几轮可修复

    if all_pass:
        choice = _menu([
            ("1", "[green]✅ 确认完成[/] — 交付项目"),
            ("0", "[red]中止[/]"),
        ])
        if choice == "1":
            return ReviewResult(ReviewAction.APPROVE)
        return ReviewResult(ReviewAction.ABORT)

    # 有失败项 ——
    options: list[tuple[str, str]] = [
        ("1", "[yellow]强制通过[/] — 忽略失败项,以当前状态交付"),
    ]
    if remaining > 0:
        options.append(
            ("2", f"[green]继续自动修复[/] — 还剩 {remaining} 轮修复机会")
        )
    options.append(("0", "[red]中止[/]"))

    choice = _menu(options)

    if choice == "1":
        # 人工强制通过:将标记写回 report(orchestrator 据此 break 循环)
        report["all_passed"] = True
        report["summary"] = (report.get("summary") or "") + "  [人工强制通过]"
        console.print("\n  [yellow]⚠️  已人工强制通过,跳过剩余修复[/]")
        return ReviewResult(ReviewAction.APPROVE)

    elif choice == "2" and remaining > 0:
        console.print("\n  [blue]继续自动修复…[/]")
        return ReviewResult(ReviewAction.FEEDBACK)  # orchestrator 继续修复循环

    else:
        console.print("\n  [red]流水线已中止[/]")
        return ReviewResult(ReviewAction.ABORT)
