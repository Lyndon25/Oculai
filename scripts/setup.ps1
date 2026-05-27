<#
.SYNOPSIS
    Oculai 一键初始化脚本 (Windows PowerShell)
.DESCRIPTION
    检查环境 -> 复制 .env -> 启动 PostgreSQL -> 安装依赖 -> 验证 MCP
.NOTES
    需要: Docker Desktop, Python >= 3.11, pip
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

function Write-Step($msg) { Write-Host "`n>>> $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg) { Write-Host "  [ERR] $msg" -ForegroundColor Red }

# ─── 1. 前置检查 ───
Write-Step "1/5 检查前置环境"

# Docker
try {
    $dockerVer = docker --version 2>$null
    if ($dockerVer) { Write-Ok "Docker: $dockerVer" }
    else { throw }
} catch {
    Write-Err "Docker 未安装或未启动。请先安装 Docker Desktop 并确保其运行。"
    exit 1
}

# Python
try {
    $pyVer = python --version 2>&1
    if ($pyVer -match "Python (\d+)\.(\d+)") {
        $major = [int]$matches[1]; $minor = [int]$matches[2]
        if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 11)) {
            Write-Ok "Python: $pyVer"
        } else {
            Write-Err "Python 版本过低 ($pyVer)，需要 >= 3.11"
            exit 1
        }
    }
} catch {
    Write-Err "Python 未安装。请安装 Python >= 3.11"
    exit 1
}

# pip
try {
    pip --version >$null 2>&1
    Write-Ok "pip: 可用"
} catch {
    Write-Err "pip 不可用"
    exit 1
}

# ─── 2. 环境变量 ───
Write-Step "2/5 检查环境变量"

$EnvFile = Join-Path $ProjectRoot "oculai-mcp" ".env"
$EnvExample = Join-Path $ProjectRoot "oculai-mcp" ".env.example"

if (Test-Path $EnvFile) {
    Write-Ok ".env 已存在，跳过复制"
} else {
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvFile
        Write-Ok ".env 已从 .env.example 复制"
        Write-Warn "请编辑 oculai-mcp/.env 填写你的 API Key（至少保留数据库默认配置即可启动）"
    } else {
        Write-Warn ".env.example 不存在，跳过"
    }
}

# ─── 3. 启动数据库 ───
Write-Step "3/5 启动 PostgreSQL"

$DbDir = Join-Path $ProjectRoot "oculai-db"
Set-Location $DbDir
try {
    docker compose up -d
    Start-Sleep -Seconds 8

    $container = docker ps --filter "name=oculai-postgres" --format "{{.Status}}"
    if ($container -and ($container -match "Up|healthy")) {
        Write-Ok "PostgreSQL 容器已启动 ($container)"
    } else {
        Write-Err "PostgreSQL 容器启动失败"
        docker compose logs --tail 30
        exit 1
    }
} catch {
    Write-Err "docker compose 执行失败: $_"
    exit 1
}

# ─── 4. 安装依赖 ───
Write-Step "4/5 安装 Python 依赖"

$McpDir = Join-Path $ProjectRoot "oculai-mcp"
Set-Location $McpDir
try {
    pip install -e . 2>&1 | ForEach-Object { "  $_" }
    Write-Ok "依赖安装完成"
} catch {
    Write-Err "pip install 失败: $_"
    exit 1
}

# 验证关键包
try {
    python -c "import fastmcp, asyncpg, pydantic; print('packages OK')" 2>$null
    Write-Ok "关键包验证通过 (fastmcp, asyncpg, pydantic)"
} catch {
    Write-Warn "关键包验证未通过，请检查 pip 输出"
}

# ─── 5. 验证 MCP Server ───
Write-Step "5/5 验证 MCP Server"

try {
    $output = python -c "from oculai_mcp.server import mcp; print('MCP import OK')" 2>&1
    if ($output -match "MCP import OK") {
        Write-Ok "MCP Server 可正常导入"
    } else {
        Write-Warn "MCP Server 导入输出异常: $output"
    }
} catch {
    Write-Warn "MCP Server 导入测试失败: $_"
}

# ─── 完成 ───
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Oculai 环境初始化完成" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  数据库:     PostgreSQL @ localhost:5432"
Write-Host "  环境文件:   oculai-mcp/.env"
Write-Host "  MCP Server: oculai-mcp/src/oculai_mcp/server.py"
Write-Host ""
Write-Host "  启动 MCP Server:" -ForegroundColor White
Write-Host "    cd oculai-mcp; fastmcp run src/oculai_mcp/server.py" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  下一步:" -ForegroundColor White
Write-Host "    1. 编辑 oculai-mcp/.env 填写 API Key（可选，可后续补充）"
Write-Host "    2. 在 Claude Code 中输入 /oculai-start 开始寻聘"
Write-Host ""
