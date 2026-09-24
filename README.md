# 中国黑客松日历

搜集当前国内黑客松（含黑客马拉松类创新赛事）的静态网页：时间、地点、主题、报名截止、奖励、直达链接，支持按标签筛选、按时间/截止/奖金排序、同城优先。

## 使用

- 本地预览：`python -m http.server` 后访问 <http://localhost:8000> （直接双击 index.html 会因 file:// 协议无法加载数据）

- 线上：push 到 GitHub 后，仓库 Settings → Pages → 选 main 分支即可开启，地址为 `https://<用户名>.github.io/<仓库名>/`

## 数据更新

数据文件 `data/hackathons.json` 由两部分合并生成：

| 文件                             | 说明                        |
| ------------------------------ | ------------------------- |
| `data/manual.json`             | 手动维护的条目，**优先级最高**，不会被脚本覆盖 |
| 思否活动页（segmentfault.com/events） | 由脚本自动抓取，按关键词过滤出黑客松类活动     |

更新方式：

1. **自动**：GitHub Actions 每天北京时间 08:00 运行 `scraper/scraper.py`，抓取并自动提交（见 `.github/workflows/update.yml`）
2. **手动**：本地运行 `python scraper/scraper.py` 后提交；想添加新活动直接编辑 `data/manual.json`（字段结构参照已有条目）

某抓取源失败时脚本会跳过该源并保留旧数据，不影响其他来源。

## 手动添加活动

在 `data/manual.json` 中追加：

```json
{
  "id": "manual-唯一ID",
  "name": "活动名称",
  "org": "主办方",
  "tags": ["AI"],
  "city": "北京",
  "online": false,
  "venue": "详细地点（可空）",
  "start": "2026-10-24",
  "end": "2026-10-26",
  "reg_deadline": "2026-10-10",
  "fee": "免费",
  "prize": 100000,
  "prize_text": "¥10万奖金池",
  "url": "https://报名或官网链接",
  "source": "manual"
}
```

`tags` 可选值：AI / Web3 / 硬件 / 应用 / 综合。状态（报名中/即将截止/进行中/待开始/已结束）由前端按当前日期自动计算，无需维护。

## 目录结构

```
index.html                    # 前端单页
data/manual.json              # 手动维护条目（不被覆盖）
data/hackathons.json          # 合并输出（自动生成，勿手动编辑）
scraper/scraper.py            # 抓取与合并脚本（纯标准库）
.github/workflows/update.yml  # 每日定时更新
```

