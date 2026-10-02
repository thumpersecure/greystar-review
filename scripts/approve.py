#!/usr/bin/env python3
"""Add the JSON draft from an approved candidate issue to data/entries.json."""
import json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRIES = os.path.join(ROOT, 'data', 'entries.json')
REQ = ['id', 'date', 'title', 'category', 'subject', 'url']

ev = json.load(open(os.environ['GITHUB_EVENT_PATH']))
m = re.search(r'```json\s*(\{.*?\})\s*```', ev['issue']['body'] or '', re.S)
if not m:
    sys.exit('no ```json block in issue body')
e = json.loads(m.group(1))
missing = [k for k in REQ if not e.get(k)]
if missing:
    sys.exit('missing fields: ' + ', '.join(missing))
if e['category'] not in ('lawsuit', 'regulator', 'news', 'tenant'):
    sys.exit('bad category: ' + e['category'])
for k in ('location', 'property', 'outlet', 'archive_url', 'summary', 'status'):
    e.setdefault(k, '')
entries = json.load(open(ENTRIES))
if any(x['id'] == e['id'] or x['url'] == e['url'] for x in entries):
    print('already present:', e['id']); sys.exit(0)
entries.append(e)
entries.sort(key=lambda x: x['date'], reverse=True)
json.dump(entries, open(ENTRIES, 'w'), indent=1, ensure_ascii=False)
print('added', e['id'])
