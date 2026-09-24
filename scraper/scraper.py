# -*- coding: utf-8 -*-
"""
黑客松数据抓取与合并脚本

用法:
    python scraper/scraper.py            # 正常运行：抓取 + 合并
    python scraper/scraper.py --dry-run  # 只打印结果，不写文件

数据流:
    各数据源(见 SOURCES) --抓取+关键词过滤--> 抓取条目
    data/manual.json (手动维护, 优先级最高)
        |--按 id + 标题去重合并--> data/hackathons.json (前端读取)

数据源优先级(同名活动先到先得):
    manual > ai-pick > huodongxing > modelscope > segmentfault
"""

import hashlib
import json
import os
import re
import ssl
import sys
import urllib.parse
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
TODAY = datetime.now(TZ_BEIJING).date()

# 标题命中任一关键词即视为黑客松类活动（不区分大小写）
HACK_KEYWORDS = [
    '黑客松', '黑客马拉松', 'hackathon', '编程马拉松', '创客马拉松',
    '创意马拉松', '48小时', '48h', '48 小时', '极客挑战', '创新挑战赛',
    '开发大赛', '创新大赛', '创客大赛', '开发者大赛',
]

# 标签推断规则: (标签, 关键词列表)
TAG_RULES = [
    ('AI', ['ai', '人工智能', '大模型', 'llm', 'aigc', 'agent', '智能体',
            '机器学习', '深度学习', 'gpt', 'mcp']),
    ('Web3', ['web3', '区块链', 'blockchain', '以太坊', 'eth', 'crypto',
              'defi', 'nft', '链上', '数字资产', 'avax', 'usdt']),
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
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            return _OPENER.open(req, timeout=TIMEOUT).read().decode('utf-8', 'ignore')
        except Exception as e:
            last_err = e
    raise last_err


def ts_to_date(ts):
    """unix 时间戳(秒/毫秒自适应) -> 北京时间 YYYY-MM-DD"""
    if not ts:
        return ''
    if ts > 1e12:
        ts /= 1000.0
    return datetime.fromtimestamp(ts, TZ_BEIJING).strftime('%Y-%m-%d')


def parse_date(v):
    """自适应解析日期: unix 时间戳 / ISO 字符串 -> YYYY-MM-DD，失败返回 ''"""
    if v in (None, '', 0):
        return ''
    if isinstance(v, (int, float)):
        return ts_to_date(v)
    s = str(v).strip()
    if re.fullmatch(r'\d{10}', s):
        return ts_to_date(int(s))
    m = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', s)
    if m:
        return '%04d-%02d-%02d' % (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return ''


def is_recent(e):
    """结束/截止日期在 30 天前之前的活动不再保留"""
    for key in ('end', 'reg_deadline'):
        v = e.get(key) or ''
        if v:
            try:
                d = datetime.strptime(v, '%Y-%m-%d').date()
                if d < TODAY - timedelta(days=30):
                    return False
            except ValueError:
                pass
    return True


def _is_hackathon(title):
    low = title.lower()
    return any(kw in low for kw in HACK_KEYWORDS)


def _guess_tags(title):
    low = title.lower()
    tags = [tag for tag, kws in TAG_RULES if any(kw in low for kw in kws)]
    return tags or ['综合']


def _make_id(prefix, key):
    return '%s-%s' % (prefix, hashlib.md5(str(key).encode('utf-8')).hexdigest()[:10])


# 主要城市列表：活动行城市形如"四川成都"，归一化为"成都"便于同城筛选
MAJOR_CITIES = [
    '北京', '上海', '广州', '深圳', '杭州', '武汉', '成都', '长沙', '南京',
    '西安', '重庆', '天津', '苏州', '厦门', '青岛', '郑州', '宁波', '东莞',
    '佛山', '石家庄', '合肥', '济南', '沈阳', '大连', '福州', '昆明', '贵阳',
    '南昌', '长春', '哈尔滨', '太原', '无锡', '常州', '珠海', '海口', '兰州',
    '乌鲁木齐', '香港', '澳门',
]


def _norm_city(s):
    for c in MAJOR_CITIES:
        if c in s:
            return c
    return s


# ---------------- 数据源 1: AI 活动雷达 (hope0719.github.io/ai-pick) ----------------
# 只保留国内及可线上参与的全球活动，过滤日/美/欧等海外线下场次
AI_PICK_KEEP_REGIONS = ('中国', '全球', '亚太', '亚洲', '线上')


def fetch_ai_pick():
    """AI 活动雷达的公开数据文件，type=黑客松 的条目字段最全"""
    data = json.loads(http_get('https://hope0719.github.io/ai-pick/data.json'))
    out = []
    for a in data.get('activities') or []:
        if (a.get('type') or '') != '黑客松':
            continue
        title = (a.get('title') or '').strip()
        if not title or not a.get('url'):
            continue
        region = (a.get('region') or '').strip()
        if region and not any(region.startswith(r) for r in AI_PICK_KEEP_REGIONS):
            continue
        online = ('线上' in region) or ('online' in region.lower()) or region in ('全球', '')
        out.append({
            'id': _make_id('aipick', a['url']),
            'name': title,
            'org': (a.get('vendor') or '').strip(),
            'tags': _guess_tags(title),
            'city': region or ('线上' if online else '未知'),
            'online': online,
            'venue': '',
            'start': parse_date(a.get('startAt')),
            'end': parse_date(a.get('endAt')),
            'reg_deadline': parse_date(a.get('deadline_date')),
            'fee': '',
            'prize': 0,
            'prize_text': (a.get('reward') or '').strip(),
            'url': a['url'],
            'source': 'ai-pick',
        })
    return [e for e in out if is_recent(e)]


# ---------------- 数据源 2: 活动行 ----------------
def fetch_huodongxing():
    """活动行搜索页（带查询参数时服务端渲染），搜"黑客松"和"黑客马拉松"两个词"""
    out, seen = [], set()
    for kw in ('黑客松', '黑客马拉松'):
        url = 'https://www.huodongxing.com/search?ps=20&pi=0&list=list&qs=%s&st=1,4' \
              % urllib.parse.quote(kw)
        html = http_get(url)
        # 事件块: <a class="item-title" href="/event/{id}?utm..."> 标题链接（href 带 utm 参数）
        for m in re.finditer(r'<a[^>]*class="[^"]*item-title[^"]*"[^>]*href="(/event/\d+)[^"]*"[^>]*>', html):
            tag = m.group(0)
            link = m.group(1)
            tm = re.search(r'title="([^"]+)"', tag) or re.search(r'>([^<]+)</a>$', tag)
            title = tm.group(1).strip() if tm else ''
            if link in seen or not title:
                continue
            seen.add(link)
            chunk = html[m.end():m.end() + 3000]
            cm = re.search(r'class="item-dress-pp"[^>]*>\s*([^<]{1,20}?)\s*<', chunk)
            city = _norm_city(cm.group(1).strip()) if cm else ''
            dm = re.search(r'(\d{2})月(\d{2})日', chunk)
            start = ''
            if dm:
                mon, day = int(dm.group(1)), int(dm.group(2))
                year = TODAY.year
                try:
                    d0 = datetime(year, mon, day).date()
                    if d0 < TODAY - timedelta(days=45):
                        year += 1
                    start = '%04d-%02d-%02d' % (year, mon, day)
                except ValueError:
                    pass
            out.append({
                'id': _make_id('hdx', link),
                'name': title,
                'org': '',
                'tags': _guess_tags(title),
                'city': city or '未知',
                'online': '线上' in city,
                'venue': '',
                'start': start,
                'end': '',
                'reg_deadline': '',
                'fee': '',
                'prize': 0,
                'prize_text': '',
                'url': 'https://www.huodongxing.com' + link,
                'source': 'huodongxing',
            })
    return [e for e in out if is_recent(e)]


# ---------------- 数据源 3: 魔搭社区 ----------------
def fetch_modelscope():
    """魔搭社区比赛/活动 API，按关键词过滤出黑客松类"""
    out, seen = [], set()
    for page in (1, 2, 3):
        try:
            data = json.loads(http_get(
                'https://modelscope.cn/api/v1/competitions?pageNumber=%d' % page))
        except Exception:
            break
        races = (data.get('Data') or {}).get('Races') or []
        if not races:
            break
        for r in races:
            title = (r.get('Title') or '').strip()
            rid = r.get('Id')
            if not title or rid in seen or not _is_hackathon(title):
                continue
            seen.add(rid)
            online = (r.get('EventType') or '') != 'offline-event'
            out.append({
                'id': 'ms-%s' % rid,
                'name': title,
                'org': '魔搭社区',
                'tags': _guess_tags(title),
                'city': (r.get('EventLocation') or '').strip() or ('线上' if online else '未知'),
                'online': online,
                'venue': '',
                'start': parse_date(r.get('StartTime') or r.get('GmtStart')),
                'end': parse_date(r.get('EndTime') or r.get('GmtEnd')),
                'reg_deadline': parse_date(r.get('RegistrationDeadline')),
                'fee': '',
                'prize': 0,
                'prize_text': '',
                'url': r.get('SignUpUrl') or ('https://modelscope.cn/competition/%s' % rid),
                'source': 'modelscope',
            })
    return [e for e in out if is_recent(e)]


# ---------------- 数据源 4: 思否活动页 ----------------
def fetch_segmentfault():
    """思否活动页（服务端渲染），解析 __NEXT_DATA__ 中的活动列表"""
    events = {}
    for url in ('https://segmentfault.com/events',
                'https://segmentfault.com/events/finished?page=2'):
        for item in _sf_fetch(url):
            events.setdefault(item['id'], item)
    return list(events.values())


def _sf_fetch(url):
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
            'prize': 0,
            'prize_text': '',
            'url': 'https://segmentfault.com/e/%s' % e['id'],
            'source': 'segmentfault',
        })
    return out


SOURCES = [
    ('ai-pick', fetch_ai_pick),
    ('huodongxing', fetch_huodongxing),
    ('modelscope', fetch_modelscope),
    ('segmentfault', fetch_segmentfault),
]

# ---------------- 合并逻辑 ----------------
def _norm_title(t):
    return re.sub(r'[\s·\-—|（）()【】\[\],，。.!！?？:：/\\"\'`]+', '', t).lower()


def merge(source_results, manual):
    """manual 优先；抓取条目按 id 与标准化标题跨源去重（源顺序即优先级）"""
    out, seen_titles = {}, {}
    for e in manual:
        out[e['id']] = e
        seen_titles[_norm_title(e['name'])] = e['id']
    for _name, items in source_results:
        for e in items:
            if e['id'] in out:
                continue
            nt = _norm_title(e['name'])
            if nt in seen_titles:
                continue
            out[e['id']] = e
            seen_titles[nt] = e['id']
    return sorted(out.values(), key=lambda e: (e.get('start') or '9999'))


def main():
    dry_run = '--dry-run' in sys.argv

    source_results, errors = [], []
    for name, fn in SOURCES:
        try:
            items = fn()
            source_results.append((name, items))
            print('[OK] %s: %d 条' % (name, len(items)))
        except Exception as e:
            errors.append('%s: %s: %s' % (name, type(e).__name__, e))
            print('[FAIL] %s -> %s: %s' % (name, type(e).__name__, e))

    manual = []
    if os.path.exists(MANUAL_FILE):
        with open(MANUAL_FILE, encoding='utf-8') as f:
            manual = json.load(f)
        print('[OK] manual: %d 条' % len(manual))
    else:
        print('[WARN] manual.json 不存在，跳过')

    merged = merge(source_results, manual)
    result = {
        'updated_at': datetime.now(TZ_BEIJING).strftime('%Y-%m-%d %H:%M'),
        'counts': {
            'total': len(merged),
            'scraped': sum(len(items) for _n, items in source_results),
            'manual': len(manual),
        },
        'errors': errors,
        'events': merged,
    }

    if dry_run:
        for e in merged:
            print('%s | %s | %s | %s | ddl=%s | %s' % (
                e['source'], e['name'][:36], e['city'], e['start'], e['reg_deadline'], e['url'][:60]))
        print('共 %d 条' % len(merged))
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print('[DONE] 写入 %s，共 %d 条（抓取 %d + 手动 %d）' % (
        OUTPUT_FILE, result['counts']['total'], result['counts']['scraped'], len(manual)))

    # 抓取源全部失败时退出码非 0，让 CI 能感知（但不阻断——保留旧数据）
    if errors and not source_results:
        print('[ERROR] 所有抓取源均失败')
        sys.exit(1)


if __name__ == '__main__':
    main()
