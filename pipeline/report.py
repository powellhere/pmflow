
import os
import re
import sqlite3
from datetime import datetime
from collections import Counter


DB_PATH = "data/pmflow.db"

# ── 情感词典（轻量版）─────────────────────────────────────
POS_WORDS = {"好用","喜欢","推荐","优秀","棒","赞","牛","香","爱了","完美","方便","实惠","值得","舒服","耐用","满意","不错","超好","太好了","好评"}
NEG_WORDS = {"差","坑","难用","失望","退货","后悔","垃圾","烂","贵","坏","质量差","不好","糟糕","骗","假","虚假","夸大","无效","没用","一般"}

# ── 高频有意义词（过滤停用词）────────────────────────────
STOPWORDS = {"的","了","是","我","你","他","她","它","在","有","和","就","都","也","不","这","那","个","啊","吧","呢","嗯","哦","哈","嘿","一个","感觉","觉得","真的","还是","已经","一直","自己","没有","可以","什么","因为","所以","但是","如果","然后","现在","时候","东西","知道","发现","很","太","被","用","买","说","看","做"}


# ── 工具函数 ──────────────────────────────────────────────

def get_conn(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def epoch_to_str(ts: int, fmt="%Y-%m-%d") -> str:
    if not ts:
        return "未知"
    try:
        return datetime.fromtimestamp(ts).strftime(fmt)
    except Exception:
        return "未知"


def extract_words(text: str, min_len=2) -> list:
    """简单分词：提取2-6字中文词组"""
    if not text:
        return []
    words = re.findall(r'[\u4e00-\u9fa5]{2,6}', text)
    return [w for w in words if w not in STOPWORDS]


def sentiment(text: str) -> str:
    pos = sum(1 for w in POS_WORDS if w in text)
    neg = sum(1 for w in NEG_WORDS if w in text)
    if pos > neg:
        return "正面"
    elif neg > pos:
        return "负面"
    return "中性"


# ── 召回 ──────────────────────────────────────────────────

def fetch_posts(conn, query: str, limit=30):
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM posts
        WHERE keyword = ?
           OR title LIKE ?
           OR text  LIKE ?
        ORDER BY comment_count DESC
        LIMIT ?
    """, (query, f"%{query}%", f"%{query}%", limit))
    return cur.fetchall()


def fetch_comments(conn, post_ids: list, limit_per_post=50):
    if not post_ids:
        return []
    all_comments = []
    cur = conn.cursor()
    for pid in post_ids:
        cur.execute("""
            SELECT * FROM comments
            WHERE post_id = ?
            ORDER BY like_count DESC
            LIMIT ?
        """, (pid, limit_per_post))
        all_comments.extend(cur.fetchall())
    return all_comments


# ── 分析模块 ──────────────────────────────────────────────

def analyze_radar(posts, comments):
    """📡 信息雷达：热点话题 + 关键词频 + 传播趋势"""

    # 关键词频（合并 post + comment 文本）
    all_text = " ".join([
        (p["title"] or p["text"] or "") for p in posts
    ] + [
        (c["text"] or "") for c in comments
    ])
    words = extract_words(all_text)
    keyword_freq = Counter(words).most_common(20)

    # 传播趋势（按发布日期统计 post 数）
    date_counter = Counter()
    for p in posts:
        d = epoch_to_str(p["created_at"], "%Y-%m")
        if d != "未知":
            date_counter[d] += 1
    trend = sorted(date_counter.items())

    # 热点话题（评论数 Top5 标题）
    hot_topics = sorted(posts, key=lambda x: x["comment_count"], reverse=True)[:5]

    return {"keyword_freq": keyword_freq, "trend": trend, "hot_topics": hot_topics}


def analyze_insights(comments):
    """🔍 需求洞察：情感分布 + 用户痛点 + 高频诉求"""

    pos_cmts, neg_cmts, neu_cmts = [], [], []
    for c in comments:
        s = sentiment(c["text"] or "")
        if s == "正面":
            pos_cmts.append(c)
        elif s == "负面":
            neg_cmts.append(c)
        else:
            neu_cmts.append(c)

    total = len(comments) or 1
    sentiment_dist = {
        "正面": (len(pos_cmts), round(len(pos_cmts)/total*100, 1)),
        "负面": (len(neg_cmts), round(len(neg_cmts)/total*100, 1)),
        "中性": (len(neu_cmts), round(len(neu_cmts)/total*100, 1)),
    }

    # 高频诉求词（从所有评论提取）
    demand_words = extract_words(" ".join(c["text"] or "" for c in comments))
    demand_freq = Counter(demand_words).most_common(15)

    # 痛点（负面高赞评论 Top5）
    pain_points = sorted(neg_cmts, key=lambda x: x["like_count"], reverse=True)[:5]

    # 好评亮点（正面高赞评论 Top5）
    highlights = sorted(pos_cmts, key=lambda x: x["like_count"], reverse=True)[:5]

    return {
        "sentiment_dist": sentiment_dist,
        "demand_freq": demand_freq,
        "pain_points": pain_points,
        "highlights": highlights,
    }


def analyze_data(posts, comments):
    """📊 数据解读：互动数据 + 地域分布 + KOL"""

    # 互动汇总
    total_likes    = sum(p["like_count"]    for p in posts)
    total_shares   = sum(p["share_count"]   for p in posts)
    total_collects = sum(p["collect_count"] for p in posts)
    total_comments = len(comments)

    # 地域分布
    locs = [c["ip_location"] for c in comments if c["ip_location"]]
    loc_dist = Counter(locs).most_common(10)

    # KOL 识别（点赞最高的评论作者）
    author_likes = {}
    author_count = Counter()
    for c in comments:
        name = c["author_name"] or "匿名"
        author_likes[name] = author_likes.get(name, 0) + c["like_count"]
        author_count[name] += 1
    kol_list = sorted(author_likes.items(), key=lambda x: x[1], reverse=True)[:8]

    # 互动排行（Top 10 posts）
    top_engage = sorted(posts, key=lambda x: x["comment_count"], reverse=True)[:10]

    return {
        "total_likes": total_likes,
        "total_shares": total_shares,
        "total_collects": total_collects,
        "total_comments": total_comments,
        "loc_dist": loc_dist,
        "kol_list": kol_list,
        "top_engage": top_engage,
        "author_count": author_count,
    }


# ── 进度条渲染 ────────────────────────────────────────────

def bar(value, total, width=12) -> str:
    if total == 0:
        return "░" * width
    filled = round(value / total * width)
    return "█" * filled + "░" * (width - filled)


# ── 报告生成 ──────────────────────────────────────────────

def build_report(query: str, db_path=DB_PATH) -> str:
    conn     = get_conn(db_path)
    posts    = fetch_posts(conn, query)
    post_ids = [p["post_id"] for p in posts]
    comments = fetch_comments(conn, post_ids)

    radar    = analyze_radar(posts, comments)
    insights = analyze_insights(comments)
    data     = analyze_data(posts, comments)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    L = []

    # ── 封面
    L += [
        f"# 📋 pmflow 舆情分析报告",
        f"\n**🔑 关键词**：`{query}`　　**🕐 生成时间**：{now}　　**📦 数据来源**：抖音离线数据",
        f"\n> 样本来自关键词检索（共 **{len(posts)}** 条内容 / **{len(comments)}** 条评论），非全量数据，结论仅供参考。",
        "\n---",
    ]

    # ══════════════════════════════════════════
    # 📡 模块一：信息雷达
    # ══════════════════════════════════════════
    L += ["\n## 📡 模块一：信息雷达\n"]

    # 1-1 热点话题
    L += ["### 🔥 热点话题 Top 5（按评论数）\n"]
    for i, p in enumerate(radar["hot_topics"], 1):
        title = (p["title"] or p["text"] or "（无标题）")[:45]
        cmt   = p["comment_count"]
        like  = p["like_count"]
        L.append(f"{i}. **{title}**")
        L.append(f"   💬 {cmt:,} 评论　❤️ {like:,} 点赞　🔗 {p['url']}\n")

    # 1-2 关键词云（用频次可视化）
    L += ["### ☁️ 高频关键词 Top 20\n", "| 排名 | 关键词 | 频次 | 热度 |", "|:----:|:------:|:----:|------|"]
    max_freq = radar["keyword_freq"][0][1] if radar["keyword_freq"] else 1
    for rank, (word, cnt) in enumerate(radar["keyword_freq"], 1):
        b = bar(cnt, max_freq, 10)
        L.append(f"| {rank} | **{word}** | {cnt} | `{b}` |")

    # 1-3 传播趋势
    L += ["\n### 📈 内容传播趋势（按月）\n", "| 月份 | 内容数 | 趋势 |", "|------|:------:|------|"]
    max_trend = max((v for _, v in radar["trend"]), default=1)
    for month, cnt in radar["trend"]:
        b = bar(cnt, max_trend, 12)
        L.append(f"| {month} | {cnt} | `{b}` |")

    L.append("\n---")

    # ══════════════════════════════════════════
    # 🔍 模块二：需求洞察
    # ══════════════════════════════════════════
    L += ["\n## 🔍 模块二：需求洞察\n"]

    # 2-1 情感分布
    L += ["### 💬 情感倾向分布\n"]
    sd = insights["sentiment_dist"]
    total_s = sum(v[0] for v in sd.values()) or 1
    emoji_map = {"正面": "🟢", "负面": "🔴", "中性": "⚪"}
    for label, (cnt, pct) in sd.items():
        b = bar(cnt, total_s, 15)
        L.append(f"{emoji_map[label]} **{label}**　`{b}`　{cnt} 条 ({pct}%)")
    L.append("")

    # 2-2 高频诉求
    L += ["### 📌 用户高频诉求词 Top 15\n", "| 词语 | 出现次数 | 热度 |", "|:----:|:--------:|------|"]
    max_d = insights["demand_freq"][0][1] if insights["demand_freq"] else 1
    for word, cnt in insights["demand_freq"]:
        b = bar(cnt, max_d, 10)
        L.append(f"| **{word}** | {cnt} | `{b}` |")

    # 2-3 用户痛点
    L += ["\n### 😤 用户痛点（负面高赞评论 Top 5）\n"]
    if insights["pain_points"]:
        for i, c in enumerate(insights["pain_points"], 1):
            loc  = f"·{c['ip_location']}" if c["ip_location"] else ""
            name = c["author_name"] or "匿名"
            L.append(f"> **{i}.** {c['text']}")
            L.append(f"> — {name}{loc}　👍 {c['like_count']} 赞\n")
    else:
        L.append("> 暂未检测到明显负面评论 ✅\n")

    # 2-4 好评亮点
    L += ["### ✨ 好评亮点（正面高赞评论 Top 5）\n"]
    if insights["highlights"]:
        for i, c in enumerate(insights["highlights"], 1):
            loc  = f"·{c['ip_location']}" if c["ip_location"] else ""
            name = c["author_name"] or "匿名"
            L.append(f"> **{i}.** {c['text']}")
            L.append(f"> — {name}{loc}　👍 {c['like_count']} 赞\n")
    else:
        L.append("> 暂未检测到明显正面评论\n")

    L.append("---")

    # ══════════════════════════════════════════
    # 📊 模块三：数据解读
    # ══════════════════════════════════════════
    L += ["\n## 📊 模块三：数据解读\n"]

    # 3-1 互动总览
    L += [
        "### 📈 互动数据总览\n",
        f"| 维度 | 数值 |",
        f"|------|------|",
        f"| 📄 内容总数 | {len(posts):,} |",
        f"| 💬 评论总数 | {data['total_comments']:,} |",
        f"| ❤️ 总点赞数 | {data['total_likes']:,} |",
        f"| 🔁 总分享数 | {data['total_shares']:,} |",
        f"| ⭐ 总收藏数 | {data['total_collects']:,} |",
    ]

    # 3-2 互动排行
    L += ["\n### 🏆 内容互动排行 Top 10\n",
          "| # | 标题摘要 | 💬评论 | ❤️点赞 | 🔁分享 | 日期 |",
          "|:-:|---------|------:|------:|------:|------|"]
    for i, p in enumerate(data["top_engage"], 1):
        title = (p["title"] or p["text"] or "—")[:25]
        date  = epoch_to_str(p["created_at"])
        L.append(f"| {i} | {title} | {p['comment_count']:,} | {p['like_count']:,} | {p['share_count']:,} | {date} |")

    # 3-3 地域分布
    L += ["\n### 🗺️ 评论地域分布 Top 10\n", "| 地区 | 评论数 | 占比 |", "|------|:------:|:----:|"]
    total_loc = sum(cnt for _, cnt in data["loc_dist"]) or 1
    for loc, cnt in data["loc_dist"]:
        pct = round(cnt / total_loc * 100, 1)
        b   = bar(cnt, total_loc, 8)
        L.append(f"| {loc} | {cnt} | `{b}` {pct}% |")

    # 3-4 KOL 分析
    L += ["\n### 👑 KOL / 活跃用户分析 Top 8\n",
          "| 用户名 | 累计获赞 | 评论条数 |",
          "|--------|:--------:|:--------:|"]
    for name, total_like in data["kol_list"]:
        cmt_cnt = data["author_count"].get(name, 0)
        L.append(f"| **{name}** | {total_like:,} | {cmt_cnt} |")

    # ── 尾部
    L += [
        "\n---",
        "\n> 📌 **报告由 pmflow MCP 自动生成** | 数据仅来源于本地抖音离线样本",
    ]

    return "\n".join(L)


# ── 入口 ──────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="续火花")
    parser.add_argument("--db",    default="data/pmflow.db")
    parser.add_argument("--out",   default="outputs")
    args = parser.parse_args()

    report_md = build_report(args.query, args.db)

    out_dir  = os.path.join(args.out, args.query)
    os.makedirs(out_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = os.path.join(out_dir, f"report_{date_str}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    print(report_md)
    print(f"\n✅ 报告已保存：{out_path}")


if __name__ == "__main__":
    main()
