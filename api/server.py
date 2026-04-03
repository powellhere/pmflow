
"""
FastAPI 后端
启动方式：cd ~/pmflow && uvicorn api.server:app --reload
"""

import os
import sys
import uuid
import sqlite3
import subprocess
import threading
import shutil
import re
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

# ════════════════════════════════════════════════════
# 常量
# ════════════════════════════════════════════════════

ROOT_DIR             = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

MEDIA_CRAWLER_DIR    = Path.home() / "MediaCrawler"
MEDIA_CRAWLER_PYTHON = MEDIA_CRAWLER_DIR / ".venv" / "bin" / "python"
DB_PATH              = ROOT_DIR / "data" / "pmflow.db"
RAW_DIR              = ROOT_DIR / "raw"

# UI 传入的短名 → 目录用的全名
PLATFORM_FULL_MAP = {
    "bili":   "bilibili",
    "xhs":    "xhs",
    "dy":     "douyin",
    "wb":     "weibo",
    "ks":     "kuaishou",
    "tieba":  "tieba",
    "zhihu":  "zhihu",
}

STEP_LABELS = [
    "初始化爬虫",
    "登录平台",
    "搜索关键词",
    "抓取内容",
    "抓取评论",
    "保存 CSV",
    "导入数据库",
]

app = FastAPI()

# ── 任务存储（内存，进程级） ──────────────────────────────
TASKS: dict = {}


# ════════════════════════════════════════════════════
# Schema
# ════════════════════════════════════════════════════

class CrawlRequest(BaseModel):
    keywords:         List[str]
    platform:         str            # bili / xhs / dy / wb / ks / tieba / zhihu
    login_type:       str  = "qrcode"
    max_comments:     int  = 50
    get_comment:      bool = True
    get_sub_comment:  bool = False
    save_data_option: str  = "csv"


# ════════════════════════════════════════════════════
# 辅助函数
# ════════════════════════════════════════════════════

def _make_steps(active_idx: int = 0, done_up_to: int = -1):
    steps = []
    for i, label in enumerate(STEP_LABELS):
        if i <= done_up_to:
            state = "done"
        elif i == active_idx:
            state = "active"
        else:
            state = "idle"
        steps.append({"label": label, "state": state})
    return steps


def _patch_config(req: CrawlRequest):
    """
    把关键词 / 评论数等写入 MediaCrawler/config/base_config.py
    兼容新旧版本的不同变量名。
    """
    config_path = MEDIA_CRAWLER_DIR / "config" / "base_config.py"
    if not config_path.exists():
        return

    text = config_path.read_text(encoding="utf-8")
    kw_str = '["' + '", "'.join(req.keywords) + '"]'

    replacements = {
        r'(KEYWORDS\s*=\s*)(\[.*?\]|".*?")':        rf'\g<1>{kw_str}',
        r'(SEARCH_KEYWORDS\s*=\s*)(\[.*?\]|".*?")': rf'\g<1>{kw_str}',
        r'(MAX_COMMENT_NUM\s*=\s*)\d+':             rf'\g<1>{req.max_comments}',
        r'(CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES\s*=\s*)\d+': rf'\g<1>{req.max_comments}',
        r'(ENABLE_GET_COMMENTS\s*=\s*)\w+':         rf'\g<1>{"True" if req.get_comment else "False"}',
        r'(GET_COMMENT\s*=\s*)\w+':                 rf'\g<1>{"True" if req.get_comment else "False"}',
        r'(SAVE_DATA_OPTION\s*=\s*)".*?"':          rf'\g<1>"{req.save_data_option}"',
    }

    for pattern, repl in replacements.items():
        text = re.sub(pattern, repl, text)

    config_path.write_text(text, encoding="utf-8")


def _ingest_after_crawl(platform_short: str) -> dict:
    """爬取完成后把 MediaCrawler 的 CSV 同步到 RAW_DIR 并导入 DB
    
    platform_short: 短平台名（bili / dy / xhs / wb / ks / tieba / zhihu）
    """
    from ingest.douyin_csv_to_sqlite import ensure_schema, ingest_posts, ingest_comments

    # 根据短名生成所有可能的 MediaCrawler 数据目录名（兼容 bili/bilibili、dy/douyin 等）
    PLATFORM_DIR_VARIANTS = {
        "bili":   ["bili", "bilibili"],
        "dy":     ["dy", "douyin"],
        "ks":     ["ks", "kuaishou"],
        "wb":     ["wb", "weibo"],
        "xhs":    ["xhs"],
        "tieba":  ["tieba"],
        "zhihu":  ["zhihu"],
    }
    
    dir_variants = PLATFORM_DIR_VARIANTS.get(platform_short, [platform_short])
    
    # 构建候选目录列表（优先级递减）
    src_candidates = []
    for variant in dir_variants:
        src_candidates.extend([
            MEDIA_CRAWLER_DIR / "data" / variant / "csv",
            MEDIA_CRAWLER_DIR / "data" / variant,
        ])
    src_candidates.append(MEDIA_CRAWLER_DIR / "data")

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # 从所有候选目录复制 CSV
    copied_files = []
    for src_dir in src_candidates:
        if not src_dir.exists():
            continue
        for pattern in ["search_contents_*.csv", "search_videos_*.csv", "search_comments_*.csv"]:
            for f in sorted(src_dir.glob(pattern)):
                dest = RAW_DIR / f.name
                shutil.copy2(str(f), str(dest))
                copied_files.append(str(f))

    # 找最新的 CSV
    def latest(pat):
        files = sorted(RAW_DIR.glob(pat))
        return files[-1] if files else None

    contents = latest("search_contents_*.csv") or latest("search_videos_*.csv")
    comments = latest("search_comments_*.csv")

    if not contents and not comments:
        return {"posts": 0, "comments": 0}

    # 导入到 DB
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    ensure_schema(conn)
    n_p = ingest_posts(conn, str(contents), platform=platform_short) if contents else 0
    n_c = ingest_comments(conn, str(comments), platform=platform_short) if comments else 0
    conn.close()
    return {"posts": n_p, "comments": n_c}


# ════════════════════════════════════════════════════
# 核心：爬虫子线程
# ════════════════════════════════════════════════════

def _run_crawler(task_id: str, req: CrawlRequest):
    """在子线程中执行 MediaCrawler，实时采集日志"""
    task = TASKS[task_id]
    platform_full = PLATFORM_FULL_MAP.get(req.platform, req.platform)

    def log(msg: str):
        task["log"].append(msg)

    # ── Step 0: 写入配置文件 ──────────────────────────────
    log(f"▶ 启动爬虫  平台={platform_full}  关键词={','.join(req.keywords)}")
    task["steps"] = _make_steps(active_idx=0)
    try:
        _patch_config(req)
        log("✓ 配置文件已更新")
    except Exception as e:
        log(f"⚠ 配置写入失败（继续运行）：{e}")

    # ── 构建命令 ──────────────────────────────────────────
    # MediaCrawler CLI 接受短名：xhs / dy / bili / wb / ks / tieba / zhihu
    # req.platform 本身就是短名，直接用
    cmd = [
        str(MEDIA_CRAWLER_PYTHON), "main.py",
        "--platform", req.platform,
        "--lt", req.login_type,
        "--type", "search",
    ]

    env = os.environ.copy()
    env["KEYWORDS"]         = ",".join(req.keywords)
    env["MAX_COMMENTS"]     = str(req.max_comments)
    env["GET_COMMENT"]      = "1" if req.get_comment else "0"
    env["GET_SUB_COMMENT"]  = "1" if req.get_sub_comment else "0"
    env["SAVE_DATA_OPTION"] = req.save_data_option
    env["PYTHONUNBUFFERED"]  = "1"

    log(f"$ {' '.join(cmd)}")
    task["steps"] = _make_steps(active_idx=0, done_up_to=0)

    # ── 启动子进程 ────────────────────────────────────────
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(MEDIA_CRAWLER_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        task["process"] = proc

        step_keywords = {
            1: ["登录", "login", "扫码", "qrcode", "cookie", "已登录", "logged"],
            2: ["搜索", "search", "keyword", "关键词"],
            3: ["抓取", "crawl", "fetch", "视频", "笔记", "note", "video"],
            4: ["评论", "comment"],
            5: ["保存", "save", "csv", "写入", "finish"],
        }
        current_step = 0

        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            log(line)
            line_lower = line.lower()

            for step_idx, kws in step_keywords.items():
                if step_idx > current_step and any(k in line_lower for k in kws):
                    current_step = step_idx
                    task["steps"] = _make_steps(
                        active_idx=current_step,
                        done_up_to=current_step - 1,
                    )
                    break

            if task["status"] == "stopped":
                proc.terminate()
                log("⏹ 用户手动停止")
                return

        proc.wait()
        rc = proc.returncode

        # ── 退出码处理 ────────────────────────────────────
        csv_found = any(
            list((MEDIA_CRAWLER_DIR / "data" / platform_full).glob("*.csv"))
            if (MEDIA_CRAWLER_DIR / "data" / platform_full).exists() else []
        ) or any(RAW_DIR.glob("search_contents_*.csv")) or any(RAW_DIR.glob("search_videos_*.csv"))

        if rc != 0 and not csv_found and task["status"] != "stopped":
            task["status"] = "error"
            task["error"]  = f"进程退出码 {rc}，且未生成 CSV，请查看日志"
            task["steps"]  = _make_steps(active_idx=-1, done_up_to=current_step - 1)
            log(f"❌ 爬虫异常退出，退出码 {rc}")
            return

        if rc != 0:
            log(f"⚠ 退出码 {rc}（已检测到 CSV，继续导入）")

    except FileNotFoundError:
        task["status"] = "error"
        task["error"]  = f"找不到 MediaCrawler，请确认路径：{MEDIA_CRAWLER_DIR}"
        log(f"❌ {task['error']}")
        return
    except Exception as e:
        task["status"] = "error"
        task["error"]  = str(e)
        log(f"❌ 异常：{e}")
        return

    # ── 导入数据库 ─────────────────────────────────────────
    log("⏳ 正在导入数据库…")
    task["steps"] = _make_steps(active_idx=6, done_up_to=5)
    try:
        imported = _ingest_after_crawl(req.platform)  # 传短名
        task["imported"] = imported
        task["steps"]    = _make_steps(active_idx=-1, done_up_to=6)
        log(f"✅ 导入完成  内容 {imported['posts']} 条 · 评论 {imported['comments']} 条")
    except Exception as e:
        task["imported"] = {"posts": 0, "comments": 0}
        log(f"⚠️ 导入失败：{e}")

    task["status"] = "done"


# ════════════════════════════════════════════════════
# 路由
# ════════════════════════════════════════════════════

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/crawl")
def start_crawl(req: CrawlRequest):
    task_id = str(uuid.uuid4())[:8]
    TASKS[task_id] = {
        "status":     "pending",
        "log":        [],
        "platform":   req.platform,
        "keywords":   req.keywords,
        "login_type": req.login_type,
        "steps":      _make_steps(active_idx=0),
        "process":    None,
        "imported":   None,
        "error":      None,
    }

    def _start():
        TASKS[task_id]["status"] = "running"
        _run_crawler(task_id, req)

    t = threading.Thread(target=_start, daemon=True)
    t.start()
    return {"task_id": task_id}


@app.get("/crawl/{task_id}")
def get_task(task_id: str):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return {
        "status":     task["status"],
        "platform":   task["platform"],
        "keywords":   task["keywords"],
        "login_type": task["login_type"],
        "steps":      task["steps"],
        "log":        task["log"],
        "imported":   task["imported"],
        "error":      task["error"],
    }


@app.post("/crawl/{task_id}/stop")
def stop_task(task_id: str):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task["status"] = "stopped"
    proc = task.get("process")
    if proc:
        proc.terminate()
    return {"ok": True}


@app.get("/crawl/{task_id}/qrcode")
def get_qrcode(task_id: str):
    """返回 MediaCrawler 生成的二维码图片"""
    qr_candidates = [
        MEDIA_CRAWLER_DIR / "qrcode.png",
        MEDIA_CRAWLER_DIR / "qr.png",
        MEDIA_CRAWLER_DIR / "temp" / "qrcode.png",
        MEDIA_CRAWLER_DIR / "browser_data" / "qrcode.png",
    ]
    for p in qr_candidates:
        if p.exists():
            return FileResponse(str(p), media_type="image/png")
    raise HTTPException(404, "QR code not ready yet")
