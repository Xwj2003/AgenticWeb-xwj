const path = require('path');
const express = require('express');
const cors = require('cors');
const { load, save } = require('./db');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// 列表
app.get('/api/todos', (req, res) => {
  res.json(load().todos);
});

// 新建(按 data_model 取请求体字段,做必要校验,布尔/数字直接用原生类型)
app.post('/api/todos', (req, res) => {
  const body = req.body || {};
  if (!body.title) return res.status(400).json({ error: 'title 不能为空' });
  const data = load();
  const item = { id: ++data.seq, ...body };   // 也可显式列字段并给默认值
  data.todos.push(item);
  save(data);
  res.status(201).json(item);
});

// 更新(注意 Number():URL 参数是字符串)
app.put('/api/todos/:id', (req, res) => {
  const data = load();
  const item = data.todos.find(x => x.id === Number(req.params.id));
  if (!item) return res.status(404).json({ error: '不存在' });
  Object.assign(item, req.body || {});
  save(data);
  res.json(item);
});

// 删除
app.delete('/api/todos/:id', (req, res) => {
  const data = load();
  const i = data.todos.findIndex(x => x.id === Number(req.params.id));
  if (i === -1) return res.status(404).json({ error: '不存在' });
  data.todos.splice(i, 1);
  save(data);
  res.json({ message: '已删除' });
});

app.listen(PORT, () => console.log(`running at http://localhost:${PORT}`));