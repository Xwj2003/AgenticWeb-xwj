"""
产品经理 Agent:把模糊的一句话需求转化为结构化 PRD。
职责边界:只澄清需求,不做技术决策。
"""
from .base_agent import BaseAgent
from shared_context import SharedContext


PM_SYSTEM_PROMPT = """你是一位资深产品经理。你的唯一职责是把用户的一句话需求,转化为一份精简、结构化的 PRD(产品需求文档)。

【硬性规则】
1. 严格遵守 "hello-world MVP" 原则:目标是端到端跑通最简版本,不是做大而全的产品。
2. 不要凭空增加用户没要求的功能。如果用户没说"用户系统",就不要加登录注册。
3. 不要做技术决策(那是架构师的事)。不要提具体框架/库的名字。
4. 必须输出严格合法的 JSON,不要加任何 Markdown 包装,不要加注释。

【输出 JSON Schema】
{
  "project_name": "小写字母+连字符,如 todo-app(英文,文件夹命名用)",
  "description": "一句话项目描述(中文)",
  "core_features": ["功能点1", "功能点2", "..."],   // 3-5 个,聚焦核心
  "user_stories": [
    {"role": "用户角色", "action": "想要做什么", "benefit": "为了什么"}
  ],
  "out_of_scope": ["明确不做的事1", "..."],   // 防止下游 Agent 越界
  "ui_requirements": {
    "dark_mode": true | false,
    "responsive": true | false,
    "key_pages": ["页面1", "页面2"]
  }
}
"""


class ProductManagerAgent(BaseAgent):
    name = "ProductManager"
    role_desc = "产品经理 - 需求拆解"

    def system_prompt(self) -> str:
        return PM_SYSTEM_PROMPT

    def run(self, ctx: SharedContext) -> None:
        self.announce_start()
        user_msg = f"用户的一句话需求是:\n\n「{ctx.requirement}」\n\n请按 JSON schema 输出 PRD。"

        # 此时 artifacts_dir 还没初始化(要等拿到 project_name),先用临时方式
        prd = self.llm.chat_json(
            system_prompt=self.system_prompt(),
            user_message=user_msg,
        )

        # 拿到 project_name 后,正式初始化目录
        project_name = prd.get("project_name", "untitled-project")
        ctx.init_paths(project_name)

        # 现在补落盘
        ctx.save_artifact("01_pm_prompt.md", self._format_prompt(user_msg))
        ctx.save_artifact("01_pm_output.json", prd)

        ctx.prd = prd
        self.log(ctx, f"PRD 已生成,项目名: {project_name}")
        self.log(ctx, f"核心功能: {', '.join(prd.get('core_features', []))}")

    def _format_prompt(self, user_message: str) -> str:
        return f"# ProductManager Prompt\n\n## System\n\n{self.system_prompt()}\n\n## User\n\n{user_message}"
