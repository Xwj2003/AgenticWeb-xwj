# employee-management-platform

## 项目简介
一个基础的员工管理平台，支持员工的增删改查操作。

## 技术栈
- 后端语言: Node.js
- 后端框架: Express
- 存储: JSON 文件
- 前端: Vanilla HTML + JavaScript

## 前置依赖
Node.js 版本 >= 14.0.0

## 安装步骤
```bash
git clone https://github.com/your-repo/employee-management-platform.git
cd employee-management-platform
npm install
```

## 启动步骤
```bash
npm start
```

## 访问地址
http://localhost:3000

## API 列表
### 获取全部员工
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

### 新增员工
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

### 编辑员工信息
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

### 删除员工
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
└── frontend/
    ├── public/
    │   ├── app.js
    │   ├── index.html
    │   └── styles.css
    └── .gitignore
```
