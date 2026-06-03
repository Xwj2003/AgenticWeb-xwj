const path = require('path');
const express = require('express');
const cors = require('cors');
const { load, save } = require('./db');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

app.post('/api/todos', (req, res) => {
  const { title } = req.body || {};
  if (!title) return res.status(400).json({ error: 'title 不能为空' });
  const data = load();
  const todo = { id: ++data.seq, title, completed: false };
  data.todos.push(todo);
  save(data);
  res.status(201).json(todo);
});

app.get('/api/todos', (req, res) => {
  res.json(load().todos);
});

app.put('/api/todos/:id', (req, res) => {
  const { title } = req.body || {};
  const data = load();
  const item = data.todos.find(t => t.id === Number(req.params.id));
  if (!item) return res.status(404).json({ error: '不存在' });
  item.title = title;
  save(data);
  res.json(item);
});

app.delete('/api/todos/:id', (req, res) => {
  const data = load();
  const i = data.todos.findIndex(t => t.id === Number(req.params.id));
  if (i === -1) return res.status(404).json({ error: '不存在' });
  data.todos.splice(i, 1);
  save(data);
  res.json({ message: '已删除' });
});

app.listen(PORT, () => console.log(`running at http://localhost:${PORT}`));