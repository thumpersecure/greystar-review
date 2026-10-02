#!/usr/bin/env python3
"""Daily sweep: Google News RSS -> scored candidates -> GitHub issues (label: candidate) -> ntfy.
Nothing is published here; an issue labeled `approved` is what adds an entry (see approve.py)."""
import html, json, os, re, sys, time, urllib.parse, urllib.request, hashlib
from email.utils import parsedate_to_datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEN = os.path.join(ROOT, 'data', 'seen.json')
ENTRIES = os.path.join(ROOT, 'data', 'entries.json')
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36'}
GRIEV = '(lawsuit OR sued OR settlement OR fine OR fined OR tenants OR eviction OR evicted OR mold OR "junk fees" OR price-fixing OR RealPage OR violation OR investigation OR complaint OR uninhabitable OR retaliation OR discrimination)'
QUERIES = [
    f'Greystar {GRIEV}',
    '"Bob Faith" Greystar',
    '"Robert Faith" Greystar',
    f'"Greystar Real Estate Partners" {GRIEV}',
    f'"Riverstone Residential" {GRIEV}',
]
GRIEVANCE_WORDS = ['lawsuit','sued','sues','suit','settle','fine','fined','penalty','tenant','evict','mold','junk fee',
    'hidden fee','price-fix','price fix','realpage','antitrust','violation','investigat','complain','uninhabitable',
    'retaliat','discriminat','attorney general','ftc','doj','class action','flood','infest','displaced','unsafe','repairs']

def score(title: str, outlet: str) -> int:
    """Relevance score for a headline; candidates scoring >= 2 become issues."""
    t = title.lower()
    s = 0
    if 'greystar' in t or 'bob faith' in t or 'robert faith' in t or 'riverstone' in t:
        s += 2
    s += sum(1 for w in GRIEVANCE_WORDS if w in t)
    # TODO(human): tune scoring — demote noise (dev/financing deals, "acquires", "breaks ground",
    # market reports) and/or boost high-value outlets. Return the adjusted int.
    return s

def fetch(q):
    url = 'https://news.google.com/rss/search?q=' + urllib.parse.quote(q + ' when:7d') + '&hl=en-US&gl=US&ceid=US:en'
    x = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode('utf-8', 'replace')
    out = []
    for it in re.findall(r'<item>(.*?)</item>', x, re.S):
        g = lambda p: (m.group(1) if (m := re.search(p, it, re.S)) else '')
        title = html.unescape(g(r'<title>(.*?)</title>'))
        outlet = html.unescape(g(r'<source url="[^"]*"[^>]*>(.*?)</source>'))
        if outlet and title.endswith(' - ' + outlet):
            title = title[: -len(outlet) - 3]
        try:
            date = parsedate_to_datetime(g(r'<pubDate>(.*?)</pubDate>')).strftime('%Y-%m-%d')
        except Exception:
            date = time.strftime('%Y-%m-%d')
        out.append({'title': title.strip(), 'outlet': outlet, 'link': html.unescape(g(r'<link>(.*?)</link>')).strip(), 'date': date})
    return out

def key(title):
    return hashlib.sha1(re.sub(r'[^a-z0-9]', '', title.lower()).encode()).hexdigest()[:16]

def gh(method, path, body=None):
    req = urllib.request.Request('https://api.github.com/repos/' + os.environ['GITHUB_REPOSITORY'] + path,
        data=json.dumps(body).encode() if body else None, method=method,
        headers={'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'], 'Accept': 'application/vnd.github+json'})
    return json.loads(urllib.request.urlopen(req, timeout=30).read() or b'{}')

def slug(s):
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', s.lower())).strip('-')[:70]

def main():
    seen = json.load(open(SEEN)) if os.path.exists(SEEN) else {}
    known = {key(e['title']) for e in json.load(open(ENTRIES))}
    fresh = {}
    for q in QUERIES:
        try:
            for h in fetch(q):
                k = key(h['title'])
                if k in seen or k in known or k in fresh:
                    continue
                h['score'] = score(h['title'], h['outlet'])
                fresh[k] = h
        except Exception as ex:
            print('query failed:', q, ex, file=sys.stderr)
        time.sleep(2)
    made, cap = [], int(os.environ.get('MAX_ISSUES', '15'))
    for k, h in sorted(fresh.items(), key=lambda kv: -kv[1]['score']):
        if h['score'] < 2:
            seen[k] = h['date']; continue
        if len(made) >= cap:
            continue  # left unseen so it rolls over to the next run
        seen[k] = h['date']
        cat = 'lawsuit' if re.search(r'lawsuit|sued|sues|class action|court', h['title'], re.I) else \
              'regulator' if re.search(r'attorney general|ftc|doj|hud|eeoc|fined|penalt|regulator', h['title'], re.I) else 'news'
        draft = {'id': slug(h['title']) + '-' + h['date'][:4], 'date': h['date'], 'title': h['title'], 'category': cat,
                 'subject': ['greystar', 'bob-faith'] if re.search(r'faith', h['title'], re.I) else ['greystar'],
                 'location': '', 'property': '', 'outlet': h['outlet'], 'url': h['link'], 'archive_url': '',
                 'summary': '', 'status': 'published'}
        body = (f"**{h['title']}** — {h['outlet']} ({h['date']}) · score {h['score']}\n\n[Open article]({h['link']})\n\n"
                "Edit the JSON below if needed (summary, location, real article URL), then add the **approved** label "
                "to publish, or **rejected** to discard.\n\n```json\n" + json.dumps(draft, indent=2) + "\n```")
        if os.environ.get('DRY_RUN'):
            print('DRY', h['score'], h['title'], '|', h['outlet']); made.append((h['title'], '')); continue
        iss = gh('POST', '/issues', {'title': 'Candidate: ' + h['title'][:200], 'body': body, 'labels': ['candidate']})
        made.append((h['title'], iss.get('html_url', '')))
    if not os.environ.get('DRY_RUN'):
        json.dump(seen, open(SEEN, 'w'), indent=0, sort_keys=True)
    print(f'{len(fresh)} new headlines, {len(made)} candidates')
    topic = os.environ.get('NTFY_TOPIC')
    if made and topic:
        msg = '\n'.join(f'• {t}' for t, _ in made[:8]) + (f'\n…and {len(made)-8} more' if len(made) > 8 else '')
        repo = os.environ['GITHUB_REPOSITORY']
        hdr = {'Title': f'Greystar Review: {len(made)} new candidate(s)', 'Tags': 'newspaper',
               'Click': f'https://github.com/{repo}/issues?q=is%3Aopen+label%3Acandidate'}
        if os.environ.get('NTFY_TOKEN'):
            hdr['Authorization'] = 'Bearer ' + os.environ['NTFY_TOKEN']  # topic is reserved
        urllib.request.urlopen(urllib.request.Request('https://ntfy.sh/' + topic, data=msg.encode(), headers=hdr), timeout=20)

if __name__ == '__main__':
    main()
