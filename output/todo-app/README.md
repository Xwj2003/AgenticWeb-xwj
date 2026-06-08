# todo-app

## 项目简介
一个简单的TODO应用WEB，支持添加、删除待办事项、标记完成待办事项和筛选待办事项。

## 技术栈
- 后端语言: Node.js
- 后端框架: Express
- 前端: Vanilla HTML + JavaScript

## 前置依赖
Node.js 版本 >= 14.0.0

## 安装步骤
1. 克隆项目到本地
2. 进入项目目录
3. 运行 `npm install`

## 启动步骤
运行 `npm start`

## 访问地址
http://localhost:3000/

## API 列表
### 获取待办列表
- **URL**: `/api/todos`
- **Method**: GET
- **Query Params**: `status=all|active|completed (可选,默认返回全部)`
- **Response Example**:
  ```json
  [
    {
      "id": 1,
      "title": "...