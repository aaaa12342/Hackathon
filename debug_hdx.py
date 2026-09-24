# -*- coding: utf-8 -*-
"""临时调试：查看活动行详情页的日期格式"""
import ssl
import urllib.request
import re

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'}
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx))

# 测试两个事件：一个近期的，一个可疑的老活动
for eid in ('4879783799900', '9504497722600'):
    req = urllib.request.Request('https://www.huodongxing.com/event/%s' % eid, headers=UA)
    html = opener.open(req, timeout=20).read().decode('utf-8', 'ignore')
    print('====', eid, 'len=', len(html))
    for pat in (r'20\d{2}[-/.年]\s?\d{1,2}[-/.月]\s?\d{1,2}日?',
                r'"(beginTime|BeginTime|startTime|time|Time|date|Date)[^,}]{0,30}',
                r'\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}'):
        ms = re.findall(pat, html)[:6]
        print('  ', pat[:30], '->', ms)
