#!/usr/bin/env python3
"""Merge data/seed/*.json into data/entries.json (dedupe by id and url)."""
import glob, json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path = os.path.join(ROOT, 'data', 'entries.json')
entries = json.load(open(path)) if os.path.exists(path) else []
ids, urls = {e['id'] for e in entries}, {e['url'] for e in entries}
for f in sorted(glob.glob(os.path.join(ROOT, 'data', 'seed', '*.json'))):
    for e in json.load(open(f)):
        if e['id'] in ids or (e['url'] in urls and e['category'] != 'tenant'):
            continue  # tenant reviews often share one listing-page URL
        entries.append(e); ids.add(e['id']); urls.add(e['url'])
entries.sort(key=lambda x: x['date'], reverse=True)
json.dump(entries, open(path, 'w'), indent=1, ensure_ascii=False)
print(len(entries), 'entries')
