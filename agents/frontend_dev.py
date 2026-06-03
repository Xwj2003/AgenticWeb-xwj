"""
前端 Agent:基于 PRD + API 契约,生成完整、好看、交互正确的前端单页应用。
职责边界:只写前端;只能调用 api_contract 中存在的接口。

要点:
- styles.css 是一套固定的、与业务无关的主题,由本模块直接注入(BASE_CSS),不经过 LLM,
  因此永不丢失、永不出错;模型只需产出 index.html 和 app.js。
- 传输沿用 JSON(call_llm_json)。为避免 JSON 转义出问题:HTML 一律用"模板字符串(反引号)
  + 单引号属性"构建,绝不用单引号字符串跨行拼接,也不写正则字面量。
"""
from .base_agent import BaseAgent
from shared_context import SharedContext


# ============================================================
# 固定注入的样式主题(现代、克制,含浅色/深色)。不经过 LLM,因此永不丢失、永不出错。
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
.toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--danger);
  color:#fff;padding:10px 18px;border-radius:var(--radius);box-shadow:var(--shadow);
  opacity:0;transition:opacity .2s;pointer-events:none;z-index:50}
.toast.show{opacity:1}
"""


FRONTEND_SYSTEM_PROMPT = """你是一位资深前端工程师,擅长用原生 JavaScript 写干净、好看、交互正确的小型 SPA。

【最重要的几条,先读】
1. 你**只需要输出两个文件**:public/index.html 和 public/app.js。styles.css 已由系统注入(现代浅色/深色主题),**不要输出 styles.css**,只在 HTML 里用下面列出的类名。
2. 构建 HTML 一律用**模板字符串(反引号 ` `)**,HTML 属性用**单引号**(例如 `<button class='danger'>`)。**绝不要用单引号字符串跨行拼接** —— 单引号字符串不能换行,会直接 SyntaxError。
3. **不要写正则字面量**(形如 /.../);需要正则就用 new RegExp("...")。只用 ASCII 引号 ' 和 ",不要用中文弯引号。
4. 表单要为 data_models 里**每个非 id 字段各放一个 <input>**(带 name 属性=字段名);新增和编辑时把**所有字段**都提交(后端通常要求字段都非空,只发一个字段会 400)。
5. 只用 fetch() 调 api_contract 里声明的接口,不要假设契约里没有的字段。所有功能完整可运行,不能有 TODO 占位。

【输出格式】
严格输出合法 JSON,只包含下面两个键,文件内容作为 JSON 字符串值:
{
  "files": {
    "public/index.html": "完整 HTML",
    "public/app.js": "完整 JS"
  }
}

【可用的 CSS 类名(已在注入的 styles.css 中定义,直接用,不要自己写样式表)】
- 布局:.container、header、h1、.card、.row(横向排列)、.grow(占满剩余宽度)
- 按钮:button(主)、button.secondary(次,用于"编辑")、button.danger(危险,用于"删除")
- 表单:input / select / textarea(已美化)
- 列表:ul.list > li.list-item;li 内可用 .info(纵向放主字段+次要信息)、.muted(灰色小字)
- 状态:.empty(空列表提示)、#toast(右下角提示,加 .show 显示)
- 深色模式:给 <html> 设 data-theme='dark' 切换,用 localStorage 记住

【index.html 要点】
- 第一行必须是 <!DOCTYPE html>(别漏感叹号)。<head> 里 <link rel="stylesheet" href="styles.css">。
- <body> 放 .container,内含:
  · header:<h1> 标题 + <button id="theme"> 切换主题
  · <form id="form" class="card">:为 data_models 每个非 id 字段放一个 <input>,每个 input 都要有 name(=字段名)和 placeholder;多个 input 包在 <div class="row"> 里;最后一个 <button type="submit">添加</button>
  · <ul id="list" class="list"></ul>
  · <div id="toast" class="toast"></div>
- 末尾 <script src="app.js"></script>,不要内联大量 JS。

【状态与渲染逻辑(界面正确的关键)】
1. 单一数据源:用 const state = { items: [] } 保存数据(items 换成真实集合名),渲染都从 state 出发。
2. 变更后刷新:每次增/删/改成功后重新拉取列表更新 state 再重渲染。
3. 渲染幂等:每次渲染先清空容器再重建,避免条目堆叠。
4. 事件委托:在 #list 上**只绑定一次** click,用 e.target.closest('[data-action]') 分发;绝不在渲染循环里反复 addEventListener。
5. 三种状态都处理:加载中 / 空列表(.empty) / 出错(toast 提示而非只 console)。
6. 表单提交阻止默认行为、收集所有字段、校验非空、成功后 reset 并刷新。
7. 用户输入插入 innerHTML 前先 escapeHtml。

【app.js 完整骨架(占位集合名 items、示例字段 name/position/email,请全部换成 data_models 的真实集合与字段)】
// >>> SKELETON START
const state = { items: [] };
const listEl = document.querySelector('#list');
const formEl = document.querySelector('#form');
const themeBtn = document.querySelector('#theme');

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = (s == null ? '' : String(s));
  return d.innerHTML;
}

function toast(msg) {
  const t = document.querySelector('#toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(function () { t.classList.remove('show'); }, 2500);
}

async function api(path, options) {
  const res = await fetch(path, Object.assign({ headers: { 'Content-Type': 'application/json' } }, options || {}));
  if (!res.ok) {
    let m = res.statusText;
    try { m = (await res.json()).error || m; } catch (e) {}
    throw new Error(m);
  }
  return res.status === 204 ? null : res.json();
}

// 用模板字符串构建 HTML(可跨行),属性用单引号;每个字段都 escapeHtml
function render() {
  listEl.innerHTML = '';
  if (state.items.length === 0) {
    listEl.innerHTML = `<li class='empty'>还没有数据</li>`;
    return;
  }
  for (const it of state.items) {
    const li = document.createElement('li');
    li.className = 'list-item';
    li.dataset.id = it.id;
    li.innerHTML = `
      <div class='info'>
        <span>${escapeHtml(it.name)}</span>
        <span class='muted'>${escapeHtml(it.position)} · ${escapeHtml(it.email)}</span>
      </div>
      <span class='row'>
        <button class='secondary' data-action='edit'>编辑</button>
        <button class='danger' data-action='delete'>删除</button>
      </span>`;
    listEl.appendChild(li);
  }
}

async function refresh() {
  try {
    state.items = await api('/api/items');
    render();
  } catch (e) {
    toast('加载失败: ' + e.message);
  }
}

// 事件委托:只绑定一次。删除直接调接口;编辑逐字段 prompt 后整条提交
listEl.addEventListener('click', async function (e) {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const id = btn.closest('[data-id]').dataset.id;
  try {
    if (btn.dataset.action === 'delete') {
      await api('/api/items/' + id, { method: 'DELETE' });
    } else if (btn.dataset.action === 'edit') {
      const cur = state.items.find(function (x) { return x.id == id; });
      const payload = {};
      let cancelled = false;
      formEl.querySelectorAll('input, select, textarea').forEach(function (el) {
        if (!el.name || cancelled) return;
        const v = prompt((el.placeholder || el.name) + ':', cur && cur[el.name] != null ? cur[el.name] : '');
        if (v === null) { cancelled = true; return; }
        payload[el.name] = v.trim();
      });
      if (cancelled) return;
      await api('/api/items/' + id, { method: 'PUT', body: JSON.stringify(payload) });
    }
    await refresh();
  } catch (err) {
    toast('操作失败: ' + err.message);
  }
});

// 新增:收集表单里每个带 name 的输入框(对应 data_models 的每个字段),整条提交
formEl.addEventListener('submit', async function (e) {
  e.preventDefault();
  const payload = {};
  formEl.querySelectorAll('input, select, textarea').forEach(function (el) {
    if (el.name) payload[el.name] = el.value.trim();
  });
  if (Object.values(payload).some(function (v) { return v === ''; })) { toast('请填写所有字段'); return; }
  try {
    await api('/api/items', { method: 'POST', body: JSON.stringify(payload) });
    formEl.reset();
    await refresh();
  } catch (err) {
    toast('添加失败: ' + err.message);
  }
});

// 深色模式:切换 <html> 的 data-theme 并记到 localStorage
function applyTheme(t) { document.documentElement.setAttribute('data-theme', t); }
applyTheme(localStorage.getItem('theme') || 'light');
if (themeBtn) themeBtn.addEventListener('click', function () {
  const next = (document.documentElement.getAttribute('data-theme') === 'dark') ? 'light' : 'dark';
  localStorage.setItem('theme', next);
  applyTheme(next);
});

refresh();
// <<< SKELETON END

【契约覆盖与兼容 QA】
- 必须实现 api_contract 里的**每一个**操作:POST→添加表单;GET→列表;PUT→每条"编辑";DELETE→每条"删除";其它(如 PATCH .../xxx)→对应按钮。删/改都要有可见可点的按钮。
- 调带参接口时路径写字面量、只把 id 拼进去:api('/api/items/' + id, { method: 'DELETE' }),不要把整段 base 路径塞进变量再拼(QA 静态比对解析不了变量会误判)。
"""


class FrontendAgent(BaseAgent):
    name = "Frontend"
    role_desc = "前端工程师 - 原生 HTML/JS SPA"

    def system_prompt(self) -> str:
        return FRONTEND_SYSTEM_PROMPT

    def run(self, ctx: SharedContext) -> None:
        self.announce_start()
        user_msg = (
            "请生成完整的前端代码。\n\n"
            + ctx.summary_for(self.name)
            + "\n\n重要提示:"
            "\n- 只输出 public/index.html 和 public/app.js 两个文件(styles.css 已由系统注入,别再生成)。"
            "\n- 构建 HTML 用模板字符串(反引号)+ 单引号属性,绝不用单引号字符串跨行拼接;不要写正则字面量。"
            "\n- 表单要为 data_models 每个非 id 字段放一个带 name 的 input,新增/编辑都提交全部字段。"
            "\n- 只能 fetch api_contract 里声明的接口,所有功能可见可交互,直接用提供的 CSS 类名。"
            "\n请按 JSON schema 输出。"
        )

        result = self.call_llm_json(user_msg, ctx, artifact_name="04_frontend")
        files = result.get("files", {})

        # 系统注入固定主题:保证 styles.css 必定存在且好看;若模型仍附带了 css 则追加在后
        model_css = files.pop("public/styles.css", None) or files.pop("styles.css", None) or ""
        css = BASE_CSS
        if isinstance(model_css, str) and model_css.strip():
            css = css + "\n\n/* ---- 模型补充的样式 ---- */\n" + model_css
        files["public/styles.css"] = css

        ctx.frontend_files = files
        self.log(ctx, f"生成前端文件 {len(files)} 个: {list(files.keys())}")
        self.log(ctx, "已注入固定基础样式主题 styles.css")