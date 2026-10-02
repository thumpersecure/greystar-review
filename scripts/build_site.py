#!/usr/bin/env python3
"""Static page builder for The Greystar Review (GitHub Pages).

Run from the repo root:   python3 scripts/build_site.py

Reads data/entries.json + data/properties.json and (re)generates:
  stories/<id>.html, <section>/index.html, properties/index.html,
  properties/<state>.html, about.html, sitemap.xml
and refreshes the crawlable fallback between <!--STATIC:START--> and
<!--STATIC:END--> inside <main id="ledger"> in index.html (nothing else in
index.html is touched). Idempotent; stdlib only.

Head tags: if assets/head-common.html exists, its contents are included in
every generated page between <!--HEAD_COMMON:START/END--> (relative URLs in it
are rewritten to /greystar-review/...). Otherwise a minimal fallback is used.
Section intros (between <!--INTRO:START--> and <!--INTRO:END-->): if
content/intros/<slug>.html exists it is used; otherwise a hand-edited block in
the existing page is preserved on rebuild as long as it no longer carries the
data-default attribute; otherwise the default copy (from SEO-PLAN.md) is used.
"""
import datetime
import html
import json
import os
import re
import sys
from collections import OrderedDict, defaultdict

SITE = "https://thumpersecure.github.io/greystar-review"
BASE = "/greystar-review"
NAME = "The Greystar Review"
OG_IMAGE = SITE + "/assets/og.png"
ISSUES = "https://github.com/thumpersecure/greystar-review/issues/new?labels=correction"
FONTS = ("https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;"
         "1,400;1,700;1,900&family=Libre+Franklin:wght@400;600;800&family=Source+Serif+4:ital,"
         "wght@0,400;0,600;1,400&display=swap")
TODAY = datetime.date.today().isoformat()

# slug, label, H1, <title>, default intro, predicate, meta description  (copy from SEO-PLAN.md)
SECTIONS = [
    ("court-docket", "Court Docket", "Greystar Lawsuits and Class Actions",
     "Greystar Lawsuits & Class Actions | Court Docket",
     "This docket lists civil lawsuits and class actions that name Greystar or its affiliates, with "
     "court, case number where available, and current status. Filed complaints contain allegations "
     "that have not been proven; where a case settled, we note whether Greystar admitted wrongdoing. "
     "Each entry links to the court record or the reporting it is based on.",
     lambda e: e["category"] == "lawsuit",
     "Every Greystar lawsuit and class action we track: RealPage price-fixing, junk fees, eviction "
     "fees, crane collapse. Case status and court records."),
    ("regulators", "Regulators", "Greystar and the Regulators: FTC, DOJ and State Actions",
     "Greystar FTC, DOJ & State AG Actions | Regulators",
     "This section records actions involving Greystar by government agencies \u2014 including the Federal "
     "Trade Commission, the Department of Justice, state attorneys general and civil rights agencies "
     "\u2014 along with complaints filed with those agencies by watchdog groups. Status labels distinguish "
     "filed complaints, pending cases, consent decrees and settlements. Unless a settlement says "
     "otherwise, Greystar has not admitted wrongdoing.",
     lambda e: e["category"] == "regulator",
     "Greystar's FTC $24M settlement, DOJ RealPage consent decree, state attorney general suits and "
     "fair housing complaints, each linked to the source."),
    ("reporting", "Reporting", "Reporting on Greystar",
     "Greystar News & Investigations | Reporting",
     "A dated index of news reporting and investigations about Greystar from national and local "
     "outlets. Each entry summarizes what the outlet reported and links to the original article. "
     "Descriptions reflect the publication's reporting, not independent findings by this site.",
     lambda e: e["category"] == "news",
     "News reporting on Greystar from ProPublica, The Guardian, HousingWire and local outlets: "
     "RealPage, junk fees, vouchers and building conditions."),
    ("letters", "Letters from Tenants", "Letters from Tenants: Greystar Complaints",
     "Greystar Tenant Complaints | Letters from Tenants",
     "These are publicly posted accounts from people who say they rented at Greystar-managed "
     "properties, drawn from review and complaint sites and petitions. They are first-person "
     "allegations, have not been verified by this site, and are summarized with a link to the "
     "original post. Greystar may not have responded to individual complaints.",
     lambda e: e["category"] == "tenant",
     "Tenant complaints about Greystar-managed apartments: deposits, move-out charges, repairs, pests "
     "and fees. Published accounts, presented as allegations."),
    ("the-chairman", "The Chairman", "The Chairman: Bob Faith",
     "Bob Faith, Greystar Founder & CEO | The Chairman",
     "Bob Faith is the founder and chief executive of Greystar. This page collects public records and "
     "reporting that name him, including a 2020 appointment to a White House economic advisory group "
     "and court filings in which he was named. Inclusion here does not imply any personal wrongdoing; "
     "each entry states its source and outcome.",
     lambda e: "bob-faith" in (e.get("subject") or []),
     "Bob Faith founded and leads Greystar. Court records, public appointments and reporting that "
     "name him, with sources and dates."),
]
# Hand-tuned <title> overrides (SEO-PLAN.md section 2). An entry's own "seo_title" field wins.
SEO_TITLES = {
    "ftc-colorado-greystar-24m-settlement-2025": "Greystar $24M FTC Settlement Over Hidden Rental Fees (2025)",
    "realpage-mdl-greystar-50m-class-settlement-2025": "Greystar $50M RealPage Class Action Settlement",
    "nine-state-ag-greystar-7m-settlement-2025": "Greystar $7M Settlement With 9 State Attorneys General",
    "doj-greystar-realpage-consent-decree-2025": "DOJ Settlement Ends Greystar's RealPage Pricing Use",
    "doj-scra-greystar-servicemember-fees-2025": "Greystar Pays $1.43M Over Servicemember Lease Fees",
    "hri-multistate-voucher-discrimination-complaints-2026": "114 Section 8 Voucher Complaints Filed Against Greystar",
    "arizona-ag-greystar-junk-fee-settlements-2026": "Arizona AG Greystar Junk Fee Settlements (2026)",
    "dallas-crane-collapse-860m-verdict-2023": "$860M Verdict Against Greystar in Dallas Crane Collapse",
    "wallace-v-greystar-nc-eviction-fees-settlement": "Greystar $4.665M NC Eviction Fee Class Settlement",
    "ftc-colorado-v-greystar-complaint-2025": "FTC and Colorado Sue Greystar Over Hidden Fees (2025)",
}
MIN_STATE_PROPS = 5  # regions with fewer properties and no story get no page of their own
CAT_SECTION = {"lawsuit": "court-docket", "regulator": "regulators", "news": "reporting",
               "tenant": "letters"}
SEC_BY_SLUG = {s[0]: s for s in SECTIONS}

STATES = OrderedDict([
    ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"), ("CA", "California"),
    ("CO", "Colorado"), ("CT", "Connecticut"), ("DE", "Delaware"), ("DC", "District of Columbia"),
    ("FL", "Florida"), ("GA", "Georgia"), ("HI", "Hawaii"), ("ID", "Idaho"), ("IL", "Illinois"),
    ("IN", "Indiana"), ("IA", "Iowa"), ("KS", "Kansas"), ("KY", "Kentucky"), ("LA", "Louisiana"),
    ("ME", "Maine"), ("MD", "Maryland"), ("MA", "Massachusetts"), ("MI", "Michigan"),
    ("MN", "Minnesota"), ("MS", "Mississippi"), ("MO", "Missouri"), ("MT", "Montana"),
    ("NE", "Nebraska"), ("NV", "Nevada"), ("NH", "New Hampshire"), ("NJ", "New Jersey"),
    ("NM", "New Mexico"), ("NY", "New York"), ("NC", "North Carolina"), ("ND", "North Dakota"),
    ("OH", "Ohio"), ("OK", "Oklahoma"), ("OR", "Oregon"), ("PA", "Pennsylvania"),
    ("RI", "Rhode Island"), ("SC", "South Carolina"), ("SD", "South Dakota"), ("TN", "Tennessee"),
    ("TX", "Texas"), ("UT", "Utah"), ("VT", "Vermont"), ("VA", "Virginia"), ("WA", "Washington"),
    ("WV", "West Virginia"), ("WI", "Wisconsin"), ("WY", "Wyoming")])
NAME_TO_CODE = {v.lower(): k for k, v in STATES.items()}
REGION_ALIASES = {"uk": "United Kingdom", "united kingdom": "United Kingdom"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

GREYSTAR = {"@type": "Organization", "name": "Greystar Real Estate Partners",
            "alternateName": "Greystar", "url": "https://www.greystar.com/"}
BOB_FAITH = {"@type": "Person", "name": "Bob Faith",
             "jobTitle": "Founder, Chairman and CEO", "worksFor": {"@type": "Organization",
                                                                   "name": "Greystar Real Estate Partners"}}
PUBLISHER = {"@type": "Organization", "name": NAME, "url": SITE + "/"}


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def fmt_date(d):
    p = (d or "").split("-")
    try:
        if len(p) == 3:
            return "%s %d, %s" % (MONTHS[int(p[1]) - 1], int(p[2]), p[0])
        if len(p) == 2:
            return "%s %s" % (MONTHS[int(p[1]) - 1], p[0])
    except (ValueError, IndexError):
        pass
    return p[0] or "Undated"


def clip(s, n=155):
    s = re.sub(r"\s+", " ", s or "").strip()
    if len(s) <= n:
        return s
    cut = s[:n - 1].rsplit(" ", 1)[0].rstrip(",;:.-—")
    return cut + "…"


AP_MONTHS = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "Jun.", "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec."]


def ap_date(d):
    p = (d or "").split("-")
    try:
        if len(p) == 3:
            return "%s %d, %s" % (AP_MONTHS[int(p[1]) - 1], int(p[2]), p[0])
        if len(p) == 2:
            return "%s %s" % (AP_MONTHS[int(p[1]) - 1], p[0])
    except (ValueError, IndexError):
        pass
    return p[0]


def clip_sentence(s, n=155):
    """SEO-PLAN: cut at last sentence end <= n; else last word boundary <= n-3 + ellipsis."""
    s = re.sub(r"\s+", " ", s or "").strip()
    if len(s) <= n:
        return s
    head = s[:n]
    m = max(head.rfind(". "), head.rfind("? "), head.rfind("! "))
    if head.endswith((".", "?", "!")):
        m = len(head) - 1
    if m > 60:
        return head[:m + 1]
    return s[:n - 3].rsplit(" ", 1)[0].rstrip(",;:.-—") + "…"


def story_title(e):
    """Story <title>: override, else title (<=60) with the publication name appended when it fits."""
    t = e.get("seo_title") or SEO_TITLES.get(e["id"])
    if t:
        return t
    t = e["title"].strip()
    if len(t) > 60:
        t = t[:57].rsplit(" ", 1)[0].rstrip(",;:.-—") + "…"
    elif "greystar" not in t.lower() and len(t) + 18 <= 60:
        t = t + " — Greystar Review"
    return t


def story_desc(e):
    loc = e.get("location") or ""
    lead = " · ".join(x for x in [ap_date(e["date"]), loc] if x)
    summ = e["summary"].strip()
    if e["category"] == "tenant" and "alleg" not in summ[:80].lower():
        summ = "Tenant alleges: " + summ
    return clip_sentence(("%s. %s" % (lead, summ)) if lead else summ)


def norm_city(c):
    """'Nashville (Bellevue)' -> {'nashville', 'bellevue'}."""
    c = (c or "").lower()
    out = {re.sub(r"\([^)]*\)", "", c).strip()}
    out |= {x.strip() for x in re.findall(r"\(([^)]*)\)", c)}
    return {x for x in out if x}


def entry_city(e):
    toks = [t.strip() for t in (e.get("location") or "").split(",")]
    if len(toks) >= 2 and entry_regions(e.get("location")) and toks[0] not in STATES:
        return norm_city(toks[0])
    return set()


def matches_property(e, p):
    """Name AND city must match (case-insensitive), and region when the entry has one."""
    if p["n"].strip().lower() not in prop_names(e.get("property")):
        return False
    if not (entry_city(e) & norm_city(p["c"])):
        return False
    regs = entry_regions(e.get("location"))
    return not regs or p["s"] in regs


def jsonld(obj):
    txt = json.dumps(obj, ensure_ascii=False, indent=1)
    txt = txt.replace("</", "<\\/")
    return '<script type="application/ld+json">\n%s\n</script>' % txt


def region_name(s):
    return STATES.get(s, s)


def entry_regions(loc):
    """Regions (properties.json 's' values) an entry location refers to."""
    loc = (loc or "").strip()
    if not loc:
        return set()
    toks = [t.strip() for t in loc.split(",")]
    codes = {t for t in toks if t in STATES}
    if codes:
        return codes
    low = loc.lower()
    if low in NAME_TO_CODE:
        return {NAME_TO_CODE[low]}
    for t in toks:
        if t.lower() in REGION_ALIASES:
            return {REGION_ALIASES[t.lower()]}
    return set()


def prop_names(p):
    out = set()
    for part in (p or "").split(";"):
        part = re.sub(r"\([^)]*\)", "", part).strip().lower()
        if part:
            out.add(part)
    return out


# ---------------------------------------------------------------- head/shell
def head_common():
    path = os.path.join("assets", "head-common.html")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            snip = f.read().strip()

        def fix(m):
            attr, q, url = m.group(1), m.group(2), m.group(3)
            if re.match(r"^(?:[a-z][a-z0-9+.-]*:|/|#)", url, re.I):
                return m.group(0)
            return "%s=%s%s/%s%s" % (attr, q, BASE, url.lstrip("./"), q)
        snip = re.sub(r'\b(href|src)=(["\'])([^"\']*)\2', fix, snip)
        # drop tags that every page sets itself (avoid duplicates)
        snip = re.sub(r'<link[^>]+rel=["\']canonical["\'][^>]*>\s*', "", snip, flags=re.I)
        snip = re.sub(r'<meta[^>]+(?:property|name)=["\'](?:og:(?:title|description|url|type)|'
                      r'twitter:(?:title|description)|description)["\'][^>]*>\s*', "", snip, flags=re.I)
    else:
        snip = ('<link rel="icon" href="%s/assets/favicon.svg" type="image/svg+xml">\n'
                '<meta name="theme-color" content="#f6f2ea">' % BASE)
    return "<!--HEAD_COMMON:START-->\n%s\n<!--HEAD_COMMON:END-->" % snip


HEAD_COMMON = None


def page(path, title, desc, body, ld=(), og_type="website", extra_meta=""):
    """path is site-relative, e.g. 'stories/x.html' or 'court-docket/'."""
    canon = "%s/%s" % (SITE, path)
    fonts = "" if "fonts.googleapis.com/css2" in HEAD_COMMON else (
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link href="%s" rel="stylesheet">\n' % esc(FONTS))
    hc = HEAD_COMMON

    def tag(t):
        """Emit a default tag unless head-common.html already provides the same key."""
        m = re.search(r'(?:property|name)="([^"]+)"', t) if t.startswith("<meta") else \
            re.search(r'href="([^"]+)"', t)
        key = m.group(1) if m else t
        if t.startswith("<meta") and re.search(r'(?:property|name)=["\']%s["\']' % re.escape(key), hc):
            return ""
        if t.startswith("<link") and key in hc:
            return ""
        return t + "\n"
    defaults = "".join(tag(t) for t in [
        '<meta property="og:site_name" content="%s">' % esc(NAME),
        '<meta property="og:image" content="%s">' % esc(OG_IMAGE),
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        '<meta name="twitter:card" content="summary_large_image">',
        '<meta name="twitter:image" content="%s">' % esc(OG_IMAGE),
        '<link rel="stylesheet" href="%s/assets/style.css">' % BASE,
    ])
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{canon}">
<meta name="robots" content="max-image-preview:large">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{canon}">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
{extra}{hc}
{fonts}{defaults}<link rel="stylesheet" href="{base}/assets/pages.css">
{ld}
</head>
<body class="sub">
{body}
</body>
</html>
""".format(title=esc(title), desc=esc(desc), canon=esc(canon), og_type=og_type,
           extra=extra_meta, hc=hc, fonts=fonts, defaults=defaults, base=BASE,
           ld="\n".join(jsonld(x) for x in ld), body=body)


def nav_links(current=None):
    items = [("%s/" % BASE, "The Record", None)]
    items += [("%s/%s/" % (BASE, s[0]), s[1], s[0]) for s in SECTIONS]
    items += [("%s/properties/" % BASE, "Properties", "properties")]
    return "".join('<a href="%s"%s>%s</a>' % (h, ' class="on" aria-current="page"' if k and k == current else "",
                                              esc(l)) for h, l, k in items)


def shell(body, current=None, crumbs=()):
    crumb_html = ""
    if crumbs:
        parts = []
        for i, (label, href) in enumerate(crumbs):
            if href and i < len(crumbs) - 1:
                parts.append('<a href="%s">%s</a>' % (esc(href), esc(label)))
            else:
                parts.append('<span aria-current="page">%s</span>' % esc(label))
        crumb_html = '<nav class="crumbs" aria-label="Breadcrumb">%s</nav>' % ' <span class="sep">›</span> '.join(parts)
    return """<div class="topbar"><span>Vol. I</span><span class="hide-sm">Independent · Every story sourced</span><a href="{base}/about.html">About &amp; standards</a></div>
<header class="nameplate small">
  <p class="plate"><a href="{base}/"><span class="the">The</span> Greystar Review</a></p>
  <div class="rules"></div>
  <nav class="depts" aria-label="Sections">{nav}</nav>
</header>
<div class="wrap">
{crumbs}
{body}
</div>
{foot}""".format(base=BASE, nav=nav_links(current), crumbs=crumb_html, body=body, foot=footer())


def footer():
    return """<footer class="foot">
  <div class="colophon">
    <p class="mini-plate"><a href="{base}/"><span class="the">The</span> Greystar Review</a></p>
    <p><strong>Editorial standard.</strong> Stories are drawn from court records, agency releases, published journalism and public tenant review sites. Allegations are reported as allegations, settlements as resolutions rather than admissions, and outcomes are stated where known. <a href="{base}/about.html">Read the standards</a>.</p>
    <p><strong>Corrections.</strong> Something wrong? <a href="{issues}&amp;title=Correction:%20" rel="noopener">File a correction</a>. Open data: <a href="{base}/data/entries.json">entries.json</a> · <a href="{base}/data/properties.json">properties.json</a>.</p>
    <p class="footnav">{nav}</p>
  </div>
</footer>""".format(base=BASE, issues=esc(ISSUES), nav=nav_links())


def breadcrumb_ld(crumbs):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": label,
                                 "item": url} for i, (label, url) in enumerate(crumbs)]}


# ---------------------------------------------------------------- pieces
def story_url(e, absolute=False):
    rel = "stories/%s.html" % e["id"]
    return ("%s/%s" % (SITE, rel)) if absolute else ("%s/%s" % (BASE, rel))


def src_rel(e):
    # Primary-source citations (courts, agencies, journalism) stay followable:
    # they are the evidence the page summarizes. Tenant review sites (user-generated
    # content on third-party platforms) and archive.org snapshots get nofollow.
    return "noopener nofollow" if e["category"] == "tenant" else "noopener"


def kicker(e):
    k = SEC_BY_SLUG[CAT_SECTION.get(e["category"], "reporting")][1]
    if "bob-faith" in (e.get("subject") or []):
        k += " · The Chairman"
    return k


def byline(e):
    return " · ".join(x for x in [fmt_date(e["date"]), e.get("outlet"), e.get("property"),
                                  e.get("location")] if x)


def entry_card(e, h="h2", show_kicker=True):
    return """<article class="entry {cat}">
  {kick}<{h}><a href="{href}">{title}</a></{h}>
  <p>{summary}</p>
  {status}<div class="byline">{byline}</div>
</article>""".format(cat=esc(e["category"]), h=h, href=esc(story_url(e)), title=esc(e["title"]),
                     summary=esc(e["summary"]),
                     kick='<p class="kicker">%s</p>\n  ' % esc(kicker(e)) if show_kicker else "",
                     status='<div class="status">%s</div>\n  ' % esc(e["status"]) if e.get("status") else "",
                     byline=esc(byline(e)))


def related(e, entries):
    out, seen = [], {e["id"]}
    pn = prop_names(e.get("property"))
    loc = e.get("location")

    def add(pred):
        for x in sorted(entries, key=lambda x: x["date"], reverse=True):
            if len(out) >= 6:
                return
            if x["id"] not in seen and pred(x):
                seen.add(x["id"])
                out.append(x)
    if pn:
        add(lambda x: pn & prop_names(x.get("property")))
    if loc and loc != "Nationwide":
        add(lambda x: x.get("location") == loc)
    add(lambda x: x["category"] == e["category"])
    return out


# ---------------------------------------------------------------- builders
STATE_PAGES = set()  # region keys that get their own page (filled in main)


def state_page_href(region):
    return "%s/properties/%s.html" % (BASE, slugify(region_name(region))) if region in STATE_PAGES else None


def build_story(e, entries, prop_index):
    sec = SEC_BY_SLUG[CAT_SECTION.get(e["category"], "reporting")]
    sec_url = "%s/%s/" % (SITE, sec[0])
    surl = story_url(e, True)
    crumbs_abs = [(NAME, SITE + "/"), (sec[1], sec_url), (e["title"], surl)]
    crumbs = [(NAME, BASE + "/"), (sec[1], "%s/%s/" % (BASE, sec[0])), (e["title"], None)]
    desc = story_desc(e)
    about = [GREYSTAR] + ([BOB_FAITH] if "bob-faith" in (e.get("subject") or []) else [])
    cites = [e["url"]] + ([e["archive_url"]] if e.get("archive_url") else [])
    art = {"@context": "https://schema.org", "@type": "Article",
           "headline": e["title"][:110], "description": desc, "url": surl,
           "mainEntityOfPage": surl, "datePublished": e["date"], "image": OG_IMAGE,
           "articleSection": sec[1], "genre": "Summary of public record",
           "isBasedOn": e["url"], "citation": cites,
           "about": about if len(about) > 1 else about[0],
           "author": PUBLISHER, "publisher": PUBLISHER, "inLanguage": "en"}
    if e.get("location") and e["location"] != "Nationwide":
        art["contentLocation"] = {"@type": "Place", "name": e["location"]}
    if e.get("outlet"):
        art["sourceOrganization"] = {"@type": "Organization", "name": e["outlet"]}

    # property listings on greystar.com that match this story (name AND city)
    listings = [p for n in prop_names(e.get("property")) for p in prop_index.get(n, [])
                if matches_property(e, p)]
    listing_html = ""
    if listings:
        def plink(p):
            sp = state_page_href(p["s"])
            name = ('<a href="%s#p-%s">%s</a>' % (sp, esc(p["id"]), esc(p["n"]))) if sp else esc(p["n"])
            return '%s, %s (<a href="https://www.greystar.com/%s/p_%s" rel="noopener nofollow">Greystar listing</a>)' % (
                name, esc(p["c"]), esc(p["slug"]), esc(p["id"]))
        listing_html = '<p class="meta-row"><b>Property</b> %s</p>' % " · ".join(plink(p) for p in listings)
    state_links = [(region_name(r), state_page_href(r)) for r in region_order(entry_regions(e.get("location")))
                   if state_page_href(r)]
    if state_links:
        listing_html += '<p class="meta-row"><b>Where</b> %s</p>' % " · ".join(
            '<a href="%s">More Greystar records and properties in %s →</a>' % (h, esc(n)) for n, h in state_links)

    rel = related(e, entries)
    rel_html = ""
    if rel:
        rel_html = '<section class="related" aria-labelledby="rel-h"><h2 id="rel-h">Related on the record</h2><div class="grid">%s</div></section>' % "".join(
            entry_card(x, "h3") for x in rel)
    sec_links = ['<a href="%s/%s/">%s</a>' % (BASE, sec[0], esc(sec[1]))]
    if "bob-faith" in (e.get("subject") or []) and sec[0] != "the-chairman":
        sec_links.append('<a href="%s/the-chairman/">The Chairman</a>' % BASE)
    archive = ('<a href="%s" rel="noopener nofollow">Archived copy</a>' % esc(e["archive_url"])
               if e.get("archive_url") else "")
    body = """<article class="story">
  <p class="kicker">{kick}</p>
  <h1>{title}</h1>
  <p class="dek">{summary}</p>
  {status}<p class="byline">{byline}</p>
  <div class="sources">
    <a class="btn" href="{url}" rel="{srel}">Read the source{outlet}</a>
    {archive}
  </div>
  {listing}
  <p class="meta-row"><b>Filed under</b> {secs}</p>
  <p class="note">This page summarizes {what}; it is not original reporting. Read the source for full context. Allegations are allegations unless a court or agency has found otherwise. See an error? <a href="{issues}&amp;title={ctitle}" rel="noopener">File a correction</a>.</p>
</article>
{related}""".format(kick=esc(kicker(e)), title=esc(e["title"]), summary=esc(e["summary"]),
                    status='<p class="status">%s</p>\n  ' % esc(e["status"]) if e.get("status") else "",
                    byline=esc(byline(e)), url=esc(e["url"]), srel=src_rel(e),
                    outlet=(" · " + esc(e["outlet"])) if e.get("outlet") else "",
                    archive=archive, listing=listing_html, secs=" · ".join(sec_links),
                    what="a public record" if e["category"] in ("lawsuit", "regulator")
                    else ("a resident's public account" if e["category"] == "tenant"
                          else "published reporting"),
                    issues=esc(ISSUES),
                    ctitle=esc("Correction: " + e["id"]).replace(" ", "%20").replace(":", "%3A"),
                    related=rel_html)
    meta = '<meta property="article:published_time" content="%s">\n<meta property="article:section" content="%s">\n' % (
        esc(e["date"]), esc(sec[1]))
    return page("stories/%s.html" % e["id"], story_title(e), desc,
                shell(body, sec[0], crumbs), [art, breadcrumb_ld(crumbs_abs)], "article", meta)


INTRO_RE = re.compile(r"<!--INTRO:START-->(.*?)<!--INTRO:END-->", re.S)


def build_section(sec, entries):
    slug, label, h1, ttl, intro, pred, desc = sec
    items = sorted([e for e in entries if pred(e)], key=lambda e: e["date"], reverse=True)
    out = os.path.join(slug, "index.html")
    # Intro precedence: content/intros/<slug>.html > hand-edited block already in the page
    # (anything without the data-default marker) > generated default.
    intro_html = '<p class="dek" data-default>%s</p>' % esc(intro)
    override = os.path.join("content", "intros", slug + ".html")
    if os.path.exists(override):
        with open(override, encoding="utf-8") as f:
            intro_html = f.read().strip()
    elif os.path.exists(out):
        with open(out, encoding="utf-8") as f:
            m = INTRO_RE.search(f.read())
        if m and m.group(1).strip() and "data-default" not in m.group(1):
            intro_html = m.group(1).strip()
    url = "%s/%s/" % (SITE, slug)
    crumbs_abs = [(NAME, SITE + "/"), (label, url)]
    grid, yr = "", None
    for e in items:
        y = e["date"][:4] or "Undated"
        if y != yr:
            grid += '<div class="year">%s</div>' % esc(y)
            yr = y
        grid += entry_card(e, "h2", show_kicker=(slug == "the-chairman"))
    body = """<header class="sec-head">
  <p class="kicker">{label} · {n} records · Last updated {upd}</p>
  <h1>{h1}</h1>
  <!--INTRO:START-->{intro}<!--INTRO:END-->
</header>
<div class="grid">{grid}</div>""".format(label=esc(label), n=len(items), h1=esc(h1), intro=intro_html, grid=grid,
                         upd=esc(fmt_date(max((e["date"] for e in items), default=TODAY))))
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": "%s | %s" % (label, NAME),
          "url": url, "description": desc,
          "about": BOB_FAITH if slug == "the-chairman" else GREYSTAR, "isPartOf": {"@type": "WebSite", "name": NAME, "url": SITE + "/"},
          "mainEntity": {"@type": "ItemList", "numberOfItems": len(items),
                         "itemListElement": [{"@type": "ListItem", "position": i + 1,
                                              "url": story_url(e, True), "name": e["title"]}
                                             for i, e in enumerate(items)]}}
    return out, page("%s/" % slug, ttl, desc,
                     shell(body, slug, [(NAME, BASE + "/"), (label, None)]),
                     [ld, breadcrumb_ld(crumbs_abs)]), items


def region_order(keys):
    return sorted(keys, key=lambda k: (0 if k in STATES else 1, region_name(k)))


def regions_with_stories(entries):
    out = defaultdict(list)
    for e in entries:
        for r in entry_regions(e.get("location")):
            out[r].append(e)
    return out


def compute_state_pages(props, entries):
    counts = defaultdict(int)
    for p in props:
        counts[p["s"]] += 1
    ebr = regions_with_stories(entries)
    return {k for k, n in counts.items() if n >= MIN_STATE_PROPS or ebr.get(k)}


def and_list(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def prop_li(p, entries):
    st = [e for e in entries if matches_property(e, p)]
    stories = ""
    if st:
        stories = '<span class="on-record">%d %s: %s</span>' % (
            len(st), "record" if len(st) == 1 else "records", " · ".join(
                '<a href="%s">%s</a>' % (esc(story_url(e)), esc(e["title"])) for e in st))
    return ('<li id="p-%s"%s><span class="pn">%s</span> <a class="gs" href="https://www.greystar.com/%s/p_%s" '
            'rel="noopener nofollow">Greystar listing ↗</a>%s</li>'
            % (esc(p["id"]), ' class="has"' if st else "", esc(p["n"]), esc(p["slug"]), esc(p["id"]), stories))


def build_properties(props, entries):
    by_region = defaultdict(list)
    for p in props:
        by_region[p["s"]].append(p)
    pages = {}
    ent_by_region = regions_with_stories(entries)
    pkey = lambda p: p["n"].lower()

    rows = []
    for k in region_order(by_region):
        name = region_name(k)
        slug = slugify(name)
        plist = by_region[k]
        n = len(plist)
        rstories = sorted(ent_by_region.get(k, []), key=lambda e: e["date"], reverse=True)
        nst = len(rstories)
        rows.append((k, name, slug, n, nst))
        if k not in STATE_PAGES:
            continue
        cities = defaultdict(list)
        for p in plist:
            cities[p["c"] or "Other"].append(p)
        top3 = [c for c, _ in sorted(cities.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:3]]
        blocks, small = [], []
        for c in sorted(cities):
            if len(cities[c]) >= 3:
                blocks.append('<section class="cityblock"><h3>%s <span>(%d)</span></h3><ul>%s</ul></section>'
                              % (esc(c), len(cities[c]), "".join(prop_li(p, entries) for p in sorted(cities[c], key=pkey))))
            else:
                small.extend(cities[c])
        if small:
            blocks.append('<section class="cityblock other"><h3>%s <span>(%d)</span></h3><ul>%s</ul></section>' % (
                "Other cities" if blocks else "All cities", len(small), "".join(
                    prop_li(p, entries).replace('<span class="pn">', '<span class="pn">', 1).replace(
                        '</span> <a class="gs"', '</span> <span class="pc">%s</span> <a class="gs"' % esc(p["c"]), 1)
                    for p in sorted(small, key=lambda p: (p["c"].lower(), pkey(p))))))
        rs_html = ""
        if rstories:
            rs_html = '<section class="related"><h2>Records from %s</h2><div class="grid">%s</div></section>' % (
                esc(name), "".join(entry_card(e, "h3") for e in rstories))
        title = "Greystar Apartments in %s (%d %s)" % (name, n, "Property" if n == 1 else "Properties")
        comm = "apartment community" if n == 1 else "apartment communities"
        if nst:
            desc = clip_sentence("%d Greystar-managed %s in %s, by city, plus %d sourced lawsuits, regulator "
                                 "actions and tenant reports from %s." % (n, comm, name, nst, name))
        else:
            desc = clip_sentence("%d Greystar-managed %s in %s, listed by city: %s." % (n, comm, name, and_list(top3)))
        intro = ("The Greystar Review lists %d %s in %s that appear in Greystar's public property directory, "
                 "across %d %s including %s." % (n, comm, name, len(cities), "city" if len(cities) == 1 else "cities",
                                                  and_list(top3)))
        if nst:
            intro += (" This archive also contains %d %s connected to %s, listed below."
                      % (nst, "lawsuit, regulator action, news report or tenant complaint" if nst == 1 else
                         "lawsuits, regulator actions, news reports or tenant complaints", name))
        intro += (" Listing a property here only means it is Greystar-managed or -owned per that directory; "
                  "it does not mean any complaint has been made about it.")
        url = "%s/properties/%s.html" % (SITE, slug)
        crumbs_abs = [(NAME, SITE + "/"), ("Properties", SITE + "/properties/"), (name, url)]
        body = """<header class="sec-head">
  <p class="kicker">Property index · {n} properties · {nc} {cw}</p>
  <h1>Greystar Apartments in {name}</h1>
  <p class="dek">{intro}</p>
</header>
{rs}
<h2 class="list-h">Properties by city</h2>
<div class="cities">{blocks}</div>""".format(
            n=n, nc=len(cities), cw="city" if len(cities) == 1 else "cities", name=esc(name), intro=esc(intro),
            rs=rs_html, blocks="".join(blocks))
        ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": title, "url": url,
              "description": desc, "about": GREYSTAR,
              "isPartOf": {"@type": "WebSite", "name": NAME, "url": SITE + "/"},
              "mainEntity": {"@type": "ItemList", "numberOfItems": n,
                             "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": p["n"],
                                                  "url": "https://www.greystar.com/%s/p_%s" % (p["slug"], p["id"])}
                                                 for i, p in enumerate(sorted(plist, key=lambda p: (p["c"], p["n"])))]}}
        pages[os.path.join("properties", slug + ".html")] = page(
            "properties/%s.html" % slug, title, desc,
            shell(body, "properties", [(NAME, BASE + "/"), ("Properties", BASE + "/properties/"), (name, None)]),
            [ld, breadcrumb_ld(crumbs_abs)])

    def tbl(rs):
        out = []
        for k, name, slug, n, nst in rs:
            label = ('<a href="%s/properties/%s.html">%s</a>' % (BASE, esc(slug), esc(name)) if k in STATE_PAGES
                     else '<a href="#r-%s">%s</a>' % (esc(slug), esc(name)))
            out.append('<li>%s <span>%d %s%s</span></li>' % (label, n, "property" if n == 1 else "properties",
                                                             (" · %d records" % nst) if nst else ""))
        return '<ul class="regions">%s</ul>' % "".join(out)
    smalls = [r for r in rows if r[0] not in STATE_PAGES]
    small_html = ""
    if smalls:
        small_html = '<h2 class="list-h">Smaller markets</h2><div class="cities">%s</div>' % "".join(
            '<section class="cityblock" id="r-%s"><h3>%s <span>(%d)</span></h3><ul>%s</ul></section>' % (
                esc(slug), esc(name), n, "".join(
                    prop_li(p, entries).replace('</span> <a class="gs"', '</span> <span class="pc">%s</span> <a class="gs"' % esc(p["c"]), 1)
                    for p in sorted(by_region[k], key=lambda p: (p["c"].lower(), pkey(p)))))
            for k, name, slug, n, nst in smalls)
    body = """<header class="sec-head">
  <p class="kicker">Property index · {total} properties · {nr} states &amp; regions</p>
  <h1>Greystar Apartments by State</h1>
  <p class="dek">An index of every property in Greystar's public property directory, by state and region. Each state page lists properties by city with a link to Greystar's listing, plus any lawsuits, regulator actions, reporting or tenant complaints connected to that state. Listing a property only means it appears in that directory.</p>
</header>
<h2 class="list-h">United States</h2>{us}
<h2 class="list-h">International</h2>{intl}
{small}""".format(total="{:,}".format(len(props)), nr=len(rows), us=tbl([r for r in rows if r[0] in STATES]),
                  intl=tbl([r for r in rows if r[0] not in STATES]), small=small_html)
    url = SITE + "/properties/"
    paged = [r for r in rows if r[0] in STATE_PAGES]
    ld = {"@context": "https://schema.org", "@type": "CollectionPage",
          "name": "Greystar Apartments by State | " + NAME, "url": url, "about": GREYSTAR,
          "mainEntity": {"@type": "ItemList", "numberOfItems": len(paged),
                         "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": r[1],
                                              "url": "%s/properties/%s.html" % (SITE, r[2])}
                                             for i, r in enumerate(paged)]}}
    total = "{:,}".format(len(props))
    pages[os.path.join("properties", "index.html")] = page(
        "properties/", "Greystar Apartments by State (%s Properties)" % total,
        clip_sentence("All %s Greystar-managed apartment communities by state and region, with sourced lawsuits, "
                      "regulator actions and tenant reports for each state." % total),
        shell(body, "properties", [(NAME, BASE + "/"), ("Properties", None)]),
        [ld, breadcrumb_ld([(NAME, SITE + "/"), ("Properties", url)])])
    return pages, rows


def build_about(entries):
    counts = {s[0]: sum(1 for e in entries if s[5](e)) for s in SECTIONS}
    body = """<article class="story about">
  <p class="kicker">About &amp; Editorial Standards</p>
  <h1>About The Greystar Review</h1>
  <p class="dek">The Greystar Review is an independent public archive of lawsuits, government actions, news reporting and tenant complaints involving Greystar, the largest apartment manager in the United States. Every entry has a date, a status and a link to its source, and allegations are labeled as allegations. We are not affiliated with Greystar Real Estate Partners. Corrections and responses, including from Greystar, can be <a href="{issues}&amp;title=Correction:%20" rel="noopener">filed on GitHub</a> and will be published with the entry.</p>
  <h2>What this is</h2>
  <p>A dated, sourced record in five sections, each summarizing material that already exists in public:</p>
  <ul>
    <li><a href="{b}/court-docket/">Court Docket</a> ({c[court-docket]}): civil lawsuits and class actions naming Greystar or its affiliates.</li>
    <li><a href="{b}/regulators/">Regulators</a> ({c[regulators]}): actions by federal, state and local agencies, and complaints filed with them.</li>
    <li><a href="{b}/reporting/">Reporting</a> ({c[reporting]}): news reporting and investigations from national and local outlets.</li>
    <li><a href="{b}/letters/">Letters from Tenants</a> ({c[letters]}): residents' publicly posted accounts.</li>
    <li><a href="{b}/the-chairman/">The Chairman</a> ({c[the-chairman]}): records and reporting that name Bob Faith, Greystar's founder and CEO.</li>
  </ul>
  <p>A separate <a href="{b}/properties/">property index</a> lists every community in Greystar's public property directory, by state and city. Appearing there only means Greystar lists the property; it does not mean any complaint has been made about it.</p>
  <h2>How entries are sourced</h2>
  <p>Every entry links to its primary source: a court record or docket, an agency release or filing, a published article, or the original public post. Where available, an archived copy is linked too. An entry is published only if its source loads or is confirmed as a real, known URL. A daily automated sweep surfaces candidate items; nothing it finds is published automatically, and each candidate is reviewed against its source before it is added. This site does not publish original allegations or anonymous tips.</p>
  <h2>Allegations, findings and status labels</h2>
  <p>Each summary is written neutrally and attributes claims to whoever made them: "alleges", "according to", "the complaint says". A filed complaint is not a finding, and a pending complaint is never described as a violation. Settlements are reported as resolutions, and we note whether wrongdoing was admitted. Every entry carries a status label, such as filed, pending, settled, dismissed or verdict, which is updated when an outcome becomes known. Tenant letters are first-person allegations that have not been verified by this site; residents are identified by first name or initial only, and no private individual's contact details are published.</p>
  <h2>Corrections and responses</h2>
  <p>If an entry is wrong, out of date or missing an outcome, <a href="{issues}&amp;title=Correction:%20" rel="noopener">file a correction on GitHub</a>. Corrections are reviewed against the source and, when confirmed, the entry is updated. Greystar, Bob Faith and anyone else named in an entry may submit a response or a later outcome with a source, and it will be published with the entry.</p>
  <h2>Independence</h2>
  <p>The Greystar Review is independent and is not affiliated with, endorsed by or funded by Greystar Real Estate Partners or any party to the matters it records. The full record is published as open data: <a href="{b}/data/entries.json">entries.json</a> and <a href="{b}/data/properties.json">properties.json</a>.</p>
</article>""".format(b=BASE, c=counts, issues=esc(ISSUES))
    url = SITE + "/about.html"
    ld = {"@context": "https://schema.org", "@type": "AboutPage", "name": "About & Editorial Standards",
          "url": url, "publisher": PUBLISHER, "about": PUBLISHER}
    return page("about.html", "About & Editorial Standards | " + NAME,
                "How The Greystar Review sources, dates and labels entries, separates allegations from findings, "
                "and handles corrections. Not affiliated with Greystar.",
                shell(body, None, [(NAME, BASE + "/"), ("About", None)]),
                [ld, breadcrumb_ld([(NAME, SITE + "/"), ("About", url)])])


STATIC_RE = re.compile(r"<!--STATIC:START-->.*?<!--STATIC:END-->", re.S)
MAIN_RE = re.compile(r'(<main\b[^>]*\bid="ledger"[^>]*>)(.*?)(</main>)', re.S)


def inject_index(entries, sections, regions):
    latest = sorted(entries, key=lambda e: e["date"], reverse=True)[:30]
    secs = "".join('<li><a href="%s/%s/">%s</a> <span>(%d)</span></li>' % (BASE, s[0], esc(s[1]), len(sections[s[0]]))
                   for s in SECTIONS)
    static = """<!--STATIC:START-->
<div class="static-fallback">
<style>.static-fallback .depts a{{display:inline-block;font:800 12px "Libre Franklin",sans-serif;letter-spacing:.12em;text-transform:uppercase;padding:12px 14px;color:var(--ink);text-decoration:none}}.static-fallback .list-h{{font:800 13px "Libre Franklin",sans-serif;letter-spacing:.16em;text-transform:uppercase;margin:24px 0 4px;padding-bottom:8px;border-bottom:1px solid var(--ink)}}.static-fallback .regions{{columns:3 240px;list-style:none;padding:0}}.static-fallback .regions li{{padding:6px 0;border-bottom:1px solid var(--line)}}</style>
<nav class="depts static-nav" aria-label="Sections">{nav}</nav>
<h2 class="list-h">Latest from the Record</h2>
<div class="grid">{cards}</div>
<h2 class="list-h">Sections</h2>
<ul class="regions">{secs}</ul>
<h2 class="list-h">The Properties</h2>
<p>{top} · <a href="{b}/properties/">All {np} states &amp; regions</a> · <a href="{b}/about.html">Editorial standards</a></p>
</div>
<!--STATIC:END-->""".format(nav=nav_links(), cards="".join(entry_card(e) for e in latest), secs=secs, b=BASE,
                            np=len(regions), top=" · ".join(
                                '<a href="%s/properties/%s.html">Greystar apartments in %s (%d)</a>' % (BASE, esc(r[2]), esc(r[1]), r[3])
                                for r in sorted([r for r in regions if r[0] in STATE_PAGES], key=lambda r: -r[3])[:5]))
    with open("index.html", encoding="utf-8") as f:
        src = f.read()
    m = MAIN_RE.search(src)
    if not m:
        sys.exit('index.html: <main id="ledger"> not found')
    inner = m.group(2)
    new_inner = STATIC_RE.sub(lambda _: static, inner) if STATIC_RE.search(inner) else ("\n" + static + "\n")
    out = src[:m.start(2)] + new_inner + src[m.end(2):]
    if out != src:
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(out)


def write(path, content):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            if f.read() == content:
                return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def main():
    global HEAD_COMMON
    if not os.path.exists(os.path.join("data", "entries.json")):
        sys.exit("run from the repo root")
    with open("data/entries.json", encoding="utf-8") as f:
        entries = json.load(f)
    with open("data/properties.json", encoding="utf-8") as f:
        props = json.load(f)
    HEAD_COMMON = head_common()
    prop_index = defaultdict(list)
    for p in props:
        prop_index[p["n"].strip().lower()].append(p)

    STATE_PAGES.clear()
    STATE_PAGES.update(compute_state_pages(props, entries))
    changed = 0
    ids = {e["id"] for e in entries}
    os.makedirs("stories", exist_ok=True)
    for e in entries:
        changed += write(os.path.join("stories", e["id"] + ".html"), build_story(e, entries, prop_index))
    for fn in os.listdir("stories"):  # remove pages for deleted entries
        if fn.endswith(".html") and fn[:-5] not in ids:
            os.remove(os.path.join("stories", fn))
            changed += 1

    sections = {}
    for sec in SECTIONS:
        out, content, items = build_section(sec, entries)
        sections[sec[0]] = items
        changed += write(out, content)

    ppages, regions = build_properties(props, entries)
    keep = set(ppages)
    for fn in os.listdir("properties") if os.path.isdir("properties") else []:
        if os.path.join("properties", fn) not in keep and fn.endswith(".html"):
            os.remove(os.path.join("properties", fn))
    for path, content in ppages.items():
        changed += write(path, content)
    changed += write("about.html", build_about(entries))
    inject_index(entries, sections, regions)

    # sitemap
    latest = max(e["date"] for e in entries) if entries else TODAY
    urls = [(SITE + "/", TODAY), (SITE + "/about.html", TODAY), (SITE + "/properties/", TODAY)]
    for s in SECTIONS:
        items = sections[s[0]]
        urls.append(("%s/%s/" % (SITE, s[0]), max((e["date"] for e in items), default=latest)))
    for k, name, slug, n, nst in regions:
        if k in STATE_PAGES:
            urls.append(("%s/properties/%s.html" % (SITE, slug), TODAY))
    for e in sorted(entries, key=lambda e: e["date"], reverse=True):
        urls.append((story_url(e, True), e["date"]))
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u, lm in urls:
        sm.append("  <url><loc>%s</loc><lastmod>%s</lastmod></url>" % (esc(u), esc(lm)))
    sm.append("</urlset>\n")
    write("sitemap.xml", "\n".join(sm))
    print("stories=%d sections=%d regions=%d state_pages=%d sitemap_urls=%d changed_files=%d head_common=%s"
          % (len(entries), len(SECTIONS), len(regions), len(STATE_PAGES), len(urls), changed,
             "assets/head-common.html" if os.path.exists("assets/head-common.html") else "fallback"))


if __name__ == "__main__":
    main()
