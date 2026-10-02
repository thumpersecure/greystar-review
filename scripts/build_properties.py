#!/usr/bin/env python3
"""Build data/properties.json from greystar.com's property + city sitemaps."""
import json, os, re, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/128'}
get = lambda u: urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read().decode()
pdp = re.findall(r'<loc>https://www\.greystar\.com/([^<]+)/p_(\d+)</loc>', get('https://www.greystar.com/sitemap-pdp.xml'))
cities = set(re.findall(r'<loc>https://www\.greystar\.com/s/([a-z0-9-]+-[a-z]{2})</loc>', get('https://www.greystar.com/sitemap-search.xml')))
SMALL = {'at','of','on','the','and','in','by','de','la','del'}
def title(s):
    w = s.split('-')
    return ' '.join(x if i and x in SMALL else x.upper() if len(x) <= 2 and not x.isalpha() else x.capitalize() for i, x in enumerate(w))
INTL = {'british-columbia': 'British Columbia, Canada', 'alberta': 'Alberta, Canada', 'ontario': 'Ontario, Canada',
        'netherlands': 'Netherlands', 'spain': 'Spain', 'ireland': 'Ireland', 'germany': 'Germany', 'australia': 'Australia',
        'france': 'France', 'brazil': 'Brazil', 'chile': 'Chile', 'austria': 'Austria', 'uk': 'United Kingdom'}
out = []
for slug, pid in pdp:
    region = next((v for k, v in INTL.items() if slug.endswith('-' + k)), None)
    if region:
        k = next(k for k in INTL if slug.endswith('-' + k))
        parts = slug[: -len(k) - 1].split('-')
        out.append({'n': title('-'.join(parts[:-1])), 'c': parts[-1].capitalize(), 's': region, 'id': pid, 'slug': slug})
        continue
    parts = slug.split('-')
    st, name, city = parts[-1].upper(), slug, ''
    for n in range(min(5, len(parts) - 2), 0, -1):       # longest known city suffix wins
        cand = '-'.join(parts[-n - 1:])
        if cand in cities:
            name, city = '-'.join(parts[:-n - 1]), ' '.join(p.capitalize() for p in parts[-n - 1:-1]); break
    else:
        name, city = '-'.join(parts[:-2]), parts[-2].capitalize()
    out.append({'n': title(name), 'c': city, 's': st if len(parts[-1]) == 2 else '', 'id': pid, 'slug': slug})
out.sort(key=lambda p: (p['s'] or 'ZZ', p['c'], p['n']))
json.dump(out, open(os.path.join(ROOT, 'data', 'properties.json'), 'w'), separators=(',', ':'), ensure_ascii=False)
print(len(out), 'properties;', len({p['s'] for p in out}), 'states/regions;', sum(1 for p in out if not p['s']), 'non-US-format')
