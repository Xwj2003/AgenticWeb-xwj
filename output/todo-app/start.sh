#!/bin/bash
if ! command -v node &> /dev/null
then
    echo "Node.js could not be found, please install it first"
    exit 1
fi
npm install
npm start