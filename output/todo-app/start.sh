#!/bin/bash

# 检查 Node.js 是否安装
if ! command -v node &> /dev/null
then
    echo "Node.js could not be found, please install it first."
    exit 1
fi

cd $(dirname "$0")
npm install
npm start