#!/bin/bash

# ==========================================
# HydroAgent 一键启停脚本 (macOS / Linux)
# ==========================================

echo "🚀 开始启动 HydroAgent 系统链路..."

# 1. 启动并配置 Python 后端环境
echo "⚙️ [1/2] 准备核心调度中心..."
if [ ! -d ".venv" ]; then
    echo "   ⚠️ 未找到 .venv 虚拟环境，开始自动创建..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

# 在后台启动后端
python src/main.py &
BACKEND_PID=$!
echo "   ✅ 后端服务启动成功 (PID: $BACKEND_PID)"

# 2. 启动并配置 React 前端环境
echo "💻 [2/2] 准备现代监控中心 (React 18)..."
cd frontend || { echo "   ❌ 找不到 frontend 目录"; exit 1; }

if [ ! -d "node_modules" ]; then
    echo "   ⚠️ 尚未安装 npm 依赖，开始拉取 (这可能需要两分钟)..."
    npm install
fi

# 在后台启动前端
npm run dev -- --host &
FRONTEND_PID=$!
echo "   ✅ 前端服务器启动成功 (PID: $FRONTEND_PID)"

# 3. 拦截 Ctrl+C 并优雅退出
trap "echo -e '\n🛑 收到中断信号，正在安全关闭所有环境...'; kill $BACKEND_PID $FRONTEND_PID; echo '👋 再见!'; exit" SIGINT SIGTERM

echo "============================================"
echo "✨ 所有服务已拉起并处于监听状态"
echo "👉 前台控制端: http://localhost:5173"
echo "👉 按下 [Ctrl + C] 即可一键停止前后端"
echo "============================================"

# 持久等待
wait
