
#!/usr/bin/env bash
# ─────────────────────────────────────────────
# pmflow 一键启动脚本（后台守护版）
# 用法：bash start.sh [--skip-ingest]
# ─────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
VENV_UV="$SCRIPT_DIR/.venv/bin/uvicorn"
VENV_ST="$SCRIPT_DIR/.venv/bin/streamlit"

API_PORT=8000
UI_PORT=8501
DB_PATH="$SCRIPT_DIR/data/pmflow.db"
RAW_DIR="$SCRIPT_DIR/raw"
LOG_DIR="$SCRIPT_DIR/logs"

mkdir -p "$LOG_DIR" "$SCRIPT_DIR/data" "$SCRIPT_DIR/outputs"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── 检查 .venv ────────────────────────────────
if [ ! -f "$VENV_PYTHON" ]; then
  error ".venv 不存在，请先执行："
  echo "  python3 -m venv .venv && .venv/bin/pip install fastapi 'uvicorn[standard]' streamlit pandas requests"
  exit 1
fi

# ── 清理旧进程 ────────────────────────────────
info "清理旧进程..."
pkill -f "uvicorn api.server:app"      2>/dev/null && info "已停止旧 API" || true
pkill -f "streamlit run ui/app.py"     2>/dev/null && info "已停止旧 UI"  || true
sleep 1

# ── 自动导入最新 CSV ──────────────────────────
SKIP_INGEST=false
for arg in "$@"; do [ "$arg" = "--skip-ingest" ] && SKIP_INGEST=true; done

if [ "$SKIP_INGEST" = false ]; then
  CONTENTS=$(ls -t "$RAW_DIR"/search_contents_*.csv 2>/dev/null | head -1)
  COMMENTS=$(ls -t "$RAW_DIR"/search_comments_*.csv 2>/dev/null | head -1)
  if [ -n "$CONTENTS" ] && [ -n "$COMMENTS" ]; then
    info "导入 CSV → SQLite"
    "$VENV_PYTHON" -m ingest.douyin_csv_to_sqlite \
      --contents "$CONTENTS" \
      --comments "$COMMENTS" \
      --db       "$DB_PATH"
    info "✅ 数据导入完成"
  else
    warn "raw/ 目录下未找到 CSV，跳过导入"
  fi
else
  info "跳过 CSV 导入（--skip-ingest）"
fi

# ── 启动 FastAPI（后台）────────────────────────
info "启动 FastAPI (端口 $API_PORT)..."
nohup env PYTHONPATH="$SCRIPT_DIR" \
  "$VENV_UV" api.server:app \
    --host 0.0.0.0 \
    --port $API_PORT \
  > "$LOG_DIR/api.log" 2>&1 &
echo $! > "$LOG_DIR/api.pid"
info "API PID: $(cat $LOG_DIR/api.pid)"

# 等待 API 就绪（最多 15 秒）
info "等待 API 就绪..."
for i in $(seq 1 15); do
  if curl -s "http://localhost:$API_PORT/stats" > /dev/null 2>&1; then
    info "✅ FastAPI 已就绪"
    break
  fi
  sleep 1
  [ $i -eq 15 ] && warn "API 启动超时，请检查 logs/api.log"
done

# ── 启动 Streamlit UI（后台）─────────────────
info "启动 Streamlit UI (端口 $UI_PORT)..."
nohup env PYTHONPATH="$SCRIPT_DIR" \
  "$VENV_ST" run ui/app.py \
    --server.port $UI_PORT \
    --server.address 0.0.0.0 \
    --server.headless true \
  > "$LOG_DIR/ui.log" 2>&1 &
echo $! > "$LOG_DIR/ui.pid"
info "UI  PID: $(cat $LOG_DIR/ui.pid)"

sleep 2

# ── 启动成功提示 ──────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  🚀 pmflow 已在后台启动${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "  📊 UI   → ${GREEN}http://localhost:$UI_PORT${NC}"
echo -e "  🔌 API  → ${GREEN}http://localhost:$API_PORT${NC}"
echo -e "  📖 Docs → ${GREEN}http://localhost:$API_PORT/docs${NC}"
echo -e "  📋 Log  → $LOG_DIR/"
echo -e ""
echo -e "  停止服务：${YELLOW}bash stop.sh${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
