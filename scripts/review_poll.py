#!/usr/bin/env python3
"""Cron replacement for the approve workflow: publish issues labeled `approved`, close `rejected` ones."""
import json, os, re, subprocess, sys, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO, TOKEN = os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_TOKEN']
ENTRIES = os.path.join(ROOT, 'data', 'entries.json')

def gh(method, path, body=None):
    req = urllib.request.Request(f'https://api.github.com/repos/{REPO}{path}', method=method,
        data=json.dumps(body).encode() if body else None,
        headers={'Authorization': 'Bearer ' + TOKEN, 'Accept': 'application/vnd.github+json'})
    return json.loads(urllib.request.urlopen(req, timeout=30).read() or b'null')

def comment_close(n, msg):
    gh('POST', f'/issues/{n}/comments', {'body': msg})
    gh('PATCH', f'/issues/{n}', {'state': 'closed'})

added = []
for label in ('approved', 'rejected'):
    for iss in gh('GET', f'/issues?state=open&labels={label}&per_page=50'):
        n = iss['number']
        if label == 'rejected':
            comment_close(n, 'Rejected — not published.'); continue
        m = re.search(r'```json\s*(\{.*?\})\s*```', iss.get('body') or '', re.S)
        try:
            e = json.loads(m.group(1)) if m else None
        except json.JSONDecodeError as ex:
            e = None; err = str(ex)
        if not e:
            comment_close(n, 'Could not read the JSON block — fix it and reopen with the approved label.'); continue
        missing = [k for k in ('id', 'date', 'title', 'category', 'subject', 'url') if not e.get(k)]
        if missing or e['category'] not in ('lawsuit', 'regulator', 'news', 'tenant'):
            comment_close(n, f'Not published: missing/invalid {missing or "category"}. Fix the JSON and reopen.'); continue
        for k in ('location', 'property', 'outlet', 'archive_url', 'summary', 'status'):
            e.setdefault(k, '')
        entries = json.load(open(ENTRIES))
        if not any(x['id'] == e['id'] or x['url'] == e['url'] for x in entries):
            entries.append(e); entries.sort(key=lambda x: x['date'], reverse=True)
            json.dump(entries, open(ENTRIES, 'w'), indent=1, ensure_ascii=False)
            added.append((n, e['title']))
        else:
            comment_close(n, 'Already in the archive.')
if added:
    if os.path.exists(os.path.join(ROOT, 'scripts', 'build_site.py')):
        subprocess.run([sys.executable, 'scripts/build_site.py'], cwd=ROOT, check=True)
    subprocess.run(['git', 'add', '-A'], cwd=ROOT, check=True)
    subprocess.run(['git', 'commit', '-qm', 'add: ' + '; '.join(t for _, t in added)[:200]], cwd=ROOT, check=True)
    subprocess.run(['git', 'push', '-q'], cwd=ROOT, check=True)
    for n, _ in added:
        comment_close(n, 'Published to The Greystar Review.')
print(f'published {len(added)}')
