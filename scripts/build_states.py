#!/usr/bin/env python3
"""State reports for The Greystar Review (SEO landing pages).

Called from build_site.main(); can also be run alone:  python3 scripts/build_states.py

Input : content/states/<slug>.md   front matter + Markdown subset (see below)
        data/entries.json          every record whose location resolves to the region
Output: states/<slug>.html (one per file) and states/index.html (hub)

Front matter keys:  region (state code, e.g. CO), slug, name, h1, description,
                    dek, img_alt
Body: '## Heading' sections, paragraphs, '- ' lists, '> ' quotes, [text](url),
      **bold**, *italic*. Link markers: {{story:<entry-id>}} (page on this site),
      {{src:<entry-id>}} (the entry's primary source), {{state:<slug>}} (sibling report).
Image: assets/art/states/<slug>.webp (960x504) and <slug>-thumb.webp (480x252).
"""
import glob
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_site as b  # noqa: E402
from build_medium import blocks, inline, parse  # noqa: E402  (Markdown subset helpers)

SRC_DIR = "content/states"
OUT_DIR = "states"
CAT_LABEL = [("lawsuit", "lawsuit", "lawsuits"), ("regulator", "regulator action", "regulator actions"),
             ("news", "news report", "news reports"), ("tenant", "tenant account", "tenant accounts")]


def load():
    out = []
    for p in sorted(glob.glob(os.path.join(SRC_DIR, "*.md"))):
        meta, body = parse(p)
        out.append((meta, body))
    return out


def expand(text, entries_by_id, slugs):
    def sub(m):
        kind, key = m.group(1), m.group(2)
        if kind == "state":
            if key not in slugs:
                sys.exit("unknown state marker: " + key)
            return "%s/states/%s.html" % (b.SITE, key)
        if key not in entries_by_id:
            sys.exit("unknown entry id in marker: " + key)
        e = entries_by_id[key]
        return e["url"] if kind == "src" else b.story_url(e, True)
    return re.sub(r"\{\{(src|story|state):([^}]+)\}\}", sub, text)


def counts_line(es):
    c = Counter(e["category"] for e in es)
    return " · ".join("%d %s" % (c[k], one if c[k] == 1 else many) for k, one, many in CAT_LABEL if c[k])


def region_entries(entries, region):
    return sorted((e for e in entries if region in b.entry_regions(e.get("location"))),
                  key=lambda e: e["date"], reverse=True)


def build(entries, props):
    """Return ({path: html}, [(abs_url, lastmod)])."""
    docs = load()
    if not docs:
        return {}, []
    if b.HEAD_COMMON is None:  # build_site may be running as __main__, so this is a second module copy
        b.HEAD_COMMON = b.head_common()
    by_id = {e["id"]: e for e in entries}
    slugs = {m["slug"] for m, _ in docs}
    prop_count = Counter(p["s"] for p in props)
    ranked = []
    for meta, _ in docs:
        es = region_entries(entries, meta["region"])
        ranked.append((meta, es))
    ranked.sort(key=lambda t: (-len(t[1]), -sum(1 for e in t[1] if e["category"] != "tenant"), t[0]["name"]))
    pages, urls = {}, []
    latest = max(e["date"] for e in entries)

    for meta, body in docs:
        region, slug, name = meta["region"], meta["slug"], meta["name"]
        es = region_entries(entries, region)
        n = len(es)
        url = "%s/states/%s.html" % (b.SITE, slug)
        art = "%s/assets/art/states/%s.webp" % (b.BASE, slug)
        title = meta.get("title") or "Greystar in %s: Lawsuits, Settlements & Tenant Complaints" % name
        desc = meta["description"]
        sib = [(m, e2) for m, e2 in ranked if m["slug"] != slug][:4]
        sib_html = "".join('<li><a href="%s/states/%s.html">%s</a> <span>%d records</span></li>'
                           % (b.BASE, m["slug"], b.esc(m["name"]), len(e2)) for m, e2 in sib)
        pcount = prop_count.get(region, 0)
        prop_link = ('<p class="note">%s has %d Greystar-managed properties in Greystar\'s public directory. '
                     '<a href="%s/properties/%s.html">See the %s property list</a>. Listing a property does not '
                     'mean a complaint has been made about it.</p>'
                     % (b.esc(name), pcount, b.BASE, b.slugify(name), b.esc(name))) if pcount else ""
        method = ('<p class="note">This report covers the %d records in The Greystar Review whose location is %s. '
                  '<a href="%s/states/">See how the state reports are ranked</a>. Allegations are reported as allegations '
                  'and settlements as resolutions, not admissions.</p>' % (n, b.esc(name), b.BASE))
        main = ('<div class="story state-report">\n%s\n</div>' % blocks(expand(body, by_id, slugs)))
        grid = ('<section class="related"><h2>All %d records from %s</h2><div class="grid">%s</div></section>'
                % (n, b.esc(name), "".join(b.entry_card(e, "h3") for e in es)))
        hero = ('<img class="sec-art" src="%s" alt="%s" width="960" height="504">' % (art, b.esc(meta["img_alt"])))
        page_body = """<header class="sec-head">
  <p class="kicker">State report · {n} sourced records · {cl}</p>
  <h1>{h1}</h1>
  {hero}
  <p class="dek">{dek}</p>
</header>
{main}
{grid}
{prop}
<section class="related"><h2>Other state reports</h2><ul class="regions">{sib}<li><a href="{base}/states/">All state reports</a></li></ul></section>
{method}""".format(n=n, cl=b.esc(counts_line(es)), h1=b.esc(meta["h1"]), hero=hero, dek=b.esc(meta["dek"]),
                   main=main, grid=grid, prop=prop_link, sib=sib_html, base=b.BASE, method=method)
        crumbs_abs = [(b.NAME, b.SITE + "/"), ("State reports", b.SITE + "/states/"), (name, url)]
        ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": title, "url": url,
              "description": desc, "about": b.GREYSTAR, "image": b.SITE + "/assets/art/states/%s.webp" % slug,
              "datePublished": b.TODAY, "dateModified": max([e["date"] for e in es] + [b.TODAY]),
              "isPartOf": {"@type": "WebSite", "name": b.NAME, "url": b.SITE + "/"},
              "mainEntity": {"@type": "ItemList", "numberOfItems": n, "itemListElement": [
                  {"@type": "ListItem", "position": i + 1, "name": e["title"], "url": b.story_url(e, True)}
                  for i, e in enumerate(es)]}}
        og = '<meta property="og:image" content="%s">\n<meta name="twitter:image" content="%s">\n' % (
            b.SITE + "/assets/art/states/%s.webp" % slug, b.SITE + "/assets/art/states/%s.webp" % slug)
        pages[os.path.join(OUT_DIR, slug + ".html")] = b.page(
            "states/%s.html" % slug, title, desc,
            b.shell(page_body, None, [(b.NAME, b.BASE + "/"), ("State reports", b.BASE + "/states/"), (name, None)]),
            [ld, b.breadcrumb_ld(crumbs_abs)], extra_meta=og)
        urls.append((url, b.TODAY))

    # hub
    cards = []
    for i, (meta, es) in enumerate(ranked, 1):
        cards.append('<article class="entry"><p class="kicker">No. %d · %d records</p>'
                     '<h3><a href="%s/states/%s.html">Greystar in %s</a></h3>'
                     '<img src="%s/assets/art/states/%s-thumb.webp" alt="" width="480" height="252" loading="lazy">'
                     '<p>%s</p><div class="byline">%s</div></article>'
                     % (i, len(es), b.BASE, meta["slug"], b.esc(meta["name"]), b.BASE, meta["slug"],
                        b.esc(meta["dek"]), b.esc(counts_line(es))))
    hub_desc = ("Greystar lawsuits, regulator actions, news reports and tenant complaints for the ten places with the "
                "most sourced records in The Greystar Review.")
    hub_body = """<header class="sec-head">
  <p class="kicker">State reports · {n} places</p>
  <h1>Greystar by State: The Most Documented Places</h1>
  <p class="dek">Ranked by the number of sourced records in this archive whose location is that state or district: court cases, regulator actions, news reports and tenant accounts. This is a count of documentation, not a finding about conduct in any place. Where two places tie, the one with more court and agency records ranks higher.</p>
</header>
<div class="grid">{cards}</div>""".format(n=len(ranked), cards="".join(cards))
    hub_url = b.SITE + "/states/"
    pages[os.path.join(OUT_DIR, "index.html")] = b.page(
        "states/", "Greystar by State: Lawsuits, Settlements & Complaints", hub_desc,
        b.shell(hub_body, None, [(b.NAME, b.BASE + "/"), ("State reports", None)]),
        [{"@context": "https://schema.org", "@type": "CollectionPage", "name": "Greystar by State", "url": hub_url,
          "description": hub_desc, "about": b.GREYSTAR,
          "mainEntity": {"@type": "ItemList", "numberOfItems": len(ranked), "itemListElement": [
              {"@type": "ListItem", "position": i + 1, "name": "Greystar in " + m["name"],
               "url": "%s/states/%s.html" % (b.SITE, m["slug"])} for i, (m, _) in enumerate(ranked)]}},
         b.breadcrumb_ld([(b.NAME, b.SITE + "/"), ("State reports", hub_url)])])
    urls.append((hub_url, b.TODAY))
    return pages, urls


def report_href(region_name):
    p = os.path.join(SRC_DIR, b.slugify(region_name) + ".md")
    return "%s/states/%s.html" % (b.BASE, b.slugify(region_name)) if os.path.exists(p) else None


def check(path):
    """Validate ONE content file; returns a list of problems (empty = ok)."""
    bad = []
    meta, body = parse(path)
    for k in ("region", "slug", "name", "h1", "description", "dek", "img_alt"):
        if not meta.get(k):
            bad.append("missing front matter: " + k)
    if bad:
        return bad
    ents = json.load(open("data/entries.json", encoding="utf-8"))
    by_id = {e["id"]: e for e in ents}
    if os.path.basename(path)[:-3] != meta["slug"] or meta["slug"] != b.slugify(meta["name"]):
        bad.append("slug must equal filename and slugify(name): " + b.slugify(meta["name"]))
    if not 110 <= len(meta["description"]) <= 160:
        bad.append("description is %d chars; want 110-160" % len(meta["description"]))
    if len(meta["h1"]) > 80:
        bad.append("h1 too long")
    es = region_entries(ents, meta["region"])
    if not es:
        bad.append("no records for region " + meta["region"])
    try:
        text = expand(body, by_id, {meta["slug"]} | {os.path.basename(p)[:-3] for p in glob.glob(SRC_DIR + "/*.md")})
    except SystemExit as ex:
        return bad + [str(ex)]
    words = len(re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text).split())
    if not 450 <= words <= 1100:
        bad.append("body is %d words; want 450-1100" % words)
    used = set(re.findall(r"\{\{story:([^}]+)\}\}", body))
    if len(used) < max(3, min(len(es), 8)):
        bad.append("link at least %d of the region's records with {{story:id}}; found %d" % (max(3, min(len(es), 8)), len(used)))
    if "## " not in body:
        bad.append("needs ## sections")
    for pat in (r"[^\x00-\x7f\u2018\u2019\u201c\u201d\u00a3\u00e9\u00e8]", ):
        pass
    for f, size in (("assets/art/states/%s.webp" % meta["slug"], (960, 504)), ("assets/art/states/%s-thumb.webp" % meta["slug"], (480, 252))):
        if not os.path.exists(f):
            bad.append("missing image " + f)
        else:
            from PIL import Image
            if Image.open(f).size != size:
                bad.append("%s is %s, want %s" % (f, Image.open(f).size, size))
            if os.path.getsize(f) > 150 * 1024:
                bad.append(f + " over 150KB")
    return bad


if __name__ == "__main__" and len(sys.argv) > 2 and sys.argv[1] == "--check":
    problems = check(sys.argv[2])
    print("OK" if not problems else "\n".join("FAIL: " + x for x in problems))
    sys.exit(1 if problems else 0)

if __name__ == "__main__":
    b.HEAD_COMMON = b.head_common()
    ents = json.load(open("data/entries.json", encoding="utf-8"))
    props = json.load(open("data/properties.json", encoding="utf-8"))
    pgs, _ = build(ents, props)
    for path, html in pgs.items():
        b.write(path, html)
        print("wrote", path)
