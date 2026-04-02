
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP
from pipeline.retrieve import fetch_bundle
from pipeline.report import build_report

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, "data", "pmflow.db")
OUT_DIR  = os.path.join(BASE_DIR, "outputs")

mcp = FastMCP("pmflow")


@mcp.tool()
def retrieve(query: str, post_limit: int = 20, comment_limit: int = 50) -> dict:
    """
    根据关键词从本地抖音数据库召回相关内容和评论。
    返回 posts 列表、评论字典和基础统计。
    """
    return fetch_bundle(
        query=query,
        db_path=DB_PATH,
        post_limit=post_limit,
        comment_limit_per_post=comment_limit,
    )


@mcp.tool()
def report(query: str) -> str:
    """
    根据关键词生成完整的竞品舆情分析 Markdown 报告，
    包含数据概览、互动排行、高赞评论、地域分布等。
    """
    md = build_report(query, db_path=DB_PATH)

    from datetime import datetime
    out_dir = os.path.join(OUT_DIR, query)
    os.makedirs(out_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = os.path.join(out_dir, f"report_{date_str}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    return md


@mcp.tool()
def top_comments(query: str, n: int = 10) -> list:
    """
    返回关键词下点赞数最高的 n 条评论，适合快速了解用户声音。
    """
    bundle = fetch_bundle(query, db_path=DB_PATH, comment_limit_per_post=50)
    all_comments = [
        c for cs in bundle["comments"].values() for c in cs
    ]
    sorted_comments = sorted(all_comments, key=lambda x: x["like_count"], reverse=True)
    return [
        {
            "text": c["text"],
            "like_count": c["like_count"],
            "author": c["author_name"],
            "location": c["ip_location"],
        }
        for c in sorted_comments[:n]
    ]


@mcp.tool()
def get_post_list(query: str) -> list:
    """
    返回关键词下所有匹配的抖音内容列表，
    包含标题、评论数、点赞数、分享数、链接。
    """
    bundle = fetch_bundle(query, db_path=DB_PATH)
    posts  = bundle["posts"]
    return [
        {
            "title":         (p.get("title") or p.get("text") or "")[:60],
            "comment_count": p["comment_count"],
            "like_count":    p["like_count"],
            "share_count":   p["share_count"],
            "collect_count": p["collect_count"],
            "url":           p["url"],
        }
        for p in sorted(posts, key=lambda x: x["comment_count"], reverse=True)
    ]


if __name__ == "__main__":
    mcp.run(transport="stdio")
