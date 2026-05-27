#!/usr/bin/env bash
set -euo pipefail

# Oculai 一键初始化脚本 (Unix/Mac)
# 需要: Docker, Python >= 3.11, pip

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

step() { echo -e "\n${CYAN}>>> $1${NC}"; }
ok()   { echo -e "${GREEN}  [OK] $1${NC}"; }
warn() { echo -e "${YELLOW}  [WARN] $1${NC}"; }
err()  { echo -e "${RED}  [ERR] $1${NC}"; }

# ─── 1. 前置检查 ───
step "1/5 检查前置环境"

if command -v docker &> /dev/null; then
    ok "Docker: $(docker --version)"
else
    err "Docker 未安装或未启动"
    exit 1
fi

PY_VER=$(python3 --version 2>/dev/null || python --version 2>/dev/null || echo "")
if [[ -z "$PY_VER" ]]; then
    err "Python 未安装，需要 >= 3.11"
    exit 1
fi

# 简单版本检查
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
    if ! python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
        err "Python 版本过低 ($PY_VER)，需要 >= 3.11"
        exit 1
    fi
fi
ok "Python: $PY_VER"

if command -v pip3 &> /dev/null || command -v pip &> /dev/null; then
    ok "pip: 可用"
else
    err "pip 不可用"
    exit 1
fi

# ─── 2. 环境变量 ───
step "2/5 检查环境变量"

ENV_FILE="$PROJECT_ROOT/oculai-mcp/.env"
ENV_EXAMPLE="$PROJECT_ROOT/oculai-mcp/.env.example"

if [[ -f "$ENV_FILE" ]]; then
    ok ".env 已存在，跳过复制"
else
    if [[ -f "$ENV_EXAMPLE" ]]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        ok ".env 已从 .env.example 复制"
        warn "请编辑 oculai-mcp/.env 填写你的 API Key（至少保留数据库默认配置即可启动）"
    else
        warn ".env.example 不存在，跳过"
    fi
fi

# ─── 3. 启动数据库 ───
step "3/5 启动 PostgreSQL"

cd "$PROJECT_ROOT/oculai-db"
if docker compose up -d; then
    sleep 8
    CONTAINER_STATUS=$(docker ps --filter "name=oculai-postgres" --format "{{.Status}}" 2>/dev/null || true)
    if [[ "$CONTAINER_STATUS" == *"Up"* ]] || [[ "$CONTAINER_STATUS" == *"healthy"* ]]; then
        ok "PostgreSQL 容器已启动 ($CONTAINER_STATUS)"
    else
        err "PostgreSQL 容器启动失败"
        docker compose logs --tail 30
        exit 1
    fi
else
    err "docker compose 执行失败"
    exit 1
fi

# ─── 4. 安装依赖 ───
step "4/5 安装 Python 依赖"

cd "$PROJECT_ROOT/oculai-mcp"
if pip3 install -e . 2>/dev/null || pip install -e .; then
    ok "依赖安装完成"
else
    err "pip install 失败"
    exit 1
fi

if python3 -c "import fastmcp, asyncpg, pydantic" 2>/dev/null || python -c "import fastmcp, asyncpg, pydantic" 2>/dev/null; then
    ok "关键包验证通过 (fastmcp, asyncpg, pydantic)"
else
    warn "关键包验证未通过"
fi

# ─── 5. 验证 MCP Server ───
step "5/5 验证 MCP Server"

if python3 -c "from oculai_mcp.server import mcp" 2>/dev/null || python -c "from oculai_mcp.server import mcp" 2>/dev/null; then
    ok "MCP Server 可正常导入"
else
    warn "MCP Server 导入测试失败"
fi

# ─── 完成 ───
echo -e "\n${CYAN}========================================"
echo -e "  Oculai 环境初始化完成"
echo -e "========================================${NC}"
echo ""
echo "  数据库:     PostgreSQL @ localhost:5432"
echo "  环境文件:   oculai-mcp/.env"
echo "  MCP Server: oculai-mcp/src/oculai_mcp/server.py"
echo ""
echo "  启动 MCP Server:"
echo "    cd oculai-mcp && fastmcp run src/oculai_mcp/server.py"
echo ""
echo "  下一步:"
echo "    1. 编辑 oculai-mcp/.env 填写 API Key（可选，可后续补充）"
echo "    2. 在 Claude Code 中输入 /oculai-start 开始寻聘"
echo ""
