
# api/server.py
import os
import sys
import glob
import asyncio
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── 路径配置（所有路径都基于项目根目录）─────────────────────
ROOT_DIR    = Path(__file__).parent.parent        # /Users/macbook/pm flow/
DB_PATH     = ROOT_DIR / "data" / "pmflow.db"
RAW_DIR     = ROOT_DIR / "raw"                    # CSV 原始数据目录
OUTPUTS_DIR = ROOT_DIR / "outputs"
CRAWLER_DIR = ROOT_DIR / "media_crawler"          # MediaCrawler 根目录

# ── 把项目根目录加入 Python 路径，才能 import pipeline/ingest ─
sys.path.insert(0, str(ROOT_DIR))

from pipeline.report   import build_report
from pipeline.retrieve import fetch_bundle
from ingest.douyin_csv_to_sqlite import (
    ensure_schema,
    ingest_posts,
    ingest_comments,
)

# ── 确保目录存在 ──────────────────────────────────────────
os.makedirs(str(DB_PATH.parent), exist_ok=True)
os.makedirs(str(OUTPUTS_DIR), exist_ok=True)

app = FastAPI(title="pmflow API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 任务状态（内存缓存）───────────────────────────────────
tasks: dict[str, dict] = {}


# ════════════════════════════════════════════════════════
# Pydantic Schema
# ════════════════════════════════════════════════════════

class CrawlRequest(BaseModel):
    keywords:     list[str]
    platform:     str = "douyin"    # douyin / xhs / bilibili / weibo
    max_posts:    int = 20
    max_comments: int = 200
    cookies:      Optional[str] = None


class ReportRequest(BaseModel):
    query:   str
    db_path: Optional[str] = None


class IngestRequest(BaseModel):
    """手动触发：把 raw/ 目录最新 CSV 导入 SQLite"""
    contents_csv: Optional[str] = None   # 不填则自动取最新
    comments_csv: Optional[str] = None
    platform:     str = "douyin"


# ════════════════════════════════════════════════════════
# 工具函数
# ════════════════════════════════════════════════════════

def _latest_csv(pattern: str) -> Optional[Path]:
    """在 raw/ 目录找最新匹配的 CSV"""
    files = sorted(glob.glob(str(RAW_DIR / pattern)))
    return Path(files[-1]) if files else None


def _log(task_id: str, msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    tasks[task_id]["log"].append(line)
    print(line)


# ════════════════════════════════════════════════════════
# 爬虫封装层（MediaCrawler subprocess）
# ════════════════════════════════════════════════════════

PLATFORM_MAP = {
    "douyin":   "dy",
    "xhs":      "xhs",
    "bilibili": "bili",
    "weibo":    "wb",
}


def _write_cookies(platform: str, cookie_str: str):
    """把 Cookie 写入 MediaCrawler 的配置"""
    import json
    cookie_path = CRAWLER_DIR / "config" / "accounts_cookies.json"
    if not cookie_path.exists():
        return
    try:
        with open(cookie_path, "r+", encoding="utf-8") as f:
            data = json.load(f)
            data[PLATFORM_MAP.get(platform, platform)] = cookie_str
            f.seek(0)
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.truncate()
    except Exception as e:
        print(f"[WARN] 写入 cookie 失败：{e}")


async def _run_crawler_for_keyword(task_id: str, keyword: str, req: CrawlRequest):
    """调用 MediaCrawler 爬取单个关键词"""
    _log(task_id, f"开始爬取关键词：{keyword} （平台：{req.platform}）")

    cmd = [
        sys.executable, "main.py",
        "--platform",       PLATFORM_MAP.get(req.platform, req.platform),
        "--lt",             "cookie",
        "--type",           "search",
        "--keywords",       keyword,
        "--max_note_count", str(req.max_posts),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(CRAWLER_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        log_text = stdout.decode("utf-8", errors="ignore")

        # 只保留最后 800 字符，避免日志过长
        _log(task_id, log_text[-800:] if len(log_text) > 800 else log_text)

        if proc.returncode == 0:
            _log(task_id, f"✅ {keyword} 爬取完成")
        else:
            _log(task_id, f"❌ {keyword} 爬取失败 returncode={proc.returncode}")

    except FileNotFoundError:
        _log(task_id, f"❌ media_crawler/main.py 不存在，请检查 CRAWLER_DIR 路径")
    except Exception as e:
        _log(task_id, f"❌ 爬取异常：{e}")


async def run_crawler_task(task_id: str, req: CrawlRequest):
    """后台任务：爬取 → 自动导入最新 CSV → done"""
    tasks[task_id]["status"] = "running"

    if req.cookies:
        _write_cookies(req.platform, req.cookies)

    # 1. 逐关键词爬取
    for keyword in req.keywords:
        await _run_crawler_for_keyword(task_id, keyword, req)

    # 2. 爬完后自动导入最新 CSV
    _log(task_id, "📥 开始导入最新 CSV 到 SQLite...")
    try:
        imported = _ingest_latest_csv(req.platform)
        _log(task_id, f"✅ 导入完成：posts={imported['posts']}, comments={imported['comments']}")
    except Exception as e:
        _log(task_id, f"⚠️ CSV 导入失败：{e}")

    tasks[task_id]["status"]      = "done"
    tasks[task_id]["finished_at"] = datetime.now().isoformat()


def _ingest_latest_csv(platform: str = "douyin") -> dict:
    """
    从 raw/ 目录找最新的 contents / comments CSV，
    调用已有的 ingest 函数写入 SQLite。
    """
    contents_csv = _latest_csv("search_contents_*.csv")
    comments_csv = _latest_csv("search_comments_*.csv")

    if not contents_csv and not comments_csv:
        raise FileNotFoundError(f"raw/ 目录下未找到 CSV 文件")

    conn = sqlite3.connect(str(DB_PATH))
    ensure_schema(conn)

    n_posts    = ingest_posts(conn, str(contents_csv), platform=platform) if contents_csv else 0
    n_comments = ingest_comments(conn, str(comments_csv), platform=platform) if comments_csv else 0

    conn.close()
    return {"posts": n_posts, "comments": n_comments,
            "contents_file": str(contents_csv),
            "comments_file": str(comments_csv)}


# ════════════════════════════════════════════════════════
# API Routes
# ════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {
        "service":  "pmflow API",
        "version":  "2.0.0",
        "status":   "ok",
        "db":       str(DB_PATH),
        "raw_dir":  str(RAW_DIR),
    }


# ── 爬取 ──────────────────────────────────────────────

@app.post("/crawl")
async def crawl(req: CrawlRequest, bg: BackgroundTasks):
    """发起爬取任务（后台异步执行）"""
    task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    tasks[task_id] = {
        "status":     "pending",
        "keywords":   req.keywords,
        "platform":   req.platform,
        "created_at": datetime.now().isoformat(),
        "log":        [],
    }
    bg.add_task(run_crawler_task, task_id, req)
    return {"task_id": task_id, "message": "爬取任务已启动，可通过 /crawl/{task_id} 查看进度"}


@app.get("/crawl/{task_id}")
def crawl_status(task_id: str):
    """查询爬取任务状态 + 日志"""
    if task_id not in tasks:
        raise HTTPException(404, f"任务 {task_id} 不存在")
    return tasks[task_id]


@app.get("/tasks")
def list_tasks():
    """所有任务列表（不含详细日志）"""
    return [
        {k: v for k, v in task.items() if k != "log"}
        | {"task_id": tid}
        for tid, task in tasks.items()
    ]


# ── 手动导入 CSV ──────────────────────────────────────

@app.post("/ingest")
def ingest(req: IngestRequest = IngestRequest()):
    """
    手动触发：把 raw/ 目录最新 CSV 导入 SQLite。
    不传参数时自动找最新文件。
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        ensure_schema(conn)

        contents_path = Path(req.contents_csv) if req.contents_csv else _latest_csv("search_contents_*.csv")
        comments_path = Path(req.comments_csv) if req.comments_csv else _latest_csv("search_comments_*.csv")

        if not contents_path and not comments_path:
            raise HTTPException(400, "raw/ 目录下未找到 CSV 文件")

        n_posts    = ingest_posts(conn, str(contents_path), platform=req.platform) if contents_path else 0
        n_comments = ingest_comments(conn, str(comments_path), platform=req.platform) if comments_path else 0
        conn.close()

        return {
            "ok":             True,
            "posts_ingested": n_posts,
            "comments_ingested": n_comments,
            "contents_file":  str(contents_path),
            "comments_file":  str(comments_path),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ── 报告 ──────────────────────────────────────────────

@app.post("/report")
def report(req: ReportRequest):
    """生成三模块分析报告，返回 Markdown 字符串"""
    db = req.db_path or str(DB_PATH)
    if not Path(db).exists():
        raise HTTPException(400, f"数据库不存在：{db}，请先执行 /ingest")
    try:
        md = build_report(req.query, db_path=db)
        # 同时保存到 outputs/
        out_dir = OUTPUTS_DIR / req.query
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"report_{datetime.now().strftime('%Y-%m-%d')}.md"
        out_file.write_text(md, encoding="utf-8")
        return {"query": req.query, "report": md, "saved_to": str(out_file)}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── 数据查询 ──────────────────────────────────────────

@app.get("/posts")
def list_posts(keyword: str = "", limit: int = 20):
    """查询 posts 表"""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    if keyword:
        cur.execute("""
            SELECT post_id, keyword, title, text, author_name,
                   like_count, comment_count, share_count, collect_count,
                   url, platform, ip_location
            FROM posts
            WHERE keyword LIKE ? OR title LIKE ? OR text LIKE ?
            ORDER BY comment_count DESC LIMIT ?
        """, (f"%{keyword}%",) * 3 + (limit,))
    else:
        cur.execute("""
            SELECT post_id, keyword, title, text, author_name,
                   like_count, comment_count, share_count, collect_count,
                   url, platform, ip_location
            FROM posts ORDER BY comment_count DESC LIMIT ?
        """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.get("/keywords")
def list_keywords():
    """已有关键词及数量"""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("""
        SELECT keyword, COUNT(*) as cnt
        FROM posts
        GROUP BY keyword
        ORDER BY cnt DESC
    """)
    rows = [{"keyword": r[0], "count": r[1]} for r in cur.fetchall()]
    conn.close()
    return rows


@app.get("/stats")
def stats():
    """数据库整体统计"""
    if not DB_PATH.exists():
        return {"posts": 0, "comments": 0, "keywords": 0}
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM posts")
    n_posts = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM comments")
    n_comments = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT keyword) FROM posts")
    n_keywords = cur.fetchone()[0]
    conn.close()
    return {"posts": n_posts, "comments": n_comments, "keywords": n_keywords}


@app.delete("/data/{keyword}")
def delete_keyword(keyword: str):
    """删除某关键词的全部 posts 和 comments"""
    if not DB_PATH.exists():
        raise HTTPException(400, "数据库不存在")
    conn = sqlite3.connect(str(DB_PATH))
    # 先找到这些 post 的 ID
    cur = conn.cursor()
    cur.execute("SELECT post_id FROM posts WHERE keyword = ?", (keyword,))
    ids = [r[0] for r in cur.fetchall()]
    if ids:
        placeholders = ",".join("?" * len(ids))
        conn.execute(f"DELETE FROM comments WHERE post_id IN ({placeholders})", ids)
    conn.execute("DELETE FROM posts WHERE keyword = ?", (keyword,))
    conn.commit()
    conn.close()
    return {"ok": True, "deleted_posts": len(ids), "keyword": keyword}
