const { createApp } = window.PetiteVue

// fetch 助手(原样保留,不要改名)
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

// 应用:数据 + 方法全部平铺(不要 data()/methods:)
createApp({
  // ---- 状态 ----
  items: [],          // 列表数据(GET 第一个集合接口返回)
  form: { title: '' },           // 表单,对应 data_models 每个非 id 字段(给出初始值)
  editingId: null,    // 当前正在编辑的 id(null=新增态)
  search: '',         // 搜索关键字(可选)
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
      this.items = await api('/api/todos');   // ← 替换为真实集合路径
    } catch (e) {
      this.error = e.message; this.toast(e.message, false);
    } finally {
      this.loading = false;
    }
  },

  async addItem() {
    // 必要的表单校验(按 data_models 的必填字段)
    try {
      await api('/api/todos', {                // ← POST 路径
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

  // ---- 标记完成 ----
  // 【关键修复】接收列表项 item,用 item.id 拼 URL。
  // 原来"完成"按钮调的是 updateItem(),它用的是一直为 null 的 this.editingId,
  // 导致请求打到 /api/todos/null → 后端 Number("null")=NaN → 404 不存在。
  async completeItem(item) {
    try {
      await api('/api/todos/' + item.id, {     // ← PUT 路径,用 item.id
        method: 'PUT',
        body: JSON.stringify({ ...item, completed: true })
      });
      this.toast('已完成', true);
      await this.fetchItems();
    } catch (e) {
      this.error = e.message; this.toast(e.message, false);
    }
  },

  // ---- 以下为编辑流程(当前 UI 暂未提供编辑入口,保留以备扩展) ----
  // 若日后在 HTML 里加"编辑"按钮调用 startEdit(item),这套逻辑即可生效。
  startEdit(item) {
    this.editingId = item.id;
    this.form = { ...item }; // 复制对象以避免直接修改原始数据
  },

  async updateItem() {
    try {
      await api('/api/todos/' + this.editingId, {  // ← PUT 路径,带 id
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

  async deleteItem(id) {
    if (!confirm('确定删除?')) return;
    try {
      await api('/api/todos/' + id, { method: 'DELETE' });  // ← DELETE 路径
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
