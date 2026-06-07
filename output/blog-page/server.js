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
app.get('/api/posts', (req, res) => {
  res.json(load().posts);
});

// 新建(按 data_model 取请求体字段,做必要校验,布尔/数字直接用原生类型)
app.post('/api/posts', (req, res) => {
  const body = req.body || {};
  if (!body.title || !body.content) return res.status(400).json({ error: 'title 和 content 不能为空' });
  const data = load();
  const item = { id: ++data.seq, ...body };   // 也可显式列字段并给默认值
  data.posts.push(item);
  save(data);
  res.status(201).json(item);
});

// 更新(注意 Number():URL 参数是字符串)
app.put('/api/posts/:id', (req, res) => {
  const data = load();
  const item = data.posts.find(x => x.id === Number(req.params.id));
  if (!item) return res.status(404).json({ error: '不存在' });
  Object.assign(item, req.body || {});
  save(data);
  res.json(item);
});

// 删除
app.delete('/api/posts/:id', (req, res) => {
  const data = load();
  const i = data.posts.findIndex(x => x.id === Number(req.params.id));
  if (i === -1) return res.status(404).json({ error: '不存在' });
  data.posts.splice(i, 1);
  save(data);
  res.json({ message: '已删除' });
});

// 列表
app.get('/api/posts/:id', (req, res) => {
  const id = Number(req.params.id);
  const post = load().posts.find(x => x.id === id);
  if (!post) return res.status(404).json({ error: '不存在' });
  res.json(post);
});

app.listen(PORT, () => console.log(`running at http://localhost:${PORT}`));