#!/usr/bin/env bash
# =============================================================================
# EconAI 开发环境手动启动脚本
#
# 用法：
#   ./deploy/manualstart.sh infra       — 启动基础设施容器
#   ./deploy/manualstart.sh all         — 启动所有后端服务（后台运行）
#   ./deploy/manualstart.sh frontend    — 启动前端 dev server
#   ./deploy/manualstart.sh status      — 检查所有组件状态
#   ./deploy/manualstart.sh stop        — 停止所有本脚本启动的进程
#   ./deploy/manualstart.sh install     — 安装所有依赖
# =============================================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

# PID 跟踪文件
PID_DIR="$PROJECT_DIR/.pids"
mkdir -p "$PID_DIR"

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*"; }
step() { echo -e "${BLUE}[STEP]${NC} $*"; }

# =============================================================================
# 安装依赖
# =============================================================================
cmd_install() {
    step "安装后端 Python 依赖..."
    for dir in api-gateway services/*/; do
        log "Installing: $dir"
        (cd "$dir" && uv sync) || warn "安装失败: $dir"
    done

    step "安装前端依赖..."
    if [ -f frontend/package.json ]; then
        (cd frontend && npm install) || warn "前端依赖安装失败"
    fi

    log "依赖安装完成。"
}

# =============================================================================
# 启动基础设施容器
# =============================================================================
cmd_infra() {
    step "启动基础设施容器..."
    docker compose up -d postgres redis etcd minio minio-init milvus

    log "等待所有基础设施健康..."
    for svc in postgres redis minio milvus; do
        printf "  等待 %s..." "$svc"
        until docker compose ps "$svc" 2>/dev/null | grep -q "healthy"; do
            sleep 2
            printf "."
        done
        echo " OK"
    done

    log "基础设施全部就绪。"
    docker compose ps --format "table {{.Name}}\t{{.Status}}"
}

# =============================================================================
# 后台启动单个 uvicorn 服务
# =============================================================================
start_uvicorn() {
    local name="$1"
    local dir="$2"
    local module="$3"
    local port="$4"

    log "启动 $name (port $port)..."
    cd "$PROJECT_DIR/$dir"
    nohup uv run uvicorn "$module" --host 0.0.0.0 --port "$port" --reload \
        > "$PID_DIR/${name}.log" 2>&1 &
    echo $! > "$PID_DIR/${name}.pid"
    sleep 2

    if kill -0 "$(cat "$PID_DIR/${name}.pid")" 2>/dev/null; then
        log "  $name 启动成功 (PID $(cat "$PID_DIR/${name}.pid"))"
    else
        err "  $name 启动失败，查看日志: $PID_DIR/${name}.log"
    fi
}

start_celery() {
    local name="$1"
    local dir="$2"
    local app="$3"
    local queue="$4"
    local concurrency="${5:-2}"

    log "启动 $name Celery Worker ($queue)..."
    cd "$PROJECT_DIR/$dir"
    nohup uv run celery -A "$app" worker \
        --loglevel=INFO --concurrency="$concurrency" --queues="$queue" \
        > "$PID_DIR/${name}.log" 2>&1 &
    echo $! > "$PID_DIR/${name}.pid"
    sleep 2

    if kill -0 "$(cat "$PID_DIR/${name}.pid")" 2>/dev/null; then
        log "  $name 启动成功 (PID $(cat "$PID_DIR/${name}.pid"))"
    else
        err "  $name 启动失败，查看日志: $PID_DIR/${name}.log"
    fi
}

# =============================================================================
# 启动所有后端服务
# =============================================================================
cmd_all() {
    # 确保基础设施先启动
    cmd_infra

    echo ""

    # Wave 2: 无业务依赖服务（并行）
    step "启动 Wave 2 (user-service + llm-router + citation-service)..."
    start_uvicorn "user-service"      "services/user-service"        "app.main:app"                      8007
    start_uvicorn "llm-router"        "services/llm-router"          "llm_router.app:app"                8004
    start_uvicorn "citation-service"  "services/citation-service"    "citation_service.app:app"          8005

    # Wave 3: 数据处理服务
    step "启动 Wave 3 (document-service + output-service)..."
    start_uvicorn "document-service"  "services/document-service"    "document_service.app:app"          8001
    start_celery  "celery-document"   "services/document-service"    "document_service.celery_app"       "document" 2
    start_uvicorn "output-service"    "services/output-service"      "output_service.app:app"            8006

    # Wave 4: 知识库服务
    step "启动 Wave 4 (kb-service)..."
    start_uvicorn "kb-service"        "services/kb-service"          "kb_service.app:app"                8002

    # Wave 5: 编排服务
    step "启动 Wave 5 (orchestration-service)..."
    start_uvicorn "orchestration"     "services/orchestration-service" "orchestration_service.app:app"     8003
    start_celery  "celery-orch"       "services/orchestration-service" "orchestration_service.celery_app"  "orchestration" 4

    # Wave 6: API 网关
    step "启动 Wave 6 (api-gateway)..."
    start_uvicorn "api-gateway"       "api-gateway"                  "app.main:app"                      8000

    echo ""
    log "=========================================="
    log "所有后端服务已启动"
    log "=========================================="
    cmd_status
}

# =============================================================================
# 启动前端
# =============================================================================
cmd_frontend() {
    step "启动前端开发服务器..."
    cd "$PROJECT_DIR/frontend"

    nohup npm run dev > "$PID_DIR/frontend.log" 2>&1 &
    echo $! > "$PID_DIR/frontend.pid"

    sleep 3
    log "前端已启动: http://localhost:5173"
    log "日志: $PID_DIR/frontend.log"
}

# =============================================================================
# 状态检查
# =============================================================================
cmd_status() {
    echo ""
    log "=== 服务状态检查 ==="
    echo ""

    # 检查基础设施
    log "基础设施容器:"
    docker compose ps --format "  {{.Name}}  {{.Status}}" 2>/dev/null || echo "  (Docker Compose 不可用)"

    echo ""

    # 检查后端服务
    log "后端服务健康检查:"
    declare -A health_checks=(
        [8000]="API 网关"
        [8001]="文档服务"
        [8002]="知识库"
        [8003]="编排服务"
        [8004]="LLM 路由"
        [8005]="引用服务"
        [8006]="输出服务"
        [8007]="用户服务"
    )

    for port in 800{0..7}; do
        name="${health_checks[$port]}"
        if curl -s --max-time 2 "http://localhost:$port/health" > /dev/null 2>&1; then
            printf "  ${GREEN}✓${NC} %s (:%s)\n" "$name" "$port"
        else
            printf "  ${RED}✗${NC} %s (:%s)\n" "$name" "$port"
        fi
    done

    echo ""

    # 检查前端
    if curl -s --max-time 2 "http://localhost:5173" > /dev/null 2>&1; then
        log "前端: ${GREEN}运行中${NC} (http://localhost:5173)"
    else
        log "前端: ${RED}未启动${NC}"
    fi

    echo ""

    # 检查 Celery workers
    log "Celery Workers:"
    if [ -f "$PID_DIR/celery-document.pid" ] && kill -0 "$(cat "$PID_DIR/celery-document.pid")" 2>/dev/null; then
        printf "  ${GREEN}✓${NC} celery-document\n"
    else
        printf "  ${RED}✗${NC} celery-document\n"
    fi
    if [ -f "$PID_DIR/celery-orch.pid" ] && kill -0 "$(cat "$PID_DIR/celery-orch.pid")" 2>/dev/null; then
        printf "  ${GREEN}✓${NC} celery-orchestration\n"
    else
        printf "  ${RED}✗${NC} celery-orchestration\n"
    fi
}

# =============================================================================
# 停止服务
# =============================================================================
cmd_stop() {
    step "停止所有本脚本启动的进程..."

    for pidfile in "$PID_DIR"/*.pid; do
        [ -f "$pidfile" ] || continue
        local name
        name=$(basename "$pidfile" .pid)
        local pid
        pid=$(cat "$pidfile")

        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null && log "已停止 $name (PID $pid)" || warn "无法停止 $name"
        fi
        rm -f "$pidfile"
    done

    log "所有进程已停止。"
    log "日志文件保留在 $PID_DIR/"
}

# =============================================================================
# 查看日志
# =============================================================================
cmd_logs() {
    if [ $# -eq 0 ]; then
        echo "可用服务:"
        ls "$PID_DIR"/*.log 2>/dev/null | while read f; do
            echo "  $(basename "$f" .log)"
        done
        echo ""
        echo "用法: $0 logs <service-name>"
        exit 0
    fi

    local logfile="$PID_DIR/$1.log"
    if [ -f "$logfile" ]; then
        tail -f "$logfile"
    else
        err "日志文件不存在: $logfile"
        exit 1
    fi
}

# =============================================================================
# 入口
# =============================================================================
case "${1:-help}" in
    install)
        cmd_install
        ;;
    infra)
        cmd_infra
        ;;
    all)
        cmd_all
        ;;
    frontend)
        cmd_frontend
        ;;
    status)
        cmd_status
        ;;
    stop)
        cmd_stop
        ;;
    logs)
        shift
        cmd_logs "$@"
        ;;
    help|--help|-h)
        echo "EconAI 开发环境管理脚本"
        echo ""
        echo "用法: $0 {command}"
        echo ""
        echo "命令:"
        echo "  install     安装所有依赖（uv sync + npm install）"
        echo "  infra       启动基础设施容器（PG/Redis/Milvus/MinIO）"
        echo "  all         按依赖顺序启动所有后端服务（后台运行）"
        echo "  frontend    启动前端 Vite dev server"
        echo "  status      检查所有组件状态"
        echo "  stop        停止所有由本脚本启动的进程"
        echo "  logs <name> 查看指定服务日志"
        echo ""
        echo "示例:"
        echo "  $0 infra          # 先启动基础设施"
        echo "  $0 all            # 再启动所有后端"
        echo "  $0 frontend       # 最后启动前端"
        echo "  $0 status         # 检查状态"
        echo "  $0 logs user-service  # 查看用户服务日志"
        ;;
    *)
        err "未知命令: $1"
        echo "运行 '$0 help' 查看帮助"
        exit 1
        ;;
esac