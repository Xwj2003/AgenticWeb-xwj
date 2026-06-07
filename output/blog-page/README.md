# blog-page

## 项目简介
一个简单的博客页面，展示文章列表和详细内容。

## 技术栈
- 后端语言: Node.js
- 后端框架: Express
- 存储: JSON 文件
- 前端: Vanilla HTML + JavaScript

## 前置依赖
Node.js 版本 >= 14.0.0

## 安装步骤
```sh
cp .env.example .env
npm install
```

## 启动步骤
```sh
npm start
```

## 访问地址
http://localhost:3000/

## API 列表
### 获取全部文章
- **方法**: GET
- **路径**: /api/posts
- **描述**: 获取全部文章

### 获取单篇文章详情
- **方法**: GET
- **路径**: /api/posts/{id}
- **描述**: 获取单篇文章详情

## 目录结构
```
blog-page/
├── backend/
│   ├── db.js
│   ├── server.js
│   └── package.json
├── frontend/
│   ├── public/
│   │   ├── index.html
│   │   ├── app.js
│   │   └── styles.css
│   └── .gitignore
├── start.sh
└── README.md
```
