"""
主入口:从命令行接收用户需求,启动 Agent 团队流水线。

用法:
    python main.py "帮我做一个待办事项 Web 应用,要登录、CRUD、深色模式"
    python main.py --interactive "..."
    python main.py --file requirements.txt
"""
import sys
import argparse
from orchestrator import run_pipeline
from config import Config


def parse_args():
    parser = argparse.ArgumentParser(
        description="全栈开发 Agent 团队 —— 一句话生成完整可运行的 Web 项目"
    )
    parser.add_argument(
        "requirement",
        nargs="?",
        help="用户需求(一句话)",
    )
    parser.add_argument(
        "--file", "-f",
        help="从文件读取需求(可写多行详细需求)",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="开启人工介入模式(在 PRD/架构 后暂停)",
    )
    parser.add_argument(
        "--output", "-o",
        help="输出目录(默认 ./output)",
    )
    parser.add_argument(
        "--run", "-r",
        action="store_true",
        help="生成完成且 QA 通过后,自动 npm install + npm start 并打开浏览器",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # 读取需求
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            requirement = f.read().strip()
    elif args.requirement:
        requirement = args.requirement
    else:
        # 没提供参数:进入交互输入
        print("📝 请输入你的需求(一句话即可),回车确认:")
        requirement = input("> ").strip()
        if not requirement:
            print("需求不能为空")
            sys.exit(1)

    # 应用 CLI 覆盖
    if args.interactive:
        Config.HUMAN_IN_LOOP = True
    if args.output:
        Config.OUTPUT_DIR = args.output
    if args.run:
        Config.AUTO_RUN = True

    # 启动!
    run_pipeline(requirement)


if __name__ == "__main__":
    main()