#!/bin/bash
# 检查 node 是否安装
cmd -v node >/dev/null 2>&1 || { echo >&2 "Node.js is not installed. Aborting."; exit 1; }

# 安装依赖
npm install

# 启动应用
npm start