# 中国黑客松日历

搜集当前国内黑客松（含黑客马拉松类创新赛事）的静态网页：时间、地点、主题、报名截止、奖励、直达链接，支持按标签筛选、按时间/截止/奖金排序、同城优先。

## 使用

- 本地预览：`python -m http.server` 后访问 <http://localhost:8000> （直接双击 index.html 会因 file:// 协议无法加载数据）

- 线上：push 到 GitHub 后，仓库 Settings → Pages → 选 main 分支即可开启，地址为 `https://<用户名>.github.io/<仓库名>/`

## 数据更新

数据文件 `data/hackathons.json` 由手动条目 + 多个自动抓取源合并生成：

| 来源 | 说明 |
|---|---|
| `data/manual.json` | 手动维护的条目，**优先级最高**，不会被脚本覆盖 |
| AI 活动雷达（hope0719.github.io/ai-pick） | 聚合数据文件，字段最全（截止时间/奖励/主办方），仅保留国内及全球线上场次 |
| 活动行（huodongxing.com） | 搜索"黑客松/黑客马拉松"，线下活动城市信息最准 |
| 魔搭社区（modelscope.cn） | 官方比赛 API，含报名截止时间 |
| 思否活动页（segmentfault.com/events） | 开发者活动，含报名截止时间 |
| 赛氪竞赛网（saikr.com） | 大学生 AI/计算机类竞赛，含报名截止与比赛时间 |

跨源按标题去重（源优先级：manual > ai-pick > 活动行 > 魔搭 > 思否 > 赛氪），同一活动只保留一条。

更新方式：

1. **自动**：GitHub Actions 每天北京时间 08:00 运行 `scraper/scraper.py`，抓取并自动提交（见 `.github/workflows/update.yml`）
2. **手动**：本地运行 `python scraper/scraper.py` 后提交；想添加新活动直接编辑 `data/manual.json`（字段结构参照已有条目）

某抓取源失败时脚本会跳过该源并保留旧数据，不影响其他来源。页面右下角显示数据更新时间。

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

