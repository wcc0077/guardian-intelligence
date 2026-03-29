# 👁️ 守护神情报局

AI科技情报自动采集与展示系统。

**站点：** https://wcc0077.github.io/guardian-intelligence

---

## 工作原理

```
定时采集（每小时）
    ↓
guardian_briefing.py
    ├── 36kr RSS
    ├── HackerNews Top Stories
    ├── GitHub Trending
    ├── MIT Tech Review
    ├── Solidot
    └── ScienceDaily AI
    ↓
MiniMax LLM 评估信号价值（0-100分）
    ↓
结构化简报 → data/latest.json
    ↓
GitHub Push → GitHub Pages 自动更新
```

## 数据来源

| 来源 | 类型 | 更新频率 |
|------|------|---------|
| 36氪 | RSS | 实时 |
| HackerNews | API | 实时 |
| GitHub Trending | API | 每小时 |
| MIT Tech Review | RSS | 实时 |
| Solidot | RSS | 实时 |
| ScienceDaily AI | RSS | 实时 |

## 本地运行

```bash
# 克隆
git clone https://github.com/wcc0077/guardian-intelligence.git
cd guardian-intelligence

# 安装依赖
pip install requests beautifulsoup4

# 运行采集
MINIMAX_API_KEY=your_key python3.11 scripts/guardian_briefing.py
```

## 自动化

定时任务由守护神服务器（OpenClaw cron）驱动，每小时自动：
1. 采集最新情报
2. LLM 评估信号价值
3. 生成简报 JSON
4. 推送到 GitHub
5. GitHub Pages 自动更新展示

---

*👁️ 由守护神 (Guardian) 自动运行*
