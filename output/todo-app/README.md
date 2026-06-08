# todo-app

## 项目简介
一个简单的待办事项Web应用，支持增删改查功能。

## 技术栈
- 后端语言: Node.js
- 后端框架: Express
- 存储: JSON 文件
- 前端: 原生 HTML 和 JavaScript

## 前置依赖
Node.js 版本 >= 14.0.0

## 安装步骤
```bash
git clone https://github.com/your-repo/todo-app.git
cd todo-app
npm install
```

## 启动步骤
```bash
npm start
```

## 访问地址
http://localhost:3000

## API 列表
### 获取全部待办事项
- **方法**: GET
- **路径**: /api/todos
- **响应示例**:
  ```json
  [
    {
      "id": 1,
      "title": "...