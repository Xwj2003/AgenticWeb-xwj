#!/bin/bash
# 检查 Node 是否安装
if ! command -v node &> /dev/null
then
    echo "Node.js 未安装，请先安装 Node.js"
    exit 1
fi

# 安装依赖
npm install

# 启动应用
npm start