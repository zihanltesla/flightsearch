#!/bin/sh
# 启动后端（首次使用请先运行 ./setup.sh）
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    echo "未找到虚拟环境，正在执行 setup.sh ..."
    ./setup.sh
fi
exec .venv/bin/python main.py
