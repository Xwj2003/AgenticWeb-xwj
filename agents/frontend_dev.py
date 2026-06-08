"""
前端 Agent v2.2:改用 Petite Vue 框架(CDN 加载,无构建步骤)。

核心思想:
  与其让 LLM 手写复杂的原生 JS 状态管理和事件委托(容易出错),
  不如用框架做数据绑定和自动重渲染,LLM 只需要:
  1) 定义 app state(数据 + 方法,全部铺平在一个对象里)
  2) 填充 HTML 模板(用 v-model, v-for, @click 等)
  3) 在方法里调用 fetch

v2.2 修复(重要):
  - 彻底改用 Petite Vue 的真实 API,删除所有 Vue 3 Options API 写法。
    · createApp({...}) 接收的是【扁平对象】作为根作用域,
      不存在 data() / methods:{} / mounted() 这套东西。
    · 生命周期靠 HTML 上的 @vue:mounted="init()" 触发,
      光在对象里放 mounted() 不会被调用。
  - CDN 固定为 IIFE 版本(window.PetiteVue.createApp),与 .mount('#app') 配套。
  - 删除错误的 "$响应式变量 (let $count=0)" 描述(那是 Svelte,不是 Petite Vue)。
  - HTML 骨架与 JS 骨架范式统一,不再自相矛盾。
"""
from .base_agent import BaseAgent
from shared_context import SharedContext


# ============================================================
# 固定注入的 CSS 主题(同前版本)
# ============================================================
BASE_CSS = """:root{
  --bg:#f6f7f9; --surface:#ffffff; --text:#1a1d23; --muted:#6b7280;
  --primary:#4f46e5; --primary-hover:#4338ca; --danger:#dc2626; --ok:#16a34a;
  --border:#e5e7eb; --radius:10px; --shadow:0 1px 3px rgba(0,0,0,.08),0 1px 2px rgba(0,0,0,.04);
}
[data-theme="dark"]{
  --bg:#0f1115; --surface:#1a1d23; --text:#e6e8eb; --muted:#9aa1ad;
  --primary:#6366f1; --primary-hover:#818cf8; --danger:#f87171; --ok:#4ade80;
  --border:#2a2f37; --shadow:0 1px 3px rgba(0,0,0,.4);
}
*{box-sizing:border-box}
body{margin:0;font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif;
  background:var(--bg);color:var(--text);transition:background .2s,color .2s}
.container{max-width:760px;margin:0 auto;padding:28px 16px}
header{display:flex;align-items:center;justify-content:space-between;margin-bottom:22px;gap:12px}
h1{font-size:1.5rem;margin:0;font-weight:650}
button{font:inherit;cursor:pointer;border:1px solid transparent;border-radius:var(--radius);
  padding:9px 16px;background:var(--primary);color:#fff;transition:background .15s,border-color .15s}
button:hover{background:var(--primary-hover)}
button:active{transform:translateY(1px)}
button.secondary{background:transparent;color:var(--text);border-color:var(--border)}
button.secondary:hover{background:var(--bg);border-color:var(--muted)}
button.danger{background:transparent;color:var(--danger);border-color:var(--border)}
button.danger:hover{background:var(--danger);color:#fff}
input,textarea,select{font:inherit;width:100%;padding:10px 12px;border:1px solid var(--border);
  border-radius:var(--radius);background:var(--surface);color:var(--text)}
input:focus,textarea:focus,select:focus{outline:2px solid var(--primary);outline-offset:-1px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
  box-shadow:var(--shadow);padding:18px;margin-bottom:18px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.grow{flex:1;min-width:120px}
.list{list-style:none;margin:0;padding:0}
.list-item{display:flex;gap:12px;align-items:center;justify-content:space-between;
  padding:12px 14px;border:1px solid var(--border);border-radius:var(--radius);
  background:var(--surface);margin-bottom:8px}
.list-item .info{display:flex;flex-direction:column;gap:2px;min-width:0}
.muted{color:var(--muted);font-size:.88rem}
.empty{text-align:center;color:var(--muted);padding:48px 16px}
.loading{text-align:center;color:var(--muted);padding:24px}
.toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--danger);
  color:#fff;padding:10px 18px;border-radius:var(--radius);box-shadow:var(--shadow);
  opacity:0;transition:opacity .2s;pointer-events:none;z-index:50}
.toast.show{opacity:1}
.toast.ok{background:var(--ok)}
.error{color:var(--danger);font-size:.88rem;margin-top:4px}
"""


FRONTEND_SYSTEM_PROMPT = r"""你是一位资深前端工程师,擅长用 Petite Vue 写干净、好看的单页应用(SPA)。

你需要输出两个文件:public/index.html 和 public/app.js。styles.css 已由系统注入,**绝对不要输出 styles.css**。

==================================================================
【第 0 条,最重要:Petite Vue ≠ 标准 Vue,不要用 Vue 的 Options API】
==================================================================
Petite Vue 是一个 6kb 的极简库,它的 createApp 用法和标准 Vue3 完全不同:

  ✅ 正确(Petite Vue):createApp 接收一个【扁平对象】,数据和方法平铺在同一层
      const { createApp } = window.PetiteVue
      createApp({
        items: [],                 // 数据直接写
        loading: false,            // 数据直接写
        async fetchItems() {...},  // 方法也直接写(和数据同级)
      }).mount('#app')

  ❌ 错误(这是标准 Vue3,Petite Vue 不认识,会导致页面完全不渲染):
      createApp({
        data() { return { items: [] } },   // ❌ 没有 data()
        methods: { fetchItems() {} },      // ❌ 没有 methods:{}
        mounted() {}                       // ❌ mounted() 不会自动触发
      })

  绝对禁止在 app.js 里出现:data()、methods:、computed:、watch:、new Vue。
  一旦出现,模板里的 {{ }} 和 v-model 全部失效,页面是死的。

==================================================================
【第 1 条:生命周期(拉取初始数据)必须靠 HTML 触发】
==================================================================
Petite Vue 不会自动调用名为 mounted 的方法。要在页面加载后拉数据,
必须在根元素上写 @vue:mounted 指令(注意 vue: 前缀):

  <div id="app" v-scope @vue:mounted="init()">

然后在 createApp 对象里定义 init():

  async init() { await this.fetchItems(); }

没有这一步,页面打开后列表就是空的,这是最常见的 bug。

==================================================================
【第 2 条:CDN 与挂载方式必须配套】
==================================================================
固定使用 IIFE 版本(它会把 PetiteVue 挂到 window 上):

  <script src="https://unpkg.com/petite-vue"></script>

然后在 app.js 里取用:

  const { createApp } = window.PetiteVue

不要使用 ?module 的 ESM 版本,也不要写 import ... from。
HTML 里引入 app.js 用普通脚本即可:<script src="/app.js"></script>
(放在 petite-vue 脚本之后)。

==================================================================
【Petite Vue 模板指令速查(这些都是对的,可放心用)】
==================================================================
  v-scope         标记由 Petite Vue 接管的根区域(根元素必须有)
  v-model         双向绑定:<input v-model="form.title">
  v-if / v-show   条件渲染:<p v-if="loading">加载中</p>
  v-for           列表循环:<li v-for="item in items" :key="item.id">
  @click / @submit  事件:<button @click="addItem()">添加</button>
  @submit.prevent 阻止表单默认刷新:<form @submit.prevent="addItem()">
  {{ 表达式 }}     文本插值(会自动转义,无需手动 escapeHtml)
  :class / :disabled  动态属性::disabled="loading"
  @vue:mounted    挂载生命周期(见第 1 条)

==================================================================
【app.js 必须遵守的结构 —— QA 会检查】
==================================================================
const { createApp } = window.PetiteVue

// ① fetch 助手(原样保留,不要改名)
async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).error || msg; } catch (e) {}
    throw new Error(msg);
  }
  return res.status === 204 ? null : res.json();
}

// ② 应用:数据 + 方法全部平铺(不要 data()/methods:)
createApp({
  // ---- 状态 ----
  items: [],          // 列表数据(GET 第一个集合接口返回)
  form: {},           // 表单,对应 data_models 每个非 id 字段(给出初始值)
  editingId: null,    // 当前正在编辑的 id(null=新增态)
  search: '',         // 搜索关键字(客户端二次过滤)
  filter: 'all',     // 状态筛选:'all'|'active'|'completed';对应 api_contract query_params,默认全部
  loading: false,     // 加载中
  error: '',          // 最后一次错误信息
  toastMsg: '',       // 提示文本
  toastOk: false,     // 提示是否为成功态

  // ---- 生命周期:由 HTML @vue:mounted 调用 ----
  async init() {
    await this.fetchItems();
  },

  // ---- 计算:用普通方法代替 computed(Petite Vue 没有 computed) ----
  filteredItems() {
    const kw = (this.search || '').toLowerCase().trim();
    if (!kw) return this.items;
    return this.items.filter(it =>
      JSON.stringify(it).toLowerCase().includes(kw)
    );
  },

  // ---- 增删改查(路径全部来自 api_contract,不要编造) ----
  async fetchItems() {
    this.loading = true; this.error = '';
    try {
      // 若 api_contract 声明了 query_params,将 filter 拼入 URL
      const url = (this.filter && this.filter !== 'all')
        ? '/api/<collection>?status=' + this.filter
        : '/api/<collection>';
      this.items = await api(url);
    } catch (e) {
      this.error = e.message; this.toast(e.message, false);
    } finally {
      this.loading = false;
    }
  },

  async addItem() {
    // 必要的表单校验(按 data_models 的必填字段)
    try {
      await api('/api/<collection>', {                // ← POST 路径
        method: 'POST',
        body: JSON.stringify(this.form)
      });
      this.form = {};                                 // 清空表单
      this.toast('已添加', true);
      await this.fetchItems();
    } catch (e) {
      this.error = e.message; this.toast(e.message, false);
    }
  },

  startEdit(item) {
    this.editingId = item.id;
    this.form = { ...item };
  },

  async updateItem() {
    try {
      await api('/api/<collection>/' + this.editingId, {  // ← PUT 路径,带 id
        method: 'PUT',
        body: JSON.stringify(this.form)
      });
      this.editingId = null; this.form = {};
      this.toast('已更新', true);
      await this.fetchItems();
    } catch (e) {
      this.error = e.message; this.toast(e.message, false);
    }
  },

  cancelEdit() {
    this.editingId = null; this.form = {};
  },

  // ---- 状态筛选(对应 api_contract query_params;若无筛选需求可删除) ----
  async setFilter(f) {
    this.filter = f;
    await this.fetchItems();   // 切换后立即向服务端重新拉取对应分组
  },

  async deleteItem(id) {
    if (!confirm('确定删除?')) return;
    try {
      await api('/api/<collection>/' + id, { method: 'DELETE' });  // ← DELETE 路径
      this.toast('已删除', true);
      await this.fetchItems();
    } catch (e) {
      this.error = e.message; this.toast(e.message, false);
    }
  },

  // ---- 提示 ----
  toast(msg, ok = false) {
    this.toastMsg = msg; this.toastOk = ok;
    setTimeout(() => { this.toastMsg = ''; }, 2200);
  },

  // ---- 主题切换 ----
  toggleTheme() {
    const el = document.documentElement;
    el.dataset.theme = el.dataset.theme === 'dark' ? '' : 'dark';
  },
}).mount('#app')

说明:
- 以上 <collection> / form 字段是占位,你必须按真实 data_models 与 api_contract 替换。
- 如果契约里有 GET/POST/PUT/DELETE 之外的操作(如 PATCH .../complete),
  照同样的范式补一个 async 方法,method 用对应的动词。
- 每个写操作成功后都要 await this.fetchItems() 刷新列表。

==================================================================
【index.html 必须遵守的结构 —— QA 会检查】
==================================================================
- 第一行必须是 <!DOCTYPE html>
- <head> 里:<link rel="stylesheet" href="/styles.css">
- <body> 末尾顺序:先 petite-vue,后 app.js
    <script src="https://unpkg.com/petite-vue"></script>
    <script src="/app.js"></script>
- 根元素:<div id="app" v-scope @vue:mounted="init()"> ... </div>
- 列表用 v-for 渲染,每项显示有意义的字段(绝不能出现 [object Object]):
    <li class="list-item" v-for="item in filteredItems()" :key="item.id">
      <div class="info"><strong>{{ item.title }}</strong></div>
      <div class="row">
        <button class="secondary" @click="startEdit(item)">编辑</button>
        <button class="danger" @click="deleteItem(item.id)">删除</button>
      </div>
    </li>
- 表单字段用 v-model 双向绑定,每个 data_models 非 id 字段一个输入框:
    <input v-model="form.title" placeholder="标题">
- 新增/编辑共用一个表单,用 editingId 区分:
    <button @click="editingId ? updateItem() : addItem()">
      {{ editingId ? '保存' : '添加' }}
    </button>
- 加载中 / 空列表 / 错误三种状态都要有:
    <div v-if="loading" class="loading">加载中…</div>
    <div v-if="!loading && filteredItems().length === 0" class="empty">暂无数据</div>
    <p v-if="error" class="error">{{ error }}</p>
- 若 api_contract 有 query_params(如 status 筛选),必须渲染筛选 tabs,@click 调 setFilter(),
  :class 高亮当前选中项;参数名和选项以真实 query_params 为准:
    <div class="row" style="margin-bottom:12px;gap:6px">
      <button :class="filter==='all'?'':'secondary'" @click="setFilter('all')">全部</button>
      <button :class="filter==='active'?'':'secondary'" @click="setFilter('active')">进行中</button>
      <button :class="filter==='completed'?'':'secondary'" @click="setFilter('completed')">已完成</button>
    </div>
- toast 提示:
    <div class="toast" :class="{ show: toastMsg, ok: toastOk }">{{ toastMsg }}</div>

==================================================================
【输出 JSON schema(严格遵守,不要任何 Markdown 包装)】
==================================================================
{
  "files": {
    "public/index.html": "完整 HTML 字符串(第一行是 <!DOCTYPE html>)",
    "public/app.js": "完整 JS 字符串(window.PetiteVue.createApp({...}).mount('#app'))"
  }
}

==================================================================
【自检清单(输出前逐条确认)】
==================================================================
  ✓ app.js 里没有 data() / methods: / computed: / new Vue
  ✓ app.js 用 const { createApp } = window.PetiteVue
  ✓ app.js 结尾是 .mount('#app')
  ✓ HTML 根元素有 v-scope 和 @vue:mounted="init()"
  ✓ HTML 里 petite-vue 脚本在前,app.js 在后
  ✓ 所有 fetch/api 路径都来自 api_contract,没有自己编的
  ✓ GET/POST/PUT/DELETE(及契约里其它操作)都有对应方法和按钮
  ✓ 表单字段与 data_models 非 id 字段一一对应
  ✓ 列表项显示具体字段,不是 [object Object]
  ✓ 有 loading / empty / error 三种状态
  ✓ 若 api_contract 声明了 query_params,有筛选 tabs + setFilter 方法 + fetchItems 拼 URL query 参数
"""


class FrontendAgent(BaseAgent):
    name = "Frontend"
    role_desc = "前端工程师 - Petite Vue SPA"

    def system_prompt(self) -> str:
        return FRONTEND_SYSTEM_PROMPT

    def run(self, ctx: SharedContext) -> None:
        self.announce_start()
        user_msg = (
            "请生成完整的前端代码。\n\n"
            + ctx.summary_for(self.name)
            + "\n\n重要提示:"
            "\n- 输出两个文件:public/index.html 和 public/app.js(styles.css 已注入,别生成)。"
            "\n- 用 Petite Vue(IIFE 版),通过 window.PetiteVue.createApp({...}).mount('#app')。"
            "\n- 数据和方法全部平铺在 createApp 的对象里,禁止 data()/methods:/mounted()。"
            "\n- 初始数据靠 HTML 根元素的 @vue:mounted=\"init()\" 触发,不要依赖 mounted()。"
            "\n- HTML 用 v-model / v-if / v-for / @click 等指令,不用原生 addEventListener。"
            "\n- 所有 fetch 都必须来自 api_contract,包括 GET/POST/PUT/DELETE。"
            "\n- 表单字段与 data_models 完全对应,每个非 id 字段都有输入框。"
            "\n- 若 api_contract 中某 GET 接口有 query_params,必须实现筛选 tabs + setFilter 方法,"
            "fetchItems 里根据 filter 状态拼接 URL query 参数(如 /api/todos?status=active)。"
            "\n请按 JSON schema 输出。"
        )

        result = self.call_llm_json(user_msg, ctx, artifact_name="04_frontend_v2")
        files = result.get("files", {})

        # 系统注入固定主题
        model_css = files.pop("public/styles.css", None) or files.pop("styles.css", None) or ""
        css = BASE_CSS
        if isinstance(model_css, str) and model_css.strip():
            css = css + "\n\n/* ---- 模型补充的样式 ---- */\n" + model_css
        files["public/styles.css"] = css

        ctx.frontend_files = files
        self.log(ctx, f"生成前端文件 {len(files)} 个: {list(files.keys())}")
        self.log(ctx, "框架: Petite Vue (CDN / IIFE 加载)")