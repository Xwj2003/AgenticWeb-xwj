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

function render() {
  listEl.innerHTML = '';
  if (state.items.length === 0) {
    listEl.innerHTML = `<li class='empty'>还没有文章</li>`;
    return;
  }
  for (const it of state.items) {
    const li = document.createElement('li');
    li.className = 'list-item';
    li.dataset.id = it.id;
    li.innerHTML = `
      <div class='info'>
        <span>${escapeHtml(it.title)}</span>
        <span class='muted'>发布于 ${it.published_date}</span>
      </div>
      <button class='secondary' data-action='edit'>编辑</button>
      <button class='danger' data-action='delete'>删除</button>
    `;
    listEl.appendChild(li);
  }
}

async function refresh() {
  try {
    state.items = await api('/api/posts');
    render();
  } catch (e) {
    toast('加载失败: ' + e.message);
  }
}

listEl.addEventListener('click', async function (e) {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const id = btn.closest('[data-id]').dataset.id;
  try {
    if (btn.dataset.action === 'delete') {
      await api('/api/posts/' + id, { method: 'DELETE' });
    } else if (btn.dataset.action === 'edit') {
      const cur = state.items.find(function (x) { return x.id == id; });
      const payload = {};
      let cancelled = false;
      formEl.querySelectorAll('input, textarea').forEach(function (el) {
        if (!el.name || cancelled) return;
        const v = prompt((el.placeholder || el.name) + ':', cur && cur[el.name] != null ? cur[el.name] : '');
        if (v === null) { cancelled = true; return; }
        payload[el.name] = v.trim();
      });
      if (cancelled) return;
      await api('/api/posts/' + id, { method: 'PUT', body: JSON.stringify(payload) });
    }
    await refresh();
  } catch (err) {
    toast('操作失败: ' + err.message);
  }
});

formEl.addEventListener('submit', async function (e) {
  e.preventDefault();
  const payload = {};
  formEl.querySelectorAll('input, textarea').forEach(function (el) {
    if (el.name) payload[el.name] = el.value.trim();
  });
  if (Object.values(payload).some(function (v) { return v === ''; })) { toast('请填写所有字段'); return; }
  try {
    await api('/api/posts', { method: 'POST', body: JSON.stringify(payload) });
    formEl.reset();
    await refresh();
  } catch (err) {
    toast('添加失败: ' + err.message);
  }
});

function applyTheme(t) { document.documentElement.setAttribute('data-theme', t); }
applyTheme(localStorage.getItem('theme') || 'light');
if (themeBtn) themeBtn.addEventListener('click', function () {
  const next = (document.documentElement.getAttribute('data-theme') === 'dark') ? 'light' : 'dark';
  localStorage.setItem('theme', next);
  applyTheme(next);
});

refresh();
// <<< SKELETON END