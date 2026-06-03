"""
DevOps Agent:产出工程化交付物 —— README、启动脚本、.gitignore。
让用户拿到项目后能一键跑起来。
"""
from .base_agent import BaseAgent
from shared_context import SharedContext


DEVOPS_SYSTEM_PROMPT = """你是一位 DevOps 工程师。基于已有的前后端代码,产出项目交付所需的工程化文件。

【硬性规则】
1. README.md 必须包含:项目简介、技术栈、前置依赖(Node.js 版本)、安装步骤、启动步骤、访问地址、API 列表(取自 api_contract)、目录结构。
2. start.sh 必须能在 macOS/Linux 上跑通,内容:检查 node 是否安装 → npm install → npm start。
3. .gitignore 至少包含:node_modules/、data.json、.DS_Store、_agent_artifacts/(中间产物和本地数据不应入仓)
4. 必须严格输出合法 JSON,文件内容用字符串表示。

【输出 JSON Schema】
{
  "files": {
    "README.md": "...",
    "start.sh": "...",
    ".gitignore": "..."
  }
}
"""


class DevOpsAgent(BaseAgent):
    name = "DevOps"
    role_desc = "运维工程师 - README + 启动脚本"

    def system_prompt(self) -> str:
        return DEVOPS_SYSTEM_PROMPT

    def run(self, ctx: SharedContext) -> None:
        self.announce_start()
        user_msg = (
            "请生成项目的工程化交付文件。\n\n"
            + ctx.summary_for(self.name)
            + "\n\n后端文件清单: " + ", ".join(ctx.backend_files.keys())
            + "\n前端文件清单: " + ", ".join(ctx.frontend_files.keys())
            + "\n请按 JSON schema 输出。"
        )

        result = self.call_llm_json(user_msg, ctx, artifact_name="05_devops")
        files = result.get("files", {})
        ctx.devops_files = files
        self.log(ctx, f"生成工程化文件 {len(files)} 个: {list(files.keys())}")
