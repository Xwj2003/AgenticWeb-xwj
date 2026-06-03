# todo-app

## 项目简介
一款简单易用的待办事项应用，支持增删改查和标记完成。

## 技术栈
- 后端语言: Node.js
- 后端框架: Express
- 存储: JSON 文件
- 前端: Vanilla HTML + JavaScript

## 前置依赖
Node.js 版本 >= 14.0.0

## 安装步骤
1. 克隆项目仓库到本地。
2. 进入项目目录：`
   cd todo-app`
3. 安装依赖：`
   npm install`

## 启动步骤
1. 确保 Node.js 已安装。
2. 在项目根目录下运行：`
   npm start`

## 访问地址
应用启动后，可以通过浏览器访问 `http://localhost:3000` 查看待办事项列表。

## API 列表
### 获取全部待办事项
- **方法**: GET
- **路径**: `/api/todos`
- **请求体**: null
- **响应示例**:
  ```json
  [
    {
      "id": 1,
      "title": "Task 1",
      "completed": false
    }
  ]
  ```
### 添加一个新任务
- **方法**: POST
- **路径**: `/api/todos`
- **请求体**:
  ```json
  {
    "title": "New Task"
  }
  ```
- **响应示例**:
  ```json
  {
    "id": 2,
    "title": "New Task",
    "completed": false
  }
  ```
### 删除一个任务
- **方法**: DELETE
- **路径**: `/api/todos/{id}`
- **请求体**: null
- **响应示例**:
  ```json
  {}
  ```
### 修改一个任务
- **方法**: PUT
- **路径**: `/api/todos/{id}`
- **请求体**:
  ```json
  {
    "title": "Updated Task",
    "completed": true
  }
  ```
- **响应示例**:
  ```json
  {
    "id": 1,
    "title": "Updated Task",
    "completed": true
  }
  ```

## 目录结构
```
todo-app/
├── backend/
│   ├── db.js
│   ├── server.js
│   └── package.json
└── public/
    ├── app.js
    ├── index.html
    └── styles.css
```