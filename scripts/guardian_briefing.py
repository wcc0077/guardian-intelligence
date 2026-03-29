#!/usr/bin/env python3
"""
守护神情报简报 · 高效采集 + LLM总结
2026-03-29
"""

import os, re, json, sqlite3
import requests
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
import warnings
from bs4 import XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

BASE_DIR   = Path("~/.openclaw/workspace").expanduser()
INTEL_DIR  = BASE_DIR / "intelligence"
MINIMAX_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_BASE = "https://api.minimaxi.com"
HEADERS    = {"User-Agent": "Mozilla/5.0 (GuardianBot/1.0; +https://guardian.ai)"}
TIMEOUT    = 8

# ── 情报来源配置 ─────────────────────────────────────────────────────────────
SOURCES = [
    {
        "name": "36氪",
        "url":  "https://36kr.com/feed",
        "type": "rss",
        "tags": ["科技", "创业", "投资", "AI"],
        "weight": 10,   # 权重（决定是否进入精选）
    },
    {
        "name": "Solidot",
        "url":  "https://www.solidot.org/index.rss",
        "type": "rss",
        "tags": ["科技", "开源", "安全", "AI"],
        "weight": 7,
    },
    {
        "name": "MIT Tech Review",
        "url":  "https://www.technologyreview.com/feed/",
        "type": "rss",
        "tags": ["AI", "科技", "深度"],
        "weight": 9,
    },
    {
        "name": "HackerNews",
        "url":  "https://hacker-news.firebaseio.com/v0/topstories.json",
        "type": "hn",
        "tags": ["科技", "创业", "开源", "AI"],
        "weight": 8,
    },
    {
        "name": "GitHub Trending",
        "url":  "https://api.github.com/search/repositories",
        "type": "github",
        "params": {"q": "created:>2026-03-20", "sort": "stars", "order": "desc", "per_page": 15},
        "tags": ["AI", "开源", "工具"],
        "weight": 8,
    },
    {
        "name": "ScienceDaily AI",
        "url":  "https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml",
        "type": "rss",
        "tags": ["AI", "研究", "技术"],
        "weight": 6,
    },
]

# ── 采集 ───────────────────────────────────────────────────────────────────

def fetch_rss(source):
    """抓取RSS源，返回标题列表"""
    try:
        r = requests.get(source["url"], headers=HEADERS, timeout=TIMEOUT)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        items = []
        for item in soup.select("item")[:8]:
            title = item.select_one("title")
            link  = item.select_one("link")
            desc  = item.select_one("description")
            items.append({
                "title":  title.text.strip() if title else "",
                "url":    link.text.strip()  if link  else "",
                "desc":   re.sub(r'<[^>]+>', '', desc.text.strip() if desc else "")[:100],
                "source": source["name"],
                "tags":   source["tags"],
                "weight": source["weight"],
            })
        return items
    except Exception as e:
        return [{"title": f"[{source['name']} 抓取失败] {e}", "url": "", "desc": "", "source": source["name"], "tags": [], "weight": 0}]

def fetch_hackernews():
    """抓取HackerNews Top"""
    try:
        r = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", headers=HEADERS, timeout=TIMEOUT)
        ids = r.json()[:10]
        items = []
        for hid in ids:
            s = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{hid}.json", headers=HEADERS, timeout=TIMEOUT).json()
            if s:
                items.append({
                    "title":  s.get("title", ""),
                    "url":    s.get("url", f"https://news.ycombinator.com/item?id={hid}"),
                    "desc":   s.get("text", "")[:100],
                    "source": "HackerNews",
                    "tags":   ["科技", "创业", "AI"],
                    "weight": 8,
                })
        return items
    except Exception as e:
        return [{"title": f"[HN抓取失败] {e}", "url": "", "desc": "", "source": "HackerNews", "tags": [], "weight": 0}]

def fetch_github_trending():
    """抓取GitHub新晋高星项目"""
    try:
        r = requests.get(
            "https://api.github.com/search/repositories",
            params={"q": "created:>2026-03-20", "sort": "stars", "order": "desc", "per_page": 15},
            headers={**HEADERS, "Accept": "application/vnd.github.v3+json"},
            timeout=TIMEOUT
        )
        items = r.json().get("items", [])
        return [{
            "title": f"[GitHub] {i['full_name']} ⭐{i.get('stargazers_count',0)}",
            "url":   i.get("html_url", ""),
            "desc":  i.get("description", "")[:100],
            "source": "GitHub",
            "tags":  ["AI", "开源", "工具"],
            "weight": 8,
        } for i in items[:10]]
    except Exception as e:
        return [{"title": f"[GitHub抓取失败] {e}", "url": "", "desc": "", "source": "GitHub", "tags": [], "weight": 0}]

# ── LLM 总结 ────────────────────────────────────────────────────────────────

def llm_summarize(title, source, desc):
    """
    用MiniMax判断是否重要 + 生成一句话摘要
    返回 (score: int, summary: str)
    """
    if not MINIMAX_KEY:
        kw_flag = any(k in title for k in ["融资", "发布", "突破", "合作", "AI", "开源"])
        return (80 if kw_flag else 50), ""

    prompt = (
        f'判断以下新闻是否重要。重要=涉及AI/科技行业趋势、投资并购、重大技术突破、政策变化。'
        f'是重要新闻返回JSON：{{"score":<0-100>,"summary":"<20字中文摘要>"}}'
        f'否则返回：{{"score":<0-30>,"summary":""}}'
        f'标题：{title}  来源：{source}  描述：{desc[:80]}'
    )

    try:
        resp = requests.post(
            f"{MINIMAX_BASE}/v1/text/chatcompletion_v2",
            headers={"Authorization": f"Bearer {MINIMAX_KEY}", "Content-Type": "application/json"},
            json={
                "model": "MiniMax-M2.7-highspeed",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 400,
                "temperature": 0.1
            },
            timeout=20
        )
        msg  = resp.json()["choices"][0]["message"]
        cont = msg.get("content", "") or msg.get("reasoning_content", "")
        m    = re.search(r'\{\s*"score"\s*:\s*(\d+)\s*,\s*"summary"\s*:\s*"([^"]*)"', cont)
        if m:
            return int(m.group(1)), m.group(2)
        return 50, ""
    except:
        return 50, ""

def llm_digest(all_signals):
    """
    把所有高价值信号汇总成结构化简报
    返回markdown字符串
    """
    if not all_signals:
        return "📭 今日未发现重大信号。"

    # 按分数组
    all_signals.sort(key=lambda x: -x["score"])

    # 构建输入
    signal_text = "\n".join([
        f"- [{s['source']}] ⭐{s['score']} {s['title']}"
        f"{' | ' + s['summary'] if s['summary'] else ''}"
        for s in all_signals[:15]
    ])

    if not MINIMAX_KEY:
        # 无API时直接返回列表
        lines = [f"## 📊 今日情报简报 · {datetime.now().strftime('%m-%d %H:%M')}"]
        lines.append("")
        for s in all_signals[:10]:
            lines.append(f"### ⭐{s['score']} | {s['source']}")
            lines.append(f"**{s['title']}**")
            if s.get("summary"):
                lines.append(f"_{s['summary']}_")
            if s.get("url"):
                lines.append(f"🔗 {s['url']}")
            lines.append("")
        return "\n".join(lines)

    prompt = (
        f"你是一个科技情报分析师。根据以下新闻列表，生成一份结构化简报。\n"
        f"格式要求：\n"
        f"- 分三个板块：【今日要点】【值得深挖】【工具/开源推荐】\n"
        f"- 每个板块不超过5条\n"
        f"- 每条不超过30字\n"
        f"- 最后给一个今日AI行业温度的主观评分（0-100）\n"
        f"新闻列表：\n{signal_text}\n"
        f"直接输出markdown，不要解释。"
    )

    try:
        resp = requests.post(
            f"{MINIMAX_BASE}/v1/text/chatcompletion_v2",
            headers={"Authorization": f"Bearer {MINIMAX_KEY}", "Content-Type": "application/json"},
            json={
                "model": "MiniMax-M2.7-highspeed",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 800,
                "temperature": 0.2
            },
            timeout=30
        )
        msg  = resp.json()["choices"][0]["message"]
        cont = msg.get("content", "") or msg.get("reasoning_content", "")
        # 去掉思考过程
        cont = re.sub(r'思考过程[：:].*?(?=\n|$)', '', cont)
        cont = re.sub(r'Thinking process.*?(?=\n|$)', '', cont, flags=re.DOTALL)
        return cont.strip()
    except Exception as e:
        return f"（LLM总结失败: {e}）\n\n" + "\n".join(
            f"- ⭐{s['score']} {s['title']}" for s in all_signals[:8]
        )

# ── 主流程 ──────────────────────────────────────────────────────────────────

def main():
    print(f"[👁️ 守护神简报] {datetime.now().strftime('%Y-%m-%d %H:%M')} 开始采集...")

    all_items = []

    for src in SOURCES:
        if src["type"] == "hn":
            print(f"  抓取 {src['name']}...")
            all_items.extend(fetch_hackernews())
        elif src["type"] == "github":
            print(f"  抓取 {src['name']}...")
            all_items.extend(fetch_github_trending())
        else:
            print(f"  抓取 {src['name']}...")
            all_items.extend(fetch_rss(src))

    print(f"\n共采集 {len(all_items)} 条，开始LLM评估...")

    # LLM评估
    scored = []
    for item in all_items:
        score, summary = llm_summarize(item["title"], item["source"], item.get("desc",""))
        item["score"]   = score
        item["summary"] = summary
        if score >= 60:
            scored.append(item)
        print(f"  ⭐{score:3d} | {item['source']:12s} | {item['title'][:40]}")

    # 生成简报
    print("\n生成结构化简报...")
    digest = llm_digest(scored)

    # 保存
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    report_file = BASE_DIR / f"briefing_{ts}.md"
    with open(report_file, "w") as f:
        f.write(f"# 📊 守护神情报简报 · {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(digest)
        f.write("\n\n---\n*由守护神雷达 v2 自动生成*\n")

    print(f"\n✅ 简报已保存: {report_file}")
    print("\n" + "="*50)
    print(digest)
    return digest, scored

if __name__ == "__main__":
    digest, signals = main()
