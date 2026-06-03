"""
项目启动器:在 QA 通过后(或用户指定 --run / AUTO_RUN=true 时),
自动执行 npm install + npm start 并打开浏览器,省去手动 cd 进目录敲命令。

跨平台:Windows / macOS / Linux 都可用(npm 在 Windows 上是 npm.cmd,
故统一用 shell=True 调用;命令均为固定字面量,cwd 为受信任的项目目录)。
"""
import os
import shutil
import subprocess
import threading
import webbrowser

from rich.console import Console

console = Console()


def npm_available() -> bool:
    """node 与 npm 是否都在 PATH 中。"""
    return shutil.which("node") is not None and shutil.which("npm") is not None


def launch_project(project_dir: str, port: int = 3000, open_browser: bool = True) -> None:
    """
    安装依赖并前台启动服务,阻塞直到用户 Ctrl+C。

    流程:
      1) npm install(实时输出)
      2) 延迟 2.5s 打开浏览器(给 server 留启动时间)
      3) npm start(前台运行,Ctrl+C 停止)
    """
    if not npm_available():
        console.print(
            "[yellow]未检测到 Node.js / npm,跳过自动启动。\n"
            "请先安装 Node.js,然后手动执行:[/]\n"
            f"  cd {project_dir}\n  npm install\n  npm start"
        )
        return

    url = f"http://localhost:{port}"

    # 1) 安装依赖(阻塞,继承标准输出以便看到进度)
    console.print(f"\n[bold cyan]📦 安装依赖[/]  [dim]({project_dir})[/]")
    try:
        install = subprocess.run(
            "npm install --no-audit --no-fund",
            cwd=project_dir,
            shell=True,
        )
    except KeyboardInterrupt:
        console.print("\n[dim]已取消。[/]")
        return
    if install.returncode != 0:
        console.print(
            "[red]npm install 失败,已中止自动启动。"
            f"可进入 {project_dir} 手动排查。[/]"
        )
        return

    # 2) 延迟打开浏览器(server 起来之前先排队)
    if open_browser:
        threading.Timer(2.5, lambda: webbrowser.open(url)).start()

    # 3) 前台启动服务(阻塞到 Ctrl+C)
    console.print(
        f"\n[bold green]🚀 启动服务[/]  →  [bold]{url}[/]   [dim](按 Ctrl+C 停止)[/]\n"
    )
    env = dict(os.environ)
    env.setdefault("PORT", str(port))
    try:
        subprocess.run("npm start", cwd=project_dir, shell=True, env=env)
    except KeyboardInterrupt:
        pass
    console.print("\n[dim]服务已停止。[/]")
