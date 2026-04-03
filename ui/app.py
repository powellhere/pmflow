
import sys
import os
import glob
import time
import sqlite3
import requests
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
import pandas as pd

from pipeline.report import build_report
from ingest.douyin_csv_to_sqlite import ensure_schema, ingest_posts, ingest_comments

# ── 常量 ───────────────────────────────────────────────
DB_PATH  = ROOT_DIR / "data" / "pmflow.db"
RAW_DIR  = ROOT_DIR / "raw"
OUT_DIR  = ROOT_DIR / "outputs"
API_BASE = "http://127.0.0.1:8000"

# ── 启动时确保数据库 & 表存在 ──────────────────────────
os.makedirs(str(DB_PATH.parent), exist_ok=True)
_init_conn = sqlite3.connect(str(DB_PATH))
ensure_schema(_init_conn)
_init_conn.close()

# ════════════════════════════════════════════════════
# 页面配置
# ════════════════════════════════════════════════════
st.set_page_config(
    page_title="竞品分析工作台",
    page_icon="📋",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", sans-serif;
    background-color: #ffffff;
    color: #1a1a1a;
}
#MainMenu, footer, header { visibility: hidden; }
section[data-testid="stSidebar"] { display: none !important; }
.main .block-container {
    max-width: 720px;
    padding: 2.5rem 1.5rem 4rem 1.5rem;
    margin: 0 auto;
}
.pg-title {
    font-size: 1.45rem; font-weight: 650; color: #1a1a1a;
    margin: 0 0 0.25rem 0; letter-spacing: -0.02em;
}
.pg-sub { font-size: 0.875rem; color: #888; margin: 0 0 2rem 0; }
hr { border: none; border-top: 1px solid #ececec; margin: 1.8rem 0; }
.stat-row { display: flex; gap: 2.5rem; margin-bottom: 2rem; }
.stat-item { display: flex; flex-direction: column; gap: 2px; }
.stat-num { font-size: 1.8rem; font-weight: 700; letter-spacing: -0.03em; color: #1a1a1a; }
.stat-label { font-size: 0.8rem; color: #999; }
.kw-tag {
    display: inline-block; background: #f5f5f4; border: 1px solid #e8e8e6;
    border-radius: 20px; padding: 4px 14px; font-size: 0.85rem; color: #444; margin: 3px;
}
.file-row {
    display: flex; align-items: center; gap: 10px;
    padding: 12px 0; border-bottom: 1px solid #f0f0ef; font-size: 0.875rem; color: #444;
}
.file-row:last-child { border-bottom: none; }
.dot-ok   { width:8px; height:8px; border-radius:50%; background:#22c55e; flex-shrink:0; }
.dot-miss { width:8px; height:8px; border-radius:50%; background:#e5e7eb; flex-shrink:0; }
.report-wrap {
    background: #fafaf9; border: 1px solid #e8e8e6; border-radius: 12px;
    padding: 1.8rem 2rem; line-height: 1.85; font-size: 0.9rem;
    color: #2d2d2d; margin-top: 1.2rem;
}
.log-box {
    background: #0f1117; border-radius: 8px; padding: 1rem 1.2rem;
    font-family: "SF Mono", "Fira Code", monospace; font-size: 0.78rem;
    color: #c9d1d9; line-height: 1.7; max-height: 320px;
    overflow-y: auto; white-space: pre-wrap; word-break: break-all;
}
.status-badge {
    display: inline-block; border-radius: 20px; padding: 3px 12px;
    font-size: 0.8rem; font-weight: 500;
}
.badge-running { background: #fef3c7; color: #92400e; }
.badge-done    { background: #d1fae5; color: #065f46; }
.badge-pending { background: #f3f4f6; color: #6b7280; }
.badge-error   { background: #fee2e2; color: #991b1b; }
.crawl-config-box {
    background: #fafaf9; border: 1px solid #e8e8e6;
    border-radius: 10px; padding: 1.2rem 1.4rem; margin-bottom: 1.2rem;
}
.crawl-config-label {
    font-size: 0.75rem; color: #999; font-weight: 500;
    text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.6rem;
}
.progress-step {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 0; font-size: 0.875rem; color: #555;
}
.step-dot-done  { width:8px; height:8px; border-radius:50%; background:#22c55e; flex-shrink:0; }
.step-dot-active{ width:8px; height:8px; border-radius:50%; background:#f59e0b; flex-shrink:0;
                  box-shadow: 0 0 0 3px #fef3c7; }
.step-dot-idle  { width:8px; height:8px; border-radius:50%; background:#e5e7eb; flex-shrink:0; }
.stButton > button[kind="primary"] {
    background: #1a1a1a !important; color: #fff !important;
    border: none !important; border-radius: 8px !important;
    font-size: 0.875rem !important; padding: 0.5rem 1.2rem !important;
    font-weight: 500 !important; cursor: pointer !important;
    transition: opacity 0.15s !important;
}
.stButton > button:hover { opacity: 0.82 !important; }
.stButton > button:disabled { opacity: 0.35 !important; }
.stDownloadButton > button {
    background: #fff !important; color: #1a1a1a !important;
    border: 1px solid #d4d4d0 !important; border-radius: 8px !important;
    font-size: 0.85rem !important;
}
.stTextInput > div > div > input,
.stSelectbox > div > div {
    border-radius: 8px !important; border: 1px solid #d4d4d0 !important;
    font-size: 0.875rem !important; background: #fff !important;
}
.stTextInput > div > div > input:focus {
    border-color: #1a1a1a !important; box-shadow: none !important;
}
.stTabs [data-baseweb="tab-list"] {
    gap: 4px; border-bottom: 1px solid #ececec; background: transparent;
}
.stTabs [data-baseweb="tab"] {
    font-size: 0.875rem !important; color: #888 !important;
    padding: 6px 14px !important; border-radius: 6px 6px 0 0 !important;
    background: transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #1a1a1a !important; font-weight: 600 !important;
    border-bottom: 2px solid #1a1a1a !important;
}
.stDataFrame { border: 1px solid #ececec; border-radius: 8px; overflow: hidden; }
.stAlert { border-radius: 8px !important; font-size: 0.875rem !important; }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════
# 工具函数
# ════════════════════════════════════════════════════

def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_table_columns(conn, table_name: str) -> list[str]:
    """返回指定表的所有列名，表不存在时返回空列表"""
    try:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table_name})")
        return [row[1] for row in cur.fetchall()]
    except Exception:
        return []


def db_stats():
    try:
        conn = get_conn()
        cur  = conn.cursor()
        # 先确认表存在
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cur.fetchall()}

        n_posts    = 0
        n_comments = 0
        keywords   = []

        if "posts" in tables:
            cur.execute("SELECT COUNT(*) FROM posts")
            n_posts = cur.fetchone()[0]
            cur.execute("SELECT keyword, COUNT(*) as c FROM posts GROUP BY keyword ORDER BY c DESC")
            keywords = [(r[0], r[1]) for r in cur.fetchall()]

        if "comments" in tables:
            cur.execute("SELECT COUNT(*) FROM comments")
            n_comments = cur.fetchone()[0]

        conn.close()
        return {"posts": n_posts, "comments": n_comments, "keywords": keywords}
    except Exception:
        return {"posts": 0, "comments": 0, "keywords": []}


def latest_csv(pattern):
    files = sorted(glob.glob(str(RAW_DIR / pattern)))
    return Path(files[-1]) if files else None


def do_ingest():
    contents = latest_csv("search_contents_*.csv")
    comments = latest_csv("search_comments_*.csv")
    if not contents and not comments:
        return None, "raw/ 目录下未找到 CSV 文件"
    os.makedirs(str(DB_PATH.parent), exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    ensure_schema(conn)
    n_p = ingest_posts(conn, str(contents)) if contents else 0
    n_c = ingest_comments(conn, str(comments)) if comments else 0
    conn.close()
    return {"posts": n_p, "comments": n_c}, None


def api_post(path: str, payload: dict) -> dict:
    try:
        r = requests.post(f"{API_BASE}{path}", json=payload, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def api_get(path: str) -> dict:
    try:
        r = requests.get(f"{API_BASE}{path}", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def check_api_alive() -> bool:
    try:
        r = requests.get(f"{API_BASE}/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


# ════════════════════════════════════════════════════
# 初始化 session state
# ════════════════════════════════════════════════════

for key, default in [
    ("page",               "overview"),
    ("task_id",            None),
    ("task_done",          False),
    ("report_md",          None),
    ("report_fname",       None),
    ("report_fname_short", None),
    ("crawl_stopped",      False),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ════════════════════════════════════════════════════
# 顶部导航
# ════════════════════════════════════════════════════

stats = db_stats()

nav_items = {
    "overview": "概览",
    "crawl":    "爬取数据",
    "ingest":   "导入数据",
    "report":   "生成报告",
    "browse":   "数据浏览",
}

cols = st.columns([1.2] + [1] * len(nav_items))
with cols[0]:
    st.markdown(
        "<span style='font-size:1rem;font-weight:700;line-height:2.4;'>📋 pmflow</span>",
        unsafe_allow_html=True,
    )
for i, (key, label) in enumerate(nav_items.items()):
    with cols[i + 1]:
        is_active = st.session_state.page == key
        if st.button(label, key=f"nav_{key}",
                     type="primary" if is_active else "secondary",
                     use_container_width=True):
            st.session_state.page = key
            st.rerun()

st.markdown("<hr>", unsafe_allow_html=True)
page = st.session_state.page


# ════════════════════════════════════════════════════
# 概览
# ════════════════════════════════════════════════════

if page == "overview":
    st.markdown('<p class="pg-title">pmflow</p>', unsafe_allow_html=True)
    st.markdown('<p class="pg-sub">竞品分析数据工作台 · 本地离线版</p>', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="stat-row">
        <div class="stat-item">
            <span class="stat-num">{stats['posts']:,}</span>
            <span class="stat-label">内容总数</span>
        </div>
        <div class="stat-item">
            <span class="stat-num">{stats['comments']:,}</span>
            <span class="stat-label">评论总数</span>
        </div>
        <div class="stat-item">
            <span class="stat-num">{len(stats['keywords'])}</span>
            <span class="stat-label">关键词</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if stats["keywords"]:
        st.markdown("**已有关键词**")
        tags_html = "".join(
            f'<span class="kw-tag">🔑 {kw or "（空）"} &nbsp;<span style="color:#bbb">{cnt}</span></span>'
            for kw, cnt in stats["keywords"]
        )
        st.markdown(tags_html, unsafe_allow_html=True)
        st.markdown("")

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("""
**使用步骤**

1. **爬取数据** — 选平台 + 输关键词，一键调用 MediaCrawler 自动抓取
2. **导入数据** — 把 `raw/` 目录的 CSV 写入 SQLite（爬取后自动触发，也可手动补录）
3. **生成报告** — 选择关键词，生成信息雷达 · 需求洞察 · 数据解读三模块报告
4. **数据浏览** — 查看原始 posts / comments 数据
""")


# ════════════════════════════════════════════════════
# 爬取数据
# ════════════════════════════════════════════════════

elif page == "crawl":
    st.markdown('<p class="pg-title">爬取数据</p>', unsafe_allow_html=True)
    st.markdown('<p class="pg-sub">调用 MediaCrawler 抓取社交平台内容，爬完自动导入数据库</p>',
                unsafe_allow_html=True)

    if not check_api_alive():
        st.error("⚠️ 后端未启动，请先在终端执行：")
        st.code("cd ~/pmflow && uvicorn api.server:app --reload", language="bash")
        st.stop()

    PLATFORM_OPTIONS = {
        "B站":   "bili",
        "小红书": "xhs",
        "抖音":  "dy",
        "微博":  "wb",
        "快手":  "ks",
        "贴吧":  "tieba",
        "知乎":  "zhihu",
    }

    if not st.session_state.task_id:
        st.markdown('<div class="crawl-config-box">', unsafe_allow_html=True)
        st.markdown('<div class="crawl-config-label">平台与关键词</div>', unsafe_allow_html=True)

        col1, col2 = st.columns([2, 3])
        with col1:
            platform_label = st.selectbox("平台", list(PLATFORM_OPTIONS.keys()),
                                           key="crawl_platform", label_visibility="collapsed")
            platform_val = PLATFORM_OPTIONS[platform_label]
        with col2:
            keywords_raw = st.text_input(
                "关键词", placeholder="无线耳机, 降噪耳机（逗号分隔）",
                key="crawl_keywords", label_visibility="collapsed",
            )

        st.markdown('<div style="height:0.6rem"></div>', unsafe_allow_html=True)
        st.markdown('<div class="crawl-config-label">高级设置</div>', unsafe_allow_html=True)

        col3, col4, col5 = st.columns(3)
        with col3:
            max_comments = st.number_input("每帖最多评论数", min_value=10, max_value=500,
                                            value=50, step=10)
        with col4:
            get_sub = st.checkbox("抓取子评论", value=False)
        with col5:
            login_type = st.selectbox("登录方式", ["qrcode", "cookie"], index=0)

        st.markdown('</div>', unsafe_allow_html=True)

        keywords_ok = bool(keywords_raw.strip())
        if not keywords_ok:
            st.caption("请输入至少一个关键词")

        if st.button("🚀 开始爬取", type="primary", disabled=not keywords_ok):
            keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
            payload  = {
                "keywords":         keywords,
                "platform":         platform_val,
                "login_type":       login_type,
                "max_comments":     int(max_comments),
                "get_comment":      True,
                "get_sub_comment":  get_sub,
                "save_data_option": "csv",
            }
            resp = api_post("/crawl", payload)
            if "task_id" in resp:
                st.session_state.task_id       = resp["task_id"]
                st.session_state.task_done     = False
                st.session_state.crawl_stopped = False
                st.rerun()
            else:
                st.error(f"启动失败：{resp.get('error', resp)}")

    else:
        task_id = st.session_state.task_id
        task    = api_get(f"/crawl/{task_id}")

        if task.get("error"):
            st.error(f"无法获取任务状态：{task['error']}")
            if st.button("重新开始", key="reset_task"):
                st.session_state.task_id = None
                st.rerun()
        else:
            status   = task.get("status", "unknown")
            platform = task.get("platform", "")
            keywords = task.get("keywords", [])

            badge_map = {
                "running": ("badge-running", "⏳ 爬取中"),
                "done":    ("badge-done",    "✅ 已完成"),
                "pending": ("badge-pending", "🕐 等待中"),
                "error":   ("badge-error",   "❌ 出错"),
                "stopped": ("badge-error",   "⏹ 已停止"),
            }
            badge_cls, badge_txt = badge_map.get(status, ("badge-error", status))

            col_badge, col_stop = st.columns([5, 1])
            with col_badge:
                st.markdown(
                    f'<span class="status-badge {badge_cls}">{badge_txt}</span>'
                    f'<span style="font-size:.8rem;color:#999;margin-left:10px">'
                    f'{platform.upper()} · {" / ".join(keywords)}</span>',
                    unsafe_allow_html=True,
                )
            with col_stop:
                if status in ("running", "pending"):
                    if st.button("停止", key="stop_btn"):
                        api_post(f"/crawl/{task_id}/stop", {})
                        st.rerun()

            st.markdown('<div style="height:.8rem"></div>', unsafe_allow_html=True)

            steps = task.get("steps", [])
            if steps:
                steps_html = ""
                for s in steps:
                    if s["state"] == "done":
                        dot = "step-dot-done"
                    elif s["state"] == "active":
                        dot = "step-dot-active"
                    else:
                        dot = "step-dot-idle"
                    steps_html += (
                        f'<div class="progress-step">'
                        f'<span class="{dot}"></span>{s["label"]}</div>'
                    )
                st.markdown(steps_html, unsafe_allow_html=True)
                st.markdown('<div style="height:.5rem"></div>', unsafe_allow_html=True)

            if task.get("login_type") == "qrcode" and status == "running":
                qr_url = f"{API_BASE}/crawl/{task_id}/qrcode"
                try:
                    qr_resp = requests.get(qr_url, timeout=3)
                    if qr_resp.status_code == 200:
                        st.markdown(
                            '<p style="font-size:.875rem;font-weight:600;margin-bottom:.4rem">'
                            '📱 请用手机扫描二维码登录</p>',
                            unsafe_allow_html=True,
                        )
                        st.image(qr_resp.content, width=180)
                except Exception:
                    st.caption("二维码尚未生成，请稍候…")

            log_lines = task.get("log", [])
            if log_lines:
                log_html = "\n".join(log_lines[-60:])
                st.markdown(
                    f'<div class="log-box">{log_html}</div>',
                    unsafe_allow_html=True,
                )

            if status == "done":
                imported = task.get("imported")
                if imported:
                    st.success(
                        f"🎉 爬取 & 导入完成  |  "
                        f"内容 **{imported.get('posts', 0)}** 条  ·  "
                        f"评论 **{imported.get('comments', 0)}** 条"
                    )
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("📊 去生成报告", key="goto_report"):
                        st.session_state.page    = "report"
                        st.session_state.task_id = None
                        st.rerun()
                with col_b:
                    if st.button("🔄 再爬一次", key="crawl_again"):
                        st.session_state.task_id = None
                        st.rerun()

            elif status in ("error", "stopped"):
                err_msg = task.get("error", "")
                if err_msg:
                    st.error(f"错误详情：{err_msg}")
                if st.button("重新配置", key="reconfigure"):
                    st.session_state.task_id = None
                    st.rerun()

            elif status in ("running", "pending"):
                time.sleep(3)
                st.rerun()


# ════════════════════════════════════════════════════
# 导入数据
# ════════════════════════════════════════════════════

elif page == "ingest":
    st.markdown('<p class="pg-title">导入数据</p>', unsafe_allow_html=True)
    st.markdown('<p class="pg-sub">将 raw/ 目录下的 CSV 写入本地数据库</p>', unsafe_allow_html=True)

    contents_csv = latest_csv("search_contents_*.csv")
    comments_csv = latest_csv("search_comments_*.csv")

    for label, f in [
        ("内容文件 (search_contents_*.csv)", contents_csv),
        ("评论文件 (search_comments_*.csv)", comments_csv),
    ]:
        dot  = '<span class="dot-ok"></span>' if f else '<span class="dot-miss"></span>'
        name = f'<code style="font-size:.8rem;color:#555">{f.name}</code>' if f \
               else '<span style="color:#bbb">未找到</span>'
        st.markdown(
            f'<div class="file-row">{dot}<span style="flex:1;color:#555">{label}</span>{name}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("")

    if not contents_csv and not comments_csv:
        st.warning("请将 CSV 文件放入项目 `raw/` 目录后重试，或使用「爬取数据」自动获取")
    else:
        if st.button("开始导入", type="primary"):
            with st.spinner("导入中..."):
                result, err = do_ingest()
            if err:
                st.error(err)
            else:
                st.success(f"✅ 导入完成 — 内容 **{result['posts']}** 条 · 评论 **{result['comments']}** 条")
                st.session_state.page = "overview"
                st.rerun()


# ════════════════════════════════════════════════════
# 生成报告
# ════════════════════════════════════════════════════

elif page == "report":
    st.markdown('<p class="pg-title">生成报告</p>', unsafe_allow_html=True)
    st.markdown('<p class="pg-sub">选择关键词，自动生成三模块舆情报告</p>', unsafe_allow_html=True)

    if stats["posts"] == 0:
        st.warning("数据库暂无数据，请先「爬取数据」或「导入数据」")
        st.stop()

    kw_options = [kw for kw, _ in stats["keywords"]] if stats["keywords"] else []

    col1, col2 = st.columns([4, 1])
    with col1:
        query = st.selectbox("关键词", kw_options) if kw_options else \
                st.text_input("关键词", placeholder="无线耳机")
    with col2:
        st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
        run = st.button("生成", type="primary", use_container_width=True)

    if run and query:
        st.session_state.pop("report_md", None)
        with st.spinner("分析中，请稍候 …"):
            try:
                md      = build_report(query, db_path=str(DB_PATH))
                out_dir = OUT_DIR / query
                out_dir.mkdir(parents=True, exist_ok=True)
                fname   = f"report_{datetime.now().strftime('%Y-%m-%d')}.md"
                fpath   = out_dir / fname
                fpath.write_text(md, encoding="utf-8")
                st.session_state["report_md"]          = md
                st.session_state["report_fname"]       = str(fpath)
                st.session_state["report_fname_short"] = fname
            except Exception as e:
                st.error(f"生成失败：{e}")

    if st.session_state.get("report_md"):
        md    = st.session_state["report_md"]
        fname = st.session_state["report_fname_short"]

        col_a, col_b = st.columns([5, 1])
        col_a.caption(f"已保存 · `{st.session_state['report_fname']}`")
        with col_b:
            st.download_button(
                "⬇ 下载", data=md, file_name=fname,
                mime="text/markdown", use_container_width=True,
            )

        st.markdown('<div class="report-wrap">', unsafe_allow_html=True)
        st.markdown(md)
        st.markdown('</div>', unsafe_allow_html=True)


# ════════════════════════════════════════════════════
# 数据浏览
# ════════════════════════════════════════════════════

elif page == "browse":
    st.markdown('<p class="pg-title">数据浏览</p>', unsafe_allow_html=True)
    st.markdown('<p class="pg-sub">查看数据库原始内容与评论</p>', unsafe_allow_html=True)

    if stats["posts"] == 0:
        st.warning("暂无数据，请先「爬取数据」或「导入数据」")
        st.stop()

    tab1, tab2 = st.tabs(["内容", "评论"])

    # ── 动态探测 posts 表的实际列名 ──────────────────────
    _conn         = get_conn()
    posts_cols    = get_table_columns(_conn, "posts")
    comments_cols = get_table_columns(_conn, "comments")
    _conn.close()

    # 兼容不同字段命名（text / desc / content / note_text）
    def pick_col(candidates: list[str], cols: list[str]) -> str | None:
        for c in candidates:
            if c in cols:
                return c
        return None

    post_text_col    = pick_col(["text", "desc", "content", "note_text", "body"], posts_cols)
    comment_text_col = pick_col(["text", "content", "comment_text", "body"],      comments_cols)

    with tab1:
        col1, col2 = st.columns([4, 1])
        kw_f  = col1.text_input("筛选", placeholder="关键词 / 标题 / 正文，留空显示全部",
                                 key="pf", label_visibility="collapsed")
        limit = col2.selectbox("条数", [20, 50, 100], key="pl", label_visibility="collapsed")

        # 动态组装 SELECT 列表
        title_col  = pick_col(["title", "note_title"], posts_cols) or "''"
        author_col = pick_col(["author_name", "nickname", "user_name"], posts_cols) or "''"
        like_col   = pick_col(["like_count", "liked_count"], posts_cols) or "0"
        cmt_col    = pick_col(["comment_count"], posts_cols) or "0"
        share_col  = pick_col(["share_count"], posts_cols) or "0"
        text_sel   = post_text_col or "''"

        select_clause = f"keyword, {title_col}, {text_sel}, {author_col}, {like_col}, {cmt_col}, {share_col}"

        try:
            conn = get_conn()
            cur  = conn.cursor()
            if kw_f and post_text_col:
                cur.execute(f"""
                    SELECT {select_clause} FROM posts
                    WHERE keyword LIKE ? OR {title_col} LIKE ? OR {text_sel} LIKE ?
                    ORDER BY {cmt_col} DESC LIMIT ?
                """, (f"%{kw_f}%",) * 3 + (limit,))
            else:
                cur.execute(f"""
                    SELECT {select_clause} FROM posts
                    ORDER BY {cmt_col} DESC LIMIT ?
                """, (limit,))
            rows = cur.fetchall()
            conn.close()

            if rows:
                df = pd.DataFrame(rows, columns=["关键词", "标题", "正文", "作者", "点赞", "评论数", "分享"])
                df["正文"] = df["正文"].astype(str).str[:50] + "…"
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("无符合条件的内容")
        except Exception as e:
            st.error(f"查询出错：{e}")
            st.caption(f"posts 表实际列名：{posts_cols}")

    with tab2:
        col1, col2 = st.columns([4, 1])
        kw_f2  = col1.text_input("筛选", placeholder="评论关键词，留空显示全部",
                                  key="cf", label_visibility="collapsed")
        limit2 = col2.selectbox("条数", [50, 100, 200], key="cl", label_visibility="collapsed")

        c_author = pick_col(["author_name", "nickname", "user_name"], comments_cols) or "''"
        c_like   = pick_col(["like_count", "liked_count"],            comments_cols) or "0"
        c_ip     = pick_col(["ip_location", "location"],              comments_cols) or "''"
        c_text   = comment_text_col or "''"

        try:
            conn = get_conn()
            cur  = conn.cursor()
            if kw_f2 and comment_text_col:
                cur.execute(f"""
                    SELECT {c_text}, {c_author}, {c_like}, {c_ip}
                    FROM comments WHERE {c_text} LIKE ?
                    ORDER BY {c_like} DESC LIMIT ?
                """, (f"%{kw_f2}%", limit2))
            else:
                cur.execute(f"""
                    SELECT {c_text}, {c_author}, {c_like}, {c_ip}
                    FROM comments ORDER BY {c_like} DESC LIMIT ?
                """, (limit2,))
            rows = cur.fetchall()
            conn.close()

            if rows:
                df = pd.DataFrame(rows, columns=["评论内容", "用户", "点赞", "地区"])
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("无符合条件的评论")
        except Exception as e:
            st.error(f"查询出错：{e}")
            st.caption(f"comments 表实际列名：{comments_cols}")
