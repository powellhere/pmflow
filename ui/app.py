
import sys
import os
import glob
import sqlite3
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
import pandas as pd

from pipeline.report import build_report
from ingest.douyin_csv_to_sqlite import ensure_schema, ingest_posts, ingest_comments

# ── 常量 ───────────────────────────────────────────────
DB_PATH = ROOT_DIR / "data" / "pmflow.db"
RAW_DIR = ROOT_DIR / "raw"
OUT_DIR = ROOT_DIR / "outputs"

# ════════════════════════════════════════════════════
# 页面配置
# ════════════════════════════════════════════════════
st.set_page_config(
    page_title="竞品分析工作台",
    page_icon="📋",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── 样式：Claude 风格 ──────────────────────────────────
st.markdown("""
<style>
/* 字体 & 背景 */
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", sans-serif;
    background-color: #ffffff;
    color: #1a1a1a;
}

/* 隐藏所有 Streamlit 默认控件 */
#MainMenu, footer, header { visibility: hidden; }
section[data-testid="stSidebar"] { display: none !important; }

/* 主内容区宽度限制 */
.main .block-container {
    max-width: 720px;
    padding: 2.5rem 1.5rem 4rem 1.5rem;
    margin: 0 auto;
}

/* 顶部导航栏 */
.topnav {
    display: flex;
    align-items: center;
    gap: 6px;
    padding-bottom: 1.8rem;
    border-bottom: 1px solid #ececec;
    margin-bottom: 2rem;
}
.topnav-logo {
    font-size: 1.05rem;
    font-weight: 700;
    color: #1a1a1a;
    margin-right: 1rem;
    letter-spacing: -0.01em;
}
.topnav a {
    font-size: 0.875rem;
    color: #666;
    text-decoration: none;
    padding: 5px 12px;
    border-radius: 6px;
    cursor: pointer;
    transition: background 0.15s;
}
.topnav a:hover { background: #f5f5f4; color: #1a1a1a; }
.topnav a.active { background: #f0f0ef; color: #1a1a1a; font-weight: 500; }

/* 页面标题 */
.pg-title {
    font-size: 1.45rem;
    font-weight: 650;
    color: #1a1a1a;
    margin: 0 0 0.25rem 0;
    letter-spacing: -0.02em;
}
.pg-sub {
    font-size: 0.875rem;
    color: #888;
    margin: 0 0 2rem 0;
}

/* 分割线 */
hr { border: none; border-top: 1px solid #ececec; margin: 1.8rem 0; }

/* stat 数字 */
.stat-row { display: flex; gap: 2.5rem; margin-bottom: 2rem; }
.stat-item { display: flex; flex-direction: column; gap: 2px; }
.stat-num { font-size: 1.8rem; font-weight: 700; letter-spacing: -0.03em; color: #1a1a1a; }
.stat-label { font-size: 0.8rem; color: #999; }

/* 关键词标签 */
.kw-tag {
    display: inline-block;
    background: #f5f5f4;
    border: 1px solid #e8e8e6;
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 0.85rem;
    color: #444;
    margin: 3px;
}

/* 文件状态行 */
.file-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 0;
    border-bottom: 1px solid #f0f0ef;
    font-size: 0.875rem;
    color: #444;
}
.file-row:last-child { border-bottom: none; }
.dot-ok   { width:8px; height:8px; border-radius:50%; background:#22c55e; flex-shrink:0; }
.dot-miss { width:8px; height:8px; border-radius:50%; background:#e5e7eb; flex-shrink:0; }

/* 报告区域 */
.report-wrap {
    background: #fafaf9;
    border: 1px solid #e8e8e6;
    border-radius: 12px;
    padding: 1.8rem 2rem;
    line-height: 1.85;
    font-size: 0.9rem;
    color: #2d2d2d;
    margin-top: 1.2rem;
}

/* 按钮覆盖 */
.stButton > button {
    background: #1a1a1a !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 8px !important;
    font-size: 0.875rem !important;
    padding: 0.5rem 1.2rem !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    transition: opacity 0.15s !important;
}
.stButton > button:hover { opacity: 0.82 !important; }

/* 次要按钮 */
.stDownloadButton > button {
    background: #ffffff !important;
    color: #1a1a1a !important;
    border: 1px solid #d4d4d0 !important;
    border-radius: 8px !important;
    font-size: 0.85rem !important;
}

/* input / select */
.stTextInput > div > div > input,
.stSelectbox > div > div {
    border-radius: 8px !important;
    border: 1px solid #d4d4d0 !important;
    font-size: 0.875rem !important;
    background: #ffffff !important;
}
.stTextInput > div > div > input:focus {
    border-color: #1a1a1a !important;
    box-shadow: none !important;
}

/* tab */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    border-bottom: 1px solid #ececec;
    background: transparent;
}
.stTabs [data-baseweb="tab"] {
    font-size: 0.875rem !important;
    color: #888 !important;
    padding: 6px 14px !important;
    border-radius: 6px 6px 0 0 !important;
    background: transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #1a1a1a !important;
    font-weight: 600 !important;
    border-bottom: 2px solid #1a1a1a !important;
}

/* 去掉 dataframe 默认 border */
.stDataFrame { border: 1px solid #ececec; border-radius: 8px; overflow: hidden; }

/* alert 扁平化 */
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


def db_stats():
    if not DB_PATH.exists():
        return {"posts": 0, "comments": 0, "keywords": []}
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM posts")
        n_posts = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM comments")
        n_comments = cur.fetchone()[0]
        cur.execute("SELECT keyword, COUNT(*) as c FROM posts GROUP BY keyword ORDER BY c DESC")
        keywords = [(r[0], r[1]) for r in cur.fetchall()]
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


# ════════════════════════════════════════════════════
# 初始化 session state
# ════════════════════════════════════════════════════
if "page" not in st.session_state:
    st.session_state.page = "overview"


# ════════════════════════════════════════════════════
# 顶部导航（用按钮模拟 tab）
# ════════════════════════════════════════════════════
stats = db_stats()

nav_items = {
    "overview":  "概览",
    "ingest":    "导入数据",
    "report":    "生成报告",
    "browse":    "数据浏览",
}

cols = st.columns([1.2] + [1] * len(nav_items))
with cols[0]:
    st.markdown("<span style='font-size:1rem;font-weight:700;line-height:2.4;'>📋 pmflow</span>",
                unsafe_allow_html=True)
for i, (key, label) in enumerate(nav_items.items()):
    with cols[i + 1]:
        is_active = st.session_state.page == key
        btn_style = "primary" if is_active else "secondary"
        if st.button(label, key=f"nav_{key}", type=btn_style, use_container_width=True):
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

1. **导入数据** — 把 `raw/` 目录的 CSV 写入本地 SQLite
2. **生成报告** — 选择关键词，生成信息雷达 · 需求洞察 · 数据解读三模块报告
3. **数据浏览** — 查看原始 posts / comments 数据
""")


# ════════════════════════════════════════════════════
# 导入数据
# ════════════════════════════════════════════════════
elif page == "ingest":
    st.markdown('<p class="pg-title">导入数据</p>', unsafe_allow_html=True)
    st.markdown('<p class="pg-sub">将 raw/ 目录下的 CSV 写入本地数据库</p>', unsafe_allow_html=True)

    contents_csv = latest_csv("search_contents_*.csv")
    comments_csv = latest_csv("search_comments_*.csv")

    # 文件检测
    for label, f in [("内容文件 (search_contents_*.csv)", contents_csv),
                     ("评论文件 (search_comments_*.csv)", comments_csv)]:
        dot = '<span class="dot-ok"></span>' if f else '<span class="dot-miss"></span>'
        name = f'<code style="font-size:.8rem;color:#555">{f.name}</code>' if f else '<span style="color:#bbb">未找到</span>'
        st.markdown(
            f'<div class="file-row">{dot}<span style="flex:1;color:#555">{label}</span>{name}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("")

    if not contents_csv and not comments_csv:
        st.warning("请将 CSV 文件放入项目 `raw/` 目录后重试")
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
        st.warning("数据库暂无数据，请先「导入数据」")
        st.stop()

    kw_options = [kw for kw, _ in stats["keywords"]] if stats["keywords"] else []

    col1, col2 = st.columns([4, 1])
    with col1:
        query = st.selectbox("关键词", kw_options) if kw_options else \
                st.text_input("关键词", placeholder="续火花")
    with col2:
        st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
        run = st.button("生成", type="primary", use_container_width=True)

    if run and query:
        # 清除旧报告
        st.session_state.pop("report_md", None)
        with st.spinner("分析中，请稍候 …"):
            try:
                md = build_report(query, db_path=str(DB_PATH))
                out_dir = OUT_DIR / query
                out_dir.mkdir(parents=True, exist_ok=True)
                fname = f"report_{datetime.now().strftime('%Y-%m-%d')}.md"
                fpath = out_dir / fname
                fpath.write_text(md, encoding="utf-8")
                st.session_state["report_md"]    = md
                st.session_state["report_fname"] = str(fpath)
                st.session_state["report_fname_short"] = fname
            except Exception as e:
                st.error(f"生成失败：{e}")

    if "report_md" in st.session_state:
        md    = st.session_state["report_md"]
        fname = st.session_state["report_fname_short"]

        col_a, col_b = st.columns([5, 1])
        col_a.caption(f"已保存 · `{st.session_state['report_fname']}`")
        with col_b:
            st.download_button(
                "⬇ 下载",
                data=md,
                file_name=fname,
                mime="text/markdown",
                use_container_width=True,
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

    if not DB_PATH.exists() or stats["posts"] == 0:
        st.warning("暂无数据，请先「导入数据」")
        st.stop()

    tab1, tab2 = st.tabs(["内容", "评论"])

    with tab1:
        col1, col2 = st.columns([4, 1])
        kw_f = col1.text_input("筛选", placeholder="关键词 / 标题 / 正文，留空显示全部", key="pf",
                               label_visibility="collapsed")
        limit = col2.selectbox("条数", [20, 50, 100], key="pl", label_visibility="collapsed")

        conn = get_conn()
        cur  = conn.cursor()
        if kw_f:
            cur.execute("""
                SELECT keyword, title, text, author_name,
                       like_count, comment_count, share_count
                FROM posts
                WHERE keyword LIKE ? OR title LIKE ? OR text LIKE ?
                ORDER BY comment_count DESC LIMIT ?
            """, (f"%{kw_f}%",) * 3 + (limit,))
        else:
            cur.execute("""
                SELECT keyword, title, text, author_name,
                       like_count, comment_count, share_count
                FROM posts ORDER BY comment_count DESC LIMIT ?
            """, (limit,))
        rows = cur.fetchall()
        conn.close()

        if rows:
            df = pd.DataFrame(rows, columns=["关键词", "标题", "正文", "作者", "点赞", "评论数", "分享"])
            df["正文"] = df["正文"].str[:50] + "…"
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("无符合条件的内容")

    with tab2:
        col1, col2 = st.columns([4, 1])
        kw_f2 = col1.text_input("筛选", placeholder="评论关键词，留空显示全部", key="cf",
                                label_visibility="collapsed")
        limit2 = col2.selectbox("条数", [50, 100, 200], key="cl", label_visibility="collapsed")

        conn = get_conn()
        cur  = conn.cursor()
        if kw_f2:
            cur.execute("""
                SELECT text, author_name, like_count, ip_location
                FROM comments WHERE text LIKE ?
                ORDER BY like_count DESC LIMIT ?
            """, (f"%{kw_f2}%", limit2))
        else:
            cur.execute("""
                SELECT text, author_name, like_count, ip_location
                FROM comments ORDER BY like_count DESC LIMIT ?
            """, (limit2,))
        rows = cur.fetchall()
        conn.close()

        if rows:
            df = pd.DataFrame(rows, columns=["评论内容", "用户", "点赞", "地区"])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("无符合条件的评论")
