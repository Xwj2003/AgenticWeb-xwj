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
app.get('/api/employees', (req, res) => {
  res.json(load().employees);
});

// 新建
app.post('/api/employees', (req, res) => {
  const body = req.body || {};
  const data = load();
  const item = { id: ++data.seq, ...body };
  data.employees.push(item);
  save(data);
  res.status(201).json(item);
});

// 更新
app.put('/api/employees/:id', (req, res) => {
  const data = load();
  const item = data.employees.find(x => x.id === Number(req.params.id));
  if (!item) return res.status(404).json({ error: '不存在' });
  Object.assign(item, req.body || {});
  save(data);
  res.json(item);
});

// 删除
app.delete('/api/employees/:id', (req, res) => {
  const data = load();
  const i = data.employees.findIndex(x => x.id === Number(req.params.id));
  if (i === -1) return res.status(404).json({ error: '不存在' });
  data.employees.splice(i, 1);
  save(data);
  res.json({ message: '已删除' });
});

app.listen(PORT, () => console.log(`running at http://localhost:${PORT}`));