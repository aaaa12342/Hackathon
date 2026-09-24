# -*- coding: utf-8 -*-
"""
黑客松数据抓取与合并脚本

用法:
    python scraper/scraper.py            # 正常运行：抓取 + 合并
    python scraper/scraper.py --dry-run  # 只打印结果，不写文件

数据流:
    各数据源(目前: 思否活动页) --抓取+关键词过滤--> 抓取条目
    data/manual.json (手动维护, 优先级最高)
        |--按 id 去重合并--> data/hackathons.json (前端读取)
"""

import json
import os
import re
import ssl
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

# ---------------- 路径 ----------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
MANUAL_FILE = os.path.join(DATA_DIR, 'manual.json')
OUTPUT_FILE = os.path.join(DATA_DIR, 'hackathons.json')

# ---------------- 抓取配置 ----------------
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')
TIMEOUT = 20
TZ_BEIJING = timezone(timedelta(hours=8))

# 标题命中任一关键词即视为黑客松类活动（不区分大小写）
HACK_KEYWORDS = [
    '黑客松', '黑客马拉松', 'hackathon', '编程马拉松', '创客马拉松',
    '创意马拉松', '48小时', '48h', '48 小时', '极客挑战', '创新挑战赛',
    '开发大赛', '创新大赛', '创客大赛', '开发者大赛',
]

# 标签推断规则: (标签, 关键词列表)
TAG_RULES = [
    ('AI', ['ai', '人工智能', '大模型', 'llm', 'aigc', 'agent', '智能体',
            '机器学习', '深度学习', 'gpt', 'aigame']),
    ('Web3', ['web3', '区块链', 'blockchain', '以太坊', 'eth', 'crypto',
              'defi', 'nft', '链上', '数字资产']),
    ('硬件', ['硬件', '嵌入式', 'iot', '物联网', '芯片', '机器人',
              'ros', '智能硬件', '开源硬件', 'riscv', 'fpga']),
    ('应用', ['小程序', 'app', '前端', '全栈', '移动应用', '微信', '鸿蒙']),
]

# ---------------- 网络工具 ----------------
_CTG = ssl.create_default_context()
_CTG.check_hostname = False
_CTG.verify_mode = ssl.CERT_NONE
_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),  # 绕过系统代理，避免本地代理干扰
    urllib.request.HTTPSHandler(context=_CTG),
)


def http_get(url, retries=3):
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            return _OPENER.open(req, timeout=TIMEOUT).read().decode('utf-8', 'ignore')
        except Exception as e:
            last_err = e
    raise last_err


def ts_to_date(ts):
    """unix 时间戳 -> 北京时间 YYYY-MM-DD"""
    if not ts:
        return ''
    return datetime.fromtimestamp(ts, TZ_BEIJING).strftime('%Y-%m-%d')


# ---------------- 数据源: 思否活动页 ----------------
def fetch_segmentfault():
    """抓取思否活动页（服务端渲染），返回黑客松类活动列表"""
    events = {}
    # 进行中/即将开始 + 已结束第一页（历史数据可用于回看）
    urls = ['https://segmentfault.com/events']
    for item in _sf_fetch_state(urls[0]):
        events[item['id']] = item

    # 已结束活动再取一页，保证近期结束的也在
    try:
        for item in _sf_fetch_state('https://segmentfault.com/events/finished?page=2'):
            events.setdefault(item['id'], item)
    except Exception:
        pass  # 单页失败不影响整体

    return list(events.values())


def _sf_fetch_state(url):
    """请求思否活动页并解析 __NEXT_DATA__ 中的活动列表"""
    html = http_get(url)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise ValueError('未找到 __NEXT_DATA__，页面结构可能已变化: %s' % url)
    state = json.loads(m.group(1))['props']['pageProps']['initialState']['activity']

    raw = []
    raw.extend(state.get('recommendList') or [])
    raw.extend(state.get('newestList') or [])
    raw.extend((state.get('finishedList') or {}).get('rows') or [])

    out = []
    for e in raw:
        title = (e.get('name') or '').strip()
        if not title or not _is_hackathon(title):
            continue
        city = (e.get('city_name') or '').strip()
        online = (e.get('category_name') or '') == '线上活动'
        out.append({
            'id': 'sf-%s' % e['id'],
            'name': title,
            'org': '',
            'tags': _guess_tags(title),
            'city': '线上' if online else (city or '未知'),
            'online': online,
            'venue': (e.get('address') or '').strip(),
            'start': ts_to_date(e.get('start')),
            'end': ts_to_date(e.get('end')),
            'reg_deadline': ts_to_date(e.get('sign_end')),
            'fee': '',
            'prize_text': '',
            'url': 'https://segmentfault.com/e/%s' % e['id'],
            'source': 'segmentfault',
        })
    return out


def _is_hackathon(title):
    low = title.lower()
    return any(kw in low for kw in HACK_KEYWORDS)


def _guess_tags(title):
    low = title.lower()
    tags = [tag for tag, kws in TAG_RULES if any(kw in low for kw in kws)]
    return tags or ['综合']


# ---------------- 合并逻辑 ----------------
def merge(scrapped, manual):
    """合并抓取数据与手动数据。manual 优先（同 id 覆盖抓取条目）"""
    merged = {e['id']: e for e in scrapped}
    for e in manual:
        merged[e['id']] = e  # 手动条目覆盖抓取条目
    return sorted(merged.values(), key=lambda e: (e.get('start') or '9999'))


def main():
    dry_run = '--dry-run' in sys.argv

    scrapped = []
    errors = []
    try:
        scrapped = fetch_segmentfault()
        print('[OK] segmentfault: %d 条黑客松类活动' % len(scrapped))
    except Exception as e:
        errors.append('segmentfault: %s: %s' % (type(e).__name__, e))
        print('[FAIL] segmentfault -> %s: %s' % (type(e).__name__, e))

    manual = []
    if os.path.exists(MANUAL_FILE):
        with open(MANUAL_FILE, encoding='utf-8') as f:
            manual = json.load(f)
        print('[OK] manual: %d 条' % len(manual))
    else:
        print('[WARN] manual.json 不存在，跳过')

    result = {
        'updated_at': datetime.now(TZ_BEIJING).strftime('%Y-%m-%d %H:%M'),
        'counts': {
            'total': len(merge(scrapped, manual)),
            'scraped': len(scrapped),
            'manual': len(manual),
        },
        'errors': errors,
        'events': merge(scrapped, manual),
    }

    if dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2)[:3000])
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print('[DONE] 写入 %s，共 %d 条（抓取 %d + 手动 %d）' % (
        OUTPUT_FILE, result['counts']['total'], len(scrapped), len(manual)))

    # 抓取源全部失败时退出码非 0，让 CI 能感知（但不阻断——保留旧数据）
    if errors and not scrapped:
        print('[ERROR] 所有抓取源均失败')
        sys.exit(1)


if __name__ == '__main__':
    main()
