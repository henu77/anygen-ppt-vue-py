#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Ubuntu 部署脚本：安装 Python 3.10 + 虚拟环境 + 运行 FastAPI
# ============================================================

APP_DIR="$(cd "$(dirname "$0")/anygen-ppt-fastapi" && pwd)"
VENV_DIR="$APP_DIR/.venv"
PYTHON_VERSION="3.10"

echo "============================================"
echo " AnyGen PPT FastAPI 部署脚本"
echo " 项目目录: $APP_DIR"
echo "============================================"

# ── 1. 系统依赖 ──────────────────────────────────────────────
echo ""
echo "[1/6] 安装系统依赖..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    software-properties-common \
    curl \
    wget \
    git \
    build-essential \
    libssl-dev \
    zlib1g-dev \
    libbz2-dev \
    libreadline-dev \
    libsqlite3-dev \
    libffi-dev \
    liblzma-dev \
    libxml2-dev \
    libxmlsec1-dev \
    tk-dev

# ── 2. 安装 Python 3.10 ─────────────────────────────────────
echo ""
echo "[2/6] 检查 Python $PYTHON_VERSION..."

if command -v python3.10 &>/dev/null; then
    echo "  Python 3.10 已安装: $(python3.10 --version)"
else
    echo "  添加 deadsnakes PPA 并安装 Python 3.10..."
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3.10 python3.10-venv python3.10-dev python3.10-distutils
    echo "  Python 3.10 安装完成: $(python3.10 --version)"
fi

# 确保 pip 可用
if ! python3.10 -m pip --version &>/dev/null; then
    echo "  安装 pip..."
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3.10
fi

# ── 3. 创建虚拟环境 ─────────────────────────────────────────
echo ""
echo "[3/6] 创建虚拟环境..."

if [ -d "$VENV_DIR" ]; then
    echo "  虚拟环境已存在: $VENV_DIR"
else
    python3.10 -m venv "$VENV_DIR"
    echo "  虚拟环境已创建: $VENV_DIR"
fi

# 激活虚拟环境
source "$VENV_DIR/bin/activate"
echo "  Python: $(python --version)"
echo "  pip:    $(pip --version)"

# ── 4. 安装依赖 ─────────────────────────────────────────────
echo ""
echo "[4/6] 安装 Python 依赖..."
pip install --upgrade pip setuptools wheel -q
pip install -r "$APP_DIR/requirements.txt" -q
echo "  依赖安装完成"

# ── 5. 安装 Playwright 浏览器 ────────────────────────────────
echo ""
echo "[5/6] 安装 Playwright 浏览器（Chromium）..."

# Playwright 需要的系统依赖
pip install playwright -q
python -m playwright install-deps chromium 2>/dev/null || sudo apt-get install -y -qq \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 2>/dev/null || true

python -m playwright install chromium
echo "  Playwright Chromium 安装完成"

# ── 6. 启动应用 ──────────────────────────────────────────────
echo ""
echo "[6/6] 启动 FastAPI 应用..."
echo "============================================"
echo " 访问地址: http://localhost:8000"
echo " API 文档: http://localhost:8000/docs"
echo " Ctrl+C 停止服务"
echo "============================================"
echo ""

cd "$APP_DIR"
exec python main.py
