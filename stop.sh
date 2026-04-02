
#!/usr/bin/env bash
# pm-flow 停止脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }

# 通过 PID 文件停止
for svc in api ui; do
  PID_FILE="$LOG_DIR/$svc.pid"
  if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
      kill "$PID" && info "已停止 $svc (PID $PID)"
    else
      warn "$svc (PID $PID) 已不在运行"
    fi
    rm -f "$PID_FILE"
  fi
done

# 兜底：按进程名 kill
pkill -f "uvicorn api.server:app"  2>/dev/null && info "已清理残留 API 进程" || true
pkill -f "streamlit run ui/app.py" 2>/dev/null && info "已清理残留 UI 进程"  || true

echo -e "${GREEN}✅ 竞品分析工作台 已完全停止${NC}"
