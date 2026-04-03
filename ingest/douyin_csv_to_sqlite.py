
import os
import csv
import json
import sqlite3
from typing import Dict, List, Optional


def normalize_header(h: str) -> str:
    """处理 UTF-8 BOM 和空格"""
    return h.replace("\ufeff", "").strip()


def to_int(x, default=0) -> int:
    """安全转换为整数"""
    try:
        if x is None:
            return default
        s = str(x).strip()
        if s == "":
            return default
        return int(float(s))
    except Exception:
        return default


def _get_first(row: dict, keys: List[str]) -> str:
    """从 row 中按优先级顺序取第一个存在且非空的字段值"""
    for k in keys:
        if k not in row:
            continue
        v = row.get(k)
        if v is not None:
            s = str(v).strip()
            if s != "":
                return s
    return ""


# ============= 平台特定字段映射 =============
# 每个平台的 CSV 使用不同的列名，这个字典定义了标准字段 -> 平台列名的映射

PLATFORM_FIELD_MAP = {
    "dy": {  # 抖音 / Douyin
        "post_id": ["aweme_id", "video_id", "id"],
        "title": ["title", "desc"],
        "text": ["desc", "description", "text", "content"],
        "media_url": ["video_download_url", "download_url", "media_url"],
        "cover_url": ["cover_url"],
        "created_at": ["create_time", "created_at"],
        "author_id": ["user_id", "sec_uid", "author_id", "uid"],
        "author_name": ["nickname", "author_name", "username"],
        "like_count": ["liked_count", "like_count"],
        "collect_count": ["collected_count", "collect_count"],
        "comment_count": ["comment_count"],
        "share_count": ["share_count"],
        "ip_location": ["ip_location", "location"],
        "url": ["aweme_url", "url"],
        "keyword": ["source_keyword", "keyword"],
        "comment_id": ["comment_id", "id"],
        "parent_comment_id": ["parent_comment_id", "reply_to_comment_id"],
        "sub_comment_count": ["sub_comment_count"],
    },
    "xhs": {  # 小红书 / Xiaohongshu
        "post_id": ["interact_id", "note_id", "id", "aweme_id"],
        "title": ["title"],
        "text": ["desc", "description", "text", "content", "note_card_describe"],
        "media_url": ["interact_id", "note_id", "download_url", "video_url"],
        "cover_url": ["cover_image_url", "image_url", "cover_url"],
        "created_at": ["create_time", "created_at", "publish_time"],
        "author_id": ["user_id", "author_id", "uid"],
        "author_name": ["nickname", "author_name", "username"],
        "like_count": ["interact_count", "like_count", "liked_count"],
        "collect_count": ["collected_count", "collect_count"],
        "comment_count": ["comment_count"],
        "share_count": ["share_count"],
        "ip_location": ["ip_location", "location"],
        "url": ["interact_id", "note_url", "url"],
        "keyword": ["source_keyword", "keyword"],
        "comment_id": ["comment_id", "id"],
        "parent_comment_id": ["parent_comment_id", "reply_to_comment_id"],
        "sub_comment_count": ["sub_comment_count"],
    },
        "bili": {  # B站 / Bilibili
        "post_id": ["video_id", "bvid", "id"],
        "title": ["title"],
        "text": ["desc", "description", "text", "content"],
        "media_url": ["video_download_url", "download_url", "media_url"],
        "cover_url": ["cover_url"],
        "created_at": ["create_time", "created_at"],
        "author_id": ["user_id", "uid"],
        "author_name": ["nickname", "author_name"],
        "like_count": ["liked_count", "like_count"],
        "collect_count": ["collected_count"],
        "comment_count": ["comment_count"],
        "share_count": ["share_count"],
        "ip_location": ["ip_location"],
        "url": ["aweme_url", "url"],
        "keyword": ["source_keyword", "keyword"],
        # === 评论字段 ===
        "comment_id": ["comment_id", "id"],
        "parent_comment_id": ["parent_comment_id"],
        "sub_comment_count": ["sub_comment_count"],
    },
    "ks": {  # 快手 / Kuaishou
        "post_id": ["video_id", "id", "aweme_id"],
        "title": ["title"],
        "text": ["description", "desc", "caption", "text", "content"],
        "media_url": ["video_url", "download_url", "media_url"],
        "cover_url": ["cover_image_url", "cover_url", "image_url"],
        "created_at": ["create_time", "created_at"],
        "author_id": ["user_id", "author_id", "uid"],
        "author_name": ["nickname", "author_name", "username"],
        "like_count": ["like_count", "liked_count"],
        "collect_count": ["collected_count", "collect_count"],
        "comment_count": ["comment_count"],
        "share_count": ["share_count"],
        "ip_location": ["ip_location", "location"],
        "url": ["video_url", "url"],
        "keyword": ["source_keyword", "keyword"],
        "comment_id": ["comment_id", "id"],
        "parent_comment_id": ["parent_comment_id", "reply_to_comment_id"],
        "sub_comment_count": ["sub_comment_count"],
    },
    "wb": {  # 微博 / Weibo
        "post_id": ["id", "mid", "post_id"],
        "title": ["title"],
        "text": ["text", "content", "desc"],
        "media_url": ["video_url", "download_url", "media_url"],
        "cover_url": ["cover_url", "image_url"],
        "created_at": ["create_time", "created_at"],
        "author_id": ["user_id", "uid"],
        "author_name": ["nickname", "screen_name"],
        "like_count": ["like_count", "attitudes_count"],
        "collect_count": ["collect_count"],
        "comment_count": ["comment_count", "comments_count"],
        "share_count": ["share_count", "reposts_count"],
        "ip_location": ["ip_location", "location", "source"],
        "url": ["url"],
        "keyword": ["source_keyword", "keyword"],
        "comment_id": ["comment_id", "id"],
        "parent_comment_id": ["parent_comment_id", "reply_to_comment_id"],
        "sub_comment_count": ["sub_comment_count"],
    },
    "tieba": {  # 贴吧 / Tieba
        "post_id": ["thread_id", "post_id", "id"],
        "title": ["title"],
        "text": ["content", "text", "desc"],
        "media_url": ["download_url", "media_url"],
        "cover_url": ["cover_url"],
        "created_at": ["create_time", "created_at"],
        "author_id": ["user_id", "author_id"],
        "author_name": ["nickname", "author_name"],
        "like_count": ["like_count"],
        "collect_count": ["collect_count"],
        "comment_count": ["reply_count", "comment_count"],
        "share_count": ["share_count"],
        "ip_location": ["ip_location", "location"],
        "url": ["url"],
        "keyword": ["source_keyword", "keyword"],
        "comment_id": ["post_id", "comment_id", "id"],
        "parent_comment_id": ["parent_comment_id", "reply_to_comment_id"],
        "sub_comment_count": ["sub_comment_count"],
    },
    "zhihu": {  # 知乎 / Zhihu
        "post_id": ["id", "answer_id", "article_id"],
        "title": ["title", "question_title"],
        "text": ["content", "text", "excerpt"],
        "media_url": ["video_url", "download_url", "media_url"],
        "cover_url": ["cover_url", "image_url"],
        "created_at": ["create_time", "created_at", "created_timestamp"],
        "author_id": ["author_id", "user_id"],
        "author_name": ["author_name", "nickname"],
        "like_count": ["voteup_count", "like_count"],
        "collect_count": ["collect_count"],
        "comment_count": ["comment_count"],
        "share_count": ["share_count"],
        "ip_location": ["ip_location", "location"],
        "url": ["url"],
        "keyword": ["source_keyword", "keyword"],
        "comment_id": ["comment_id", "id"],
        "parent_comment_id": ["parent_comment_id", "reply_to_comment_id"],
        "sub_comment_count": ["sub_comment_count"],
    },
}


def get_field_value(row: dict, platform: str, field_name: str) -> str:
    """根据平台和标准字段名从 CSV 行中提取值"""
    platform_lower = platform.lower()
    if platform_lower not in PLATFORM_FIELD_MAP:
        platform_lower = "dy"  # 默认使用抖音映射
    
    field_keys = PLATFORM_FIELD_MAP[platform_lower].get(field_name, [field_name])
    return _get_first(row, field_keys)


def ensure_schema(conn: sqlite3.Connection):
    """创建/检查数据库表和索引"""
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS posts (
        platform TEXT NOT NULL,
        post_id TEXT PRIMARY KEY,
        keyword TEXT,
        title TEXT,
        text TEXT,
        created_at INTEGER,
        author_id TEXT,
        author_name TEXT,
        like_count INTEGER,
        collect_count INTEGER,
        comment_count INTEGER,
        share_count INTEGER,
        ip_location TEXT,
        url TEXT,
        cover_url TEXT,
        media_url TEXT,
        raw TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS comments (
        platform TEXT NOT NULL,
        comment_id TEXT PRIMARY KEY,
        post_id TEXT NOT NULL,
        created_at INTEGER,
        ip_location TEXT,
        text TEXT,
        like_count INTEGER,
        author_id TEXT,
        author_name TEXT,
        parent_comment_id TEXT,
        sub_comment_count INTEGER,
        raw TEXT
    );
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_posts_keyword ON posts(keyword);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_posts_platform ON posts(platform);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_postid ON comments(post_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_platform ON comments(platform);")

    conn.commit()


def ingest_posts(conn: sqlite3.Connection, csv_path: str, platform: str = "dy") -> int:
    """导入帖子/视频数据
    
    Args:
        conn: sqlite3 连接
        csv_path: CSV 文件路径
        platform: 平台标识（dy/xhs/bili/ks/wb/tieba/zhihu）
        
    Returns:
        成功导入的行数
    """
    cur = conn.cursor()
    platform_lower = platform.lower()
    
    try:
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return 0
                
            reader.fieldnames = [normalize_header(h) for h in reader.fieldnames]

            n = 0
            for row in reader:
                # 提取必需字段
                post_id = get_field_value(row, platform_lower, "post_id")
                if not post_id:
                    continue

                # 构建数据字典
                payload = {
                    "platform": platform_lower,
                    "post_id": post_id,
                    "keyword": get_field_value(row, platform_lower, "keyword"),
                    "title": get_field_value(row, platform_lower, "title"),
                    "text": get_field_value(row, platform_lower, "text"),
                    "created_at": to_int(get_field_value(row, platform_lower, "created_at")),
                    "author_id": get_field_value(row, platform_lower, "author_id"),
                    "author_name": get_field_value(row, platform_lower, "author_name"),
                    "like_count": to_int(get_field_value(row, platform_lower, "like_count")),
                    "collect_count": to_int(get_field_value(row, platform_lower, "collect_count")),
                    "comment_count": to_int(get_field_value(row, platform_lower, "comment_count")),
                    "share_count": to_int(get_field_value(row, platform_lower, "share_count")),
                    "ip_location": get_field_value(row, platform_lower, "ip_location"),
                    "url": get_field_value(row, platform_lower, "url"),
                    "cover_url": get_field_value(row, platform_lower, "cover_url"),
                    "media_url": get_field_value(row, platform_lower, "media_url"),
                    "raw": json.dumps(row, ensure_ascii=False),
                }

                cur.execute("""
                INSERT OR REPLACE INTO posts(
                    platform, post_id, keyword, title, text, created_at,
                    author_id, author_name,
                    like_count, collect_count, comment_count, share_count,
                    ip_location, url, cover_url, media_url, raw
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    payload["platform"], payload["post_id"], payload["keyword"], 
                    payload["title"], payload["text"], payload["created_at"],
                    payload["author_id"], payload["author_name"],
                    payload["like_count"], payload["collect_count"], 
                    payload["comment_count"], payload["share_count"],
                    payload["ip_location"], payload["url"], 
                    payload["cover_url"], payload["media_url"], payload["raw"]
                ))
                n += 1

        conn.commit()
        return n
    except Exception as e:
        print(f"[ERROR] ingest_posts failed: {e}")
        return 0


def ingest_comments(conn: sqlite3.Connection, csv_path: str, platform: str = "dy") -> int:
    """导入评论数据
    
    Args:
        conn: sqlite3 连接
        csv_path: CSV 文件路径
        platform: 平台标识（dy/xhs/bili/ks/wb/tieba/zhihu）
        
    Returns:
        成功导入的行数
    """
    cur = conn.cursor()
    platform_lower = platform.lower()
    
    try:
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return 0
                
            reader.fieldnames = [normalize_header(h) for h in reader.fieldnames]

            n = 0
            for row in reader:
                # 提取必需字段
                comment_id = get_field_value(row, platform_lower, "comment_id")
                post_id = get_field_value(row, platform_lower, "post_id")
                text = get_field_value(row, platform_lower, "text")

                if not comment_id or not post_id or not text:
                    continue

                payload = {
                    "platform": platform_lower,
                    "comment_id": comment_id,
                    "post_id": post_id,
                    "created_at": to_int(get_field_value(row, platform_lower, "created_at")),
                    "ip_location": get_field_value(row, platform_lower, "ip_location"),
                    "text": text,
                    "like_count": to_int(get_field_value(row, platform_lower, "like_count")),
                    "author_id": get_field_value(row, platform_lower, "author_id"),
                    "author_name": get_field_value(row, platform_lower, "author_name"),
                    "parent_comment_id": get_field_value(row, platform_lower, "parent_comment_id"),
                    "sub_comment_count": to_int(get_field_value(row, platform_lower, "sub_comment_count")),
                    "raw": json.dumps(row, ensure_ascii=False),
                }

                cur.execute("""
                INSERT OR REPLACE INTO comments(
                    platform, comment_id, post_id, created_at, ip_location, text,
                    like_count, author_id, author_name, parent_comment_id, 
                    sub_comment_count, raw
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    payload["platform"], payload["comment_id"], payload["post_id"], 
                    payload["created_at"], payload["ip_location"], payload["text"],
                    payload["like_count"], payload["author_id"], payload["author_name"], 
                    payload["parent_comment_id"], payload["sub_comment_count"], payload["raw"]
                ))
                n += 1

        conn.commit()
        return n
    except Exception as e:
        print(f"[ERROR] ingest_comments failed: {e}")
        return 0


def main():
    """命令行入口"""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--contents", required=True, help="path to search_contents_*.csv")
    parser.add_argument("--comments", required=True, help="path to search_comments_*.csv")
    parser.add_argument("--platform", default="dy", help="platform: dy/xhs/bili/ks/wb/tieba/zhihu")
    parser.add_argument("--db", default="data/pmflow.db")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.db) or ".", exist_ok=True)

    conn = sqlite3.connect(args.db)
    ensure_schema(conn)

    n_posts = ingest_posts(conn, args.contents, platform=args.platform)
    n_comments = ingest_comments(conn, args.comments, platform=args.platform)

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM posts;")
    total_posts = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM comments;")
    total_comments = cur.fetchone()[0]

    print(f"[OK] ingested posts: {n_posts}, comments: {n_comments}")
    print(f"[OK] db totals -> posts: {total_posts}, comments: {total_comments}")
    print(f"[OK] db path: {args.db}")

    conn.close()


if __name__ == "__main__":
    main()
