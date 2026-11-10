#!/bin/sh
# 首次使用：创建虚拟环境并安装依赖
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
echo
echo "安装完成。如需接入真实数据源，请复制 .env.example 为 .env 并填入 Amadeus 密钥，然后运行 ./start.sh"
