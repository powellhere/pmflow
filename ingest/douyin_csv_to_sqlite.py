import os
import csv
import json
import sqlite3


def normalize_header(h: str) -> str:
    # 处理 UTF-8 BOM：有时会出现 "﻿aweme_id" / "﻿comment_id"
    return h.replace("\ufeff", "").strip()


def to_int(x, default=0) -> int:
    try:
        if x is None:
            return default
        s = str(x).strip()
        if s == "":
            return default
        return int(float(s))
    except Exception:
        return default


def ensure_schema(conn: sqlite3.Connection):
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
    cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_postid ON comments(post_id);")

    conn.commit()


def ingest_posts(conn: sqlite3.Connection, csv_path: str, platform="douyin") -> int:
    cur = conn.cursor()
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        reader.fieldnames = [normalize_header(h) for h in reader.fieldnames]

        n = 0
        for row in reader:
            post_id = (row.get("aweme_id") or "").strip()
            if not post_id:
                continue

            media_url = (row.get("video_download_url") or "").strip()
            if not media_url:
                media_url = (row.get("note_download_url") or "").strip()

            payload = {
                "platform": platform,
                "post_id": post_id,
                "keyword": (row.get("source_keyword") or "").strip(),
                "title": row.get("title") or "",
                "text": row.get("desc") or "",
                "created_at": to_int(row.get("create_time")),
                "author_id": (row.get("user_id") or row.get("sec_uid") or "").strip(),
                "author_name": row.get("nickname") or "",
                "like_count": to_int(row.get("liked_count")),
                "collect_count": to_int(row.get("collected_count")),
                "comment_count": to_int(row.get("comment_count")),
                "share_count": to_int(row.get("share_count")),
                "ip_location": (row.get("ip_location") or "").strip(),
                "url": row.get("aweme_url") or "",
                "cover_url": row.get("cover_url") or "",
                "media_url": media_url,
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
                payload["platform"], payload["post_id"], payload["keyword"], payload["title"], payload["text"], payload["created_at"],
                payload["author_id"], payload["author_name"],
                payload["like_count"], payload["collect_count"], payload["comment_count"], payload["share_count"],
                payload["ip_location"], payload["url"], payload["cover_url"], payload["media_url"], payload["raw"]
            ))
            n += 1

    conn.commit()
    return n


def ingest_comments(conn: sqlite3.Connection, csv_path: str, platform="douyin") -> int:
    cur = conn.cursor()
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        reader.fieldnames = [normalize_header(h) for h in reader.fieldnames]

        n = 0
        for row in reader:
            comment_id = (row.get("comment_id") or "").strip()
            post_id = (row.get("aweme_id") or "").strip()
            text = (row.get("content") or "").strip()

            if not comment_id or not post_id:
                continue
            if not text:
                continue

            payload = {
                "platform": platform,
                "comment_id": comment_id,
                "post_id": post_id,
                "created_at": to_int(row.get("create_time")),
                "ip_location": (row.get("ip_location") or "").strip(),
                "text": text,
                "like_count": to_int(row.get("like_count")),
                "author_id": (row.get("user_id") or row.get("sec_uid") or "").strip(),
                "author_name": row.get("nickname") or "",
                "parent_comment_id": str(row.get("parent_comment_id") or "").strip(),
                "sub_comment_count": to_int(row.get("sub_comment_count")),
                "raw": json.dumps(row, ensure_ascii=False),
            }

            cur.execute("""
            INSERT OR REPLACE INTO comments(
                platform, comment_id, post_id, created_at, ip_location, text,
                like_count, author_id, author_name, parent_comment_id, sub_comment_count, raw
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                payload["platform"], payload["comment_id"], payload["post_id"], payload["created_at"], payload["ip_location"], payload["text"],
                payload["like_count"], payload["author_id"], payload["author_name"], payload["parent_comment_id"], payload["sub_comment_count"], payload["raw"]
            ))
            n += 1

    conn.commit()
    return n


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--contents", required=True, help="path to search_contents_*.csv")
    parser.add_argument("--comments", required=True, help="path to search_comments_*.csv")
    parser.add_argument("--db", default="data/pm-flow.db")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.db), exist_ok=True)

    conn = sqlite3.connect(args.db)
    ensure_schema(conn)

    n_posts = ingest_posts(conn, args.contents)
    n_comments = ingest_comments(conn, args.comments)

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM posts;")
    total_posts = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM comments;")
    total_comments = cur.fetchone()[0]

    print(f"[OK] ingested posts: {n_posts}, comments: {n_comments}")
    print(f"[OK] db totals -> posts: {total_posts}, comments: {total_comments}")
    print(f"[OK] db path: {args.db}")


if __name__ == "__main__":
    main()