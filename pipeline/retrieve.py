
# pipeline/retrieve.py
import sqlite3
from typing import Optional

DB_PATH = "data/pmflow.db"


def get_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # 让结果可以用 row["字段名"] 访问
    return conn


def search_posts(
    query: str,
    db_path: str = DB_PATH,
    limit: int = 50,
) -> list[dict]:
    """
    按 keyword / title / text 召回相关 posts。
    优先级：keyword 完全匹配 > title/text 包含匹配
    再按 comment_count 降序（讨论越多越有价值）
    """
    conn = get_conn(db_path)
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM posts
        WHERE
            keyword LIKE ?
            OR title LIKE ?
            OR text  LIKE ?
        ORDER BY
            CASE WHEN keyword = ? THEN 0 ELSE 1 END,
            comment_count DESC
        LIMIT ?
    """, (
        f"%{query}%",
        f"%{query}%",
        f"%{query}%",
        query,
        limit,
    ))

    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_comments(
    post_ids: list[str],
    db_path: str = DB_PATH,
    limit_per_post: int = 200,
    only_top_level: bool = False,
) -> dict[str, list[dict]]:
    """
    按 post_id 列表批量拉取评论。
    返回格式：{ post_id: [comment, ...], ... }

    only_top_level=True 时只取一级评论（parent_comment_id == '0'）
    """
    if not post_ids:
        return {}

    conn = get_conn(db_path)
    cur = conn.cursor()

    result: dict[str, list[dict]] = {pid: [] for pid in post_ids}

    for pid in post_ids:
        if only_top_level:
            cur.execute("""
                SELECT *
                FROM comments
                WHERE post_id = ?
                  AND (parent_comment_id = '0' OR parent_comment_id = '')
                ORDER BY like_count DESC
                LIMIT ?
            """, (pid, limit_per_post))
        else:
            cur.execute("""
                SELECT *
                FROM comments
                WHERE post_id = ?
                ORDER BY like_count DESC
                LIMIT ?
            """, (pid, limit_per_post))

        result[pid] = [dict(r) for r in cur.fetchall()]

    conn.close()
    return result


def fetch_bundle(
    query: str,
    db_path: str = DB_PATH,
    post_limit: int = 50,
    comment_limit_per_post: int = 200,
    only_top_level: bool = False,
) -> dict:
    """
    主入口：输入一个 query，返回完整的 posts + comments bundle。

    返回格式：
    {
        "query": str,
        "posts": [ {post 字段...}, ... ],
        "comments": { post_id: [ {comment 字段...}, ... ], ... },
        "stats": {
            "post_count": int,
            "comment_count": int,
            "top_level_ratio": float,   # 一级评论占比
        }
    }
    """
    posts = search_posts(query, db_path=db_path, limit=post_limit)

    if not posts:
        return {
            "query": query,
            "posts": [],
            "comments": {},
            "stats": {"post_count": 0, "comment_count": 0, "top_level_ratio": 0.0},
        }

    post_ids = [p["post_id"] for p in posts]
    comments_map = fetch_comments(
        post_ids,
        db_path=db_path,
        limit_per_post=comment_limit_per_post,
        only_top_level=only_top_level,
    )

    # 统计
    all_comments = [c for cs in comments_map.values() for c in cs]
    total_comments = len(all_comments)
    top_level_count = sum(
        1 for c in all_comments
        if c.get("parent_comment_id") in ("0", "", None)
    )
    top_level_ratio = round(top_level_count / total_comments, 4) if total_comments else 0.0

    return {
        "query": query,
        "posts": posts,
        "comments": comments_map,
        "stats": {
            "post_count": len(posts),
            "comment_count": total_comments,
            "top_level_ratio": top_level_ratio,
        },
    }


# ── 快速验证（直接 python pipeline/retrieve.py 运行）──────────────────────────
if __name__ == "__main__":
    import json

    bundle = fetch_bundle("续火花", post_limit=50, comment_limit_per_post=200)

    print(f"query       : {bundle['query']}")
    print(f"posts found : {bundle['stats']['post_count']}")
    print(f"comments    : {bundle['stats']['comment_count']}")
    print(f"top-level % : {bundle['stats']['top_level_ratio'] * 100:.1f}%")

    if bundle["posts"]:
        print("\n── Top 3 posts (by comment_count) ──")
        for p in bundle["posts"][:3]:
            print(f"  [{p['comment_count']} 评论] {p['title'] or p['text'][:40]}")

    if bundle["comments"]:
        first_pid = list(bundle["comments"].keys())[0]
        sample_comments = bundle["comments"][first_pid][:3]
        print(f"\n── 前 3 条高赞评论（post: {first_pid}）──")
        for c in sample_comments:
            print(f"  [{c['like_count']} 赞] {c['text'][:50]}")
