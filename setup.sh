
#!/usr/bin/env bash
# ─────────────────────────────────────────────────
# pm-flow 首次部署脚本
# 用法：bash setup.sh
# ─────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── 检查 Python ───────────────────────────────────
if ! command -v python3 &>/dev/null; then
  error "未找到 python3，请先安装 Python 3.10+"
  exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Python 版本：$PY_VER"

# ── 创建虚拟环境 ──────────────────────────────────
if [ ! -d ".venv" ]; then
  info "创建虚拟环境 .venv ..."
  python3 -m venv .venv
else
  info ".venv 已存在，跳过创建"
fi

# ── 安装依赖 ──────────────────────────────────────
info "安装依赖..."
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q
info "✅ 依赖安装完成"

# ── 创建目录 ──────────────────────────────────────
mkdir -p raw data outputs logs
info "✅ 目录结构就绪"

# ── 完成提示 ──────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ 初始化完成${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo "下一步："
echo "  1. 把 CSV 放入 raw/ 目录"
echo "  2. bash start.sh        ← 启动服务（自动导入数据）"
echo "  3. 打开 http://localhost:8501"
echo ""
