#!/usr/bin/env bash
# =============================================================================
# PolicyAI Deploy Script
# Usage:
#   ./deploy/deploy.sh start    — start all services
#   ./deploy/deploy.sh stop     — stop all services
#   ./deploy/deploy.sh restart  — restart all services
#   ./deploy/deploy.sh status   — show service health
#   ./deploy/deploy.sh logs     — tail logs
#   ./deploy/deploy.sh build    — rebuild images
# =============================================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

COMPOSE_FILES="-f docker-compose.yml"
if [[ "${ENVIRONMENT:-development}" == "development" ]]; then
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.override.yml"
else
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.prod.yml"
fi

cmd_start() {
    echo "==> Starting PolicyAI services..."
    docker compose $COMPOSE_FILES up -d --wait
    echo "==> All services started."
    cmd_status
}

cmd_stop() {
    echo "==> Stopping PolicyAI services..."
    docker compose $COMPOSE_FILES down --remove-orphans
    echo "==> All services stopped."
}

cmd_restart() {
    echo "==> Restarting PolicyAI services..."
    docker compose $COMPOSE_FILES down --remove-orphans
    docker compose $COMPOSE_FILES up -d --wait
    echo "==> All services restarted."
    cmd_status
}

cmd_status() {
    echo "==> Service Status:"
    docker compose $COMPOSE_FILES ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
}

cmd_logs() {
    docker compose $COMPOSE_FILES logs -f --tail=100 "${@:-}"
}

cmd_build() {
    echo "==> Rebuilding images..."
    docker compose $COMPOSE_FILES build --no-cache
    echo "==> Build complete."
}

case "${1:-help}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_restart ;;
    status)  cmd_status ;;
    logs)    shift; cmd_logs "$@" ;;
    build)   cmd_build ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|build}"
        exit 1
        ;;
esac