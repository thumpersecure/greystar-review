#!/usr/bin/env python3
"""Build the Medium-importable follow-up articles for The Greystar Review.

Run from the repo root:   python3 scripts/build_medium.py

Reads  medium/src/*.md   (front matter + a small Markdown subset)
       data/entries.json (for {{src:id}} / {{story:id}} link markers)
Writes medium/<slug>.html and medium/index.html, then lints every page against
Medium's editor rules (help.medium.com: Using the story editor / images /
embeds / import tool). Exits non-zero if any page fails the lint.

Markers in article text:
  {{src:<entry-id>}}      -> the entry's primary source URL
  {{story:<entry-id>}}    -> that entry's page on this site
  {{article:<slug>}}      -> another article in this series

Front matter keys: title, dek, slug, alt, caption, description, record
(record = comma-separated entry ids -> generated "Read the record" list).
"""
import glob
import html
import json
import os
import re
import sys

SITE = "https://thumpersecure.github.io/greystar-review"
NAME = "The Greystar Review"
PUBLISHED = "2026-10-02"
CORRECTIONS = "https://github.com/thumpersecure/greystar-review/issues/new?labels=correction"
IMG_CAPTION = "Illustration generated with ElevenLabs. It depicts no real people, properties or documents."

# Tags Medium's editor can represent. Anything else in <article> fails the lint.
ARTICLE_TAGS = {"article", "h1", "h2", "h3", "p", "a", "ul", "ol", "li", "blockquote",
                "figure", "img", "figcaption", "strong", "em", "time"}


def esc(s):
    return html.escape(s, quote=True)


def load_entries():
    with open("data/entries.json", encoding="utf-8") as f:
        return {e["id"]: e for e in json.load(f)}


def parse(path):
    raw = open(path, encoding="utf-8").read()
    head, _, body = raw.partition("\n---\n")
    meta = {}
    for line in head.strip().splitlines():
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip()
    return meta, body.strip() + "\n"


def expand(text, entries, slugs):
    def sub(m):
        kind, key = m.group(1), m.group(2)
        if kind == "article":
            if key not in slugs:
                sys.exit("unknown article marker: " + key)
            return "%s/medium/%s.html" % (SITE, key)
        if key not in entries:
            sys.exit("unknown entry id in marker: " + key)
        return entries[key]["url"] if kind == "src" else "%s/stories/%s.html" % (SITE, key)
    return re.sub(r"\{\{(src|story|article):([^}]+)\}\}", sub, text)


def inline(s):
    s = esc(s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", lambda m: '<a href="%s">%s</a>' % (m.group(2), m.group(1)), s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*([^*]+)\*(?![\w*])", r"<em>\1</em>", s)
    return s


def blocks(body):
    out, para, items, kind = [], [], [], None

    def flush():
        nonlocal para, items, kind
        if para:
            out.append("<p>%s</p>" % inline(" ".join(para)))
        if items:
            tag = "ol" if kind == "ol" else "ul"
            out.append("<%s>\n%s\n</%s>" % (tag, "\n".join("<li>%s</li>" % inline(i) for i in items), tag))
        para, items, kind = [], [], None

    for line in body.splitlines():
        if not line.strip():
            flush()
        elif line.startswith("## "):
            flush()
            out.append("<h2>%s</h2>" % inline(line[3:].strip()))
        elif line.startswith("> "):
            flush()
            out.append("<blockquote><p>%s</p></blockquote>" % inline(line[2:].strip()))
        elif re.match(r"- ", line):
            if kind != "ul":
                flush()
            kind = "ul"
            items.append(line[2:].strip())
        elif re.match(r"\d+\. ", line):
            if kind != "ol":
                flush()
            kind = "ol"
            items.append(re.sub(r"^\d+\.\s+", "", line))
        else:
            if items:
                flush()
            para.append(line.strip())
    flush()
    return "\n".join(out)


def record_list(ids, entries):
    lis = []
    for i in ids:
        e = entries[i]
        # Court/agency names are long; only press and tenant entries get an outlet suffix.
        outlet = " (%s)" % esc(e["outlet"]) if e["category"] in ("news", "tenant") else ""
        lis.append('<li><a href="%s/stories/%s.html">%s</a>%s</li>' % (SITE, i, esc(e["title"]), outlet))
    return "<h2>Read the record</h2>\n<p>Each item below is on The Greystar Review with a link to its original source.</p>\n<ul>\n%s\n</ul>" % "\n".join(lis)


CSS = """:root{--bg:#fbf8f2;--fg:#1c1a17;--mute:#6b645a;--rule:#ddd5c6;--acc:#a3201a}
@media (prefers-color-scheme:dark){:root{--bg:#141210;--fg:#ece6da;--mute:#9d9486;--rule:#3a352d;--acc:#e0645c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:19px/1.7 Georgia,'Source Serif 4',serif}
header.site,footer.site{max-width:720px;margin:0 auto;padding:18px 16px;font:600 14px/1.4 system-ui,sans-serif;color:var(--mute)}
header.site a,footer.site a{color:var(--mute)}
main{max-width:720px;margin:0 auto;padding:0 16px 40px}
h1{font:900 clamp(30px,6vw,46px)/1.1 Georgia,serif;margin:.3em 0 .3em}
h3{font:italic 400 clamp(19px,3.4vw,23px)/1.45 Georgia,serif;color:var(--mute);margin:0 0 1.2em}
h2{font:800 clamp(22px,4vw,28px)/1.25 system-ui,sans-serif;margin:1.8em 0 .5em}
a{color:var(--acc)}blockquote{margin:1.4em 0;padding:0 0 0 1em;border-left:3px solid var(--acc);color:var(--mute)}
figure{margin:0 0 1.6em}img{display:block;width:100%;height:auto}figcaption{font:14px/1.4 system-ui,sans-serif;color:var(--mute);margin-top:6px}
.meta{font:14px/1.4 system-ui,sans-serif;color:var(--mute);margin:0 0 1.2em}
li{margin:.3em 0}"""


def page(meta, body_html, url, img_url):
    t, d = esc(meta["title"]), esc(meta["description"])
    ld = json.dumps({
        "@context": "https://schema.org", "@type": "Article", "headline": meta["title"],
        "description": meta["description"], "url": url, "mainEntityOfPage": url,
        "datePublished": PUBLISHED, "image": img_url, "inLanguage": "en",
        "author": {"@type": "Organization", "name": NAME, "url": SITE + "/"},
        "publisher": {"@type": "Organization", "name": NAME, "url": SITE + "/"}}, indent=1)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{t} | {NAME}</title>
<meta name="description" content="{d}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="{NAME}">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{img_url}">
<meta property="og:image:width" content="1280">
<meta property="og:image:height" content="720">
<meta name="twitter:card" content="summary_large_image">
<meta property="article:published_time" content="{PUBLISHED}">
<link rel="icon" href="/greystar-review/assets/favicon-32.png" sizes="32x32" type="image/png">
<style>{CSS}</style>
<script type="application/ld+json">
{ld}
</script>
</head>
<body>
<header class="site"><a href="{SITE}/">{NAME}</a> &middot; Follow-up</header>
<main>
<article>
{body_html}
</article>
</main>
<footer class="site">Part of <a href="{SITE}/">{NAME}</a>. <a href="{CORRECTIONS}">Report a correction</a>.</footer>
</body>
</html>
"""


def build_article(path, entries, slugs):
    meta, body = parse(path)
    slug = meta["slug"]
    url = "%s/medium/%s.html" % (SITE, slug)
    img_rel = "medium/img/%s.jpg" % slug
    img_url = "%s/%s" % (SITE, img_rel)
    body = expand(body, entries, slugs)
    ids = [i.strip() for i in meta["record"].split(",") if i.strip()]
    for i in ids:
        if i not in entries:
            sys.exit("%s: unknown record id %s" % (slug, i))
    closing = ("<p>This article summarizes public records and published reporting collected by %s. "
               "Allegations are described as allegations, and a settlement is not a finding of wrongdoing unless a court or agency says so. "
               "If something here is wrong, <a href=\"%s\">tell us</a> and we will fix it.</p>" % (NAME, CORRECTIONS))
    parts = [
        "<h1>%s</h1>" % esc(meta["title"]),
        "<h3>%s</h3>" % esc(meta["dek"]),
        '<figure><img src="%s" alt="%s" width="1280" height="720"><figcaption>%s</figcaption></figure>'
        % (img_url, esc(meta["alt"]), esc(meta.get("caption") or IMG_CAPTION)),
        blocks(body),
        record_list(ids, entries),
        closing,
    ]
    return slug, meta, page(meta, "\n".join(parts), url, img_url), url


def lint(slug, doc):
    """Medium editor/import rules. Returns a list of problems."""
    bad = []
    m = re.search(r"<article>(.*)</article>", doc, re.S)
    art = m.group(1)
    for tag in set(re.findall(r"<\s*([a-z0-9]+)", art)):
        if tag not in ARTICLE_TAGS:
            bad.append("unsupported tag <%s> in article" % tag)
    if len(re.findall(r"<h1>", doc)) != 1:
        bad.append("need exactly one <h1> (Medium title)")
    if not re.match(r"\s*<h1>.*?</h1>\s*<h3>", art, re.S):
        bad.append("<h3> subtitle must directly follow <h1>")
    if re.search(r"<h[456]", art):
        bad.append("heading deeper than Medium's two levels")
    if re.search(r"<(ul|ol)>(?:(?!</\1>).)*<(ul|ol)>", art, re.S):
        bad.append("nested list (Medium lists are flat)")
    if re.search(r"<figcaption>.*?<(em|i)>", art, re.S):
        bad.append("italic in image caption (unsupported by Medium)")
    if re.search(r"<h2>\s*</h2>|<li>\s*</li>|<p>\s*</p>", art):
        bad.append("empty element")
    if re.search(r"\.(webp|svg)\b", art):
        bad.append("image format Medium rejects (webp/svg)")
    for src in re.findall(r'<img src="([^"]+)"', art):
        local = src.replace(SITE + "/", "")
        if not local.lower().endswith((".jpg", ".jpeg", ".png", ".gif")):
            bad.append("image not jpg/png/gif: " + src)
        elif not os.path.exists(local):
            bad.append("image file missing: " + local)
        else:
            try:
                from PIL import Image
                w, h = Image.open(local).size
                if w < 1192:
                    bad.append("image %dpx wide; Medium needs >=1192 for all placements" % w)
                if os.path.getsize(local) > 25 * 1024 * 1024:
                    bad.append("image over Medium's 25MB limit")
            except ImportError:
                pass
    for href in re.findall(r'<a href="([^"]+)"', art):
        if not href.startswith("https://"):
            bad.append("non-https link: " + href)
    if "{{" in art or "}}" in art:
        bad.append("unexpanded marker")
    if not re.search(r"<link rel=\"canonical\" href=\"https://", doc):
        bad.append("missing canonical")
    words = len(re.sub(r"<[^>]+>", " ", art).split())
    return bad, words


def build_index(rows):
    lis = []
    for slug, meta, url in rows:
        lis.append('<li><strong>%s</strong><br>%s<br><code>%s</code></li>' % (esc(meta["title"]), esc(meta["dek"]), esc(url)))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>Medium follow-ups | {NAME}</title>
<style>{CSS}code{{font-size:14px;word-break:break-all}}</style>
</head>
<body>
<header class="site"><a href="{SITE}/">{NAME}</a></header>
<main>
<h1>Medium follow-ups</h1>
<p class="meta">Ten articles for import. On Medium: profile menu &rarr; Stories &rarr; Import a story &rarr; paste the URL &rarr; Import &rarr; See your story &rarr; Publish.</p>
<ol>
{chr(10).join(lis)}
</ol>
</main>
</body>
</html>
"""


def main():
    if not os.path.exists("data/entries.json"):
        sys.exit("run from the repo root")
    entries = load_entries()
    paths = sorted(glob.glob("medium/src/*.md"))
    slugs = {parse(p)[0]["slug"] for p in paths}
    failed, rows = False, []
    order = [parse(p)[0]["slug"] for p in paths]
    for p in paths:
        slug, meta, doc, url = build_article(p, entries, slugs)
        problems, words = lint(slug, doc)
        with open("medium/%s.html" % slug, "w", encoding="utf-8") as f:
            f.write(doc)
        print("%-40s %4d words  %s" % (slug, words, "OK" if not problems else "FAIL"))
        for pr in problems:
            print("    - " + pr)
            failed = True
        rows.append((slug, meta, url))
    with open("medium/index.html", "w", encoding="utf-8") as f:
        f.write(build_index(rows))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
