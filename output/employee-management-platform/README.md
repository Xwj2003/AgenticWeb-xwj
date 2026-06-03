# employee-management-platform

## 项目简介
一个简单的员工管理平台，支持基础的增删改查操作。

## 技术栈
- 后端语言: Node.js
- 后端框架: Express
- 存储: JSON 文件
- 前端: Vanilla HTML & JS

## 前置依赖
Node.js 版本 >= 14.0.0

## 安装步骤
1. 克隆项目到本地
2. 进入项目根目录
3. 运行 `npm install`

## 启动步骤
1. 确保 Node.js 已安装
2. 运行 `npm start`

## 访问地址
http://localhost:3000

## API 列表
### 获取全部员工信息
- **方法**: GET
- **路径**: /api/employees
- **请求体**: null
- **响应示例**:
  ```json
  [
    {
      "id": 1,
      "name": "...",
      "position": "...",
      "email": "..."
    }
  ]
  ```
### 添加新员工
- **方法**: POST
- **路径**: /api/employees
- **请求体**:
  ```json
  {
    "name": "string",
    "position": "string",
    "email": "string"
  }
  ```
- **响应示例**:
  ```json
  {
    "id": 1,
    "name": "...",
    "position": "...",
    "email": "..."
  }
  ```
### 修改现有员工信息
- **方法**: PUT
- **路径**: /api/employees/{id}
- **请求体**:
  ```json
  {
    "name": "string",
    "position": "string",
    "email": "string"
  }
  ```
- **响应示例**:
  ```json
  {
    "id": 1,
    "name": "...",
    "position": "...",
    "email": "..."
  }
  ```
### 删除员工信息
- **方法**: DELETE
- **路径**: /api/employees/{id}
- **请求体**: null
- **响应示例**:
  ```json
  {}
  ```

## 目录结构
```
employee-management-platform/
├── backend/
│   ├── db.js
│   ├── package.json
│   └── server.js
└── public/
    ├── app.js
    ├── index.html
    └── styles.css
```