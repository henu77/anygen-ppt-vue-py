#!/bin/bash

# Anygen PPT FastAPI 启动脚本

echo "=========================================="
echo "Anygen PPT FastAPI 启动"
echo "=========================================="

# 检查 Python 版本
python_version=$(python --version 2>&1 | awk '{print $2}')
echo "Python 版本: $python_version"

# 检查依赖
echo ""
echo "检查依赖..."
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python -m venv venv
fi

# 激活虚拟环境
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
fi

# 安装依赖
echo "安装依赖..."
pip install -r requirements.txt

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo ""
    echo "创建 .env 文件..."
    cp .env.example .env
    echo "请编辑 .env 文件配置参数"
fi

# 启动服务
echo ""
echo "=========================================="
echo "启动服务..."
echo "=========================================="
echo ""
echo "API 文档: http://localhost:8000/docs"
echo "Redoc: http://localhost:8000/redoc"
echo ""

python main.py
