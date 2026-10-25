#!/usr/bin/env python3
"""Curbside Rules static site builder. Standard library only (Python 3.8+).

Usage:  python3 build.py
Reads   site.config.json, content/pages/<city>/<item>.md, templates/base.html, static/*
Writes  docs/  (deployable as-is to GitHub Pages "/docs" or Netlify publish dir)
"""
import datetime as dt
import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "site.config.json").read_text())
OUT = ROOT / CONFIG.get("output_dir", "docs")
BASE = CONFIG["base_url"].rstrip("/")
BASE_PATH = "/" + CONFIG.get("base_path", "/").strip("/") + "/"
if BASE_PATH == "//":
    BASE_PATH = "/"


def with_base(html_text):
    """Prefix every root-relative href/src ("/x", not "//x") with base_path."""
    if BASE_PATH == "/":
        return html_text
    return re.sub(r'((?:href|src)=")/(?!/)', lambda m: m.group(1) + BASE_PATH, html_text)
TEMPLATE = (ROOT / "templates" / "base.html").read_text()
SOURCES_NOTE = ("Every rule, fee, schedule and phone number on this page comes from these official pages. "
                "Rules change, so confirm with the city before you put anything on the curb.")
# Optional front-matter "category": "housing" lists a page under "Moving & housing" instead of the trash guides.
CATEGORY_LABELS = {"housing": "Moving & housing"}
ERRORS = []


def esc(s):
    return html.escape(str(s), quote=True)


# ---------------------------------------------------------------- markdown
def inline(text, sources=None, src_used=None):
    """Tiny inline Markdown: escapes HTML, then **bold**, *em*, [text](url), [[source-id]]."""
    out = esc(text)

    def cite(m):
        sid = m.group(1)
        if sources is None or sid not in sources:
            ERRORS.append(f"unknown source id [[{sid}]]")
            return m.group(0)
        if src_used is not None:
            src_used.add(sid)
        s = sources[sid]
        n = s["_n"]
        return (f'<a class="cite" href="{esc(s["url"])}" rel="noopener" '
                f'title="{esc(s["title"])} (last checked {esc(s["_checked"])})">'
                f'{esc(s["publisher"])}<sup>[{n}]</sup></a>')

    out = re.sub(r"\[\[([a-z0-9_-]+)\]\]", cite, out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?![\*\w])", r"<em>\1</em>", out)

    def link(m):
        label, url = m.group(1), html.unescape(m.group(2))
        ext = url.startswith("http")
        rel = ' rel="noopener"' if ext else ""
        return f'<a href="{esc(url)}"{rel}>{label}</a>'

    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, out)
    return out


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def markdown(md, sources=None, src_used=None, shortcodes=None, toc=None):
    """Block Markdown subset: ## / ### headings, paragraphs, - lists, 1. lists, > notes, {{shortcodes}}."""
    lines = md.strip("\n").split("\n")
    html_out, para, lst, lst_type = [], [], [], None

    def flush_para():
        nonlocal para
        if para:
            html_out.append(f"<p>{inline(' '.join(para), sources, src_used)}</p>")
            para = []

    def flush_list():
        nonlocal lst, lst_type
        if lst:
            items = "".join(f"<li>{inline(i, sources, src_used)}</li>" for i in lst)
            html_out.append(f"<{lst_type}>{items}</{lst_type}>")
            lst, lst_type = [], None

    for raw in lines:
        line = raw.rstrip()
        sc = re.fullmatch(r"\{\{\s*([a-z0-9-]+)\s*\}\}", line.strip())
        if sc:
            flush_para(); flush_list()
            name = sc.group(1)
            if shortcodes and name in shortcodes:
                html_out.append(shortcodes[name]())
            else:
                ERRORS.append(f"unknown shortcode {{{{{name}}}}}")
            continue
        h = re.match(r"^(#{2,3})\s+(.*)$", line)
        ul = re.match(r"^\s*[-*]\s+(.*)$", line)
        ol = re.match(r"^\s*\d+\.\s+(.*)$", line)
        bq = re.match(r"^>\s?(.*)$", line)
        if h:
            flush_para(); flush_list()
            lvl, text = len(h.group(1)), h.group(2)
            hid = slugify(re.sub(r"\[\[.*?\]\]", "", text))
            if toc is not None and lvl == 2:
                toc.append((hid, text))
            html_out.append(f'<h{lvl} id="{hid}">{inline(text, sources, src_used)}</h{lvl}>')
        elif ul or ol:
            flush_para()
            t = "ul" if ul else "ol"
            if lst_type and lst_type != t:
                flush_list()
            lst_type = t
            lst.append((ul or ol).group(1))
        elif bq:
            flush_para(); flush_list()
            html_out.append(f'<p class="note">{inline(bq.group(1), sources, src_used)}</p>')
        elif not line.strip():
            flush_para(); flush_list()
        elif lst and raw.startswith("  "):
            lst[-1] += " " + line.strip()
        else:
            flush_list()
            para.append(line.strip())
    flush_para(); flush_list()
    return "\n".join(html_out)


# ---------------------------------------------------------------- content
def load_page(path):
    text = path.read_text()
    m = re.match(r"^---json\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        ERRORS.append(f"{path}: missing ---json front matter")
        return None
    meta = json.loads(m.group(1))
    meta["body"] = m.group(2)
    meta["_path"] = path
    required = ["title", "description", "city", "state", "item", "slug", "published",
                "updated", "last_checked", "sources"]
    for k in required:
        if k not in meta:
            ERRORS.append(f"{path}: missing front-matter key '{k}'")
    if len(meta.get("description", "")) > 160:
        ERRORS.append(f"{path}: description is {len(meta['description'])} chars (max 160)")
    meta["city_slug"] = slugify(meta["city"])
    meta["url_path"] = f"/{meta['city_slug']}/{meta['slug']}/"
    return meta


def affiliate_href(key):
    a = CONFIG["affiliates"].get(key)
    if not a:
        ERRORS.append(f"unknown affiliate '{key}'")
        return "#"
    return a.get("tracking_url") or a["url"]


def pickup_box(page):
    def render():
        items = []
        # Optional front-matter "partners": list of affiliate keys that actually serve this city.
        keys = page.get("partners")
        if keys is None:
            keys = list(CONFIG["affiliates"])
        for key in keys:
            if key not in CONFIG["affiliates"]:
                ERRORS.append(f"{page['_path'].name}: unknown partner '{key}'")
        keys = [k for k in keys if k in CONFIG["affiliates"]]
        if not keys:
            ERRORS.append(f"{page['_path'].name}: {{{{pickup-box}}}} used but no partners serve this city; remove the box")
        for key in keys:
            a = CONFIG["affiliates"][key]
            items.append(
                f'<li><a class="btn" data-affiliate="{esc(key)}" href="{esc(affiliate_href(key))}" '
                f'rel="sponsored nofollow noopener" target="_blank">{esc(a["name"])} &rarr;</a>'
                f'<span>{esc(a["blurb"])}</span></li>')
        return (
            '<aside class="pickup-box" aria-labelledby="pickup-h">'
            f'<h2 id="pickup-h">{esc(page.get("pickup_heading", "Too much to haul? Book a pickup"))}</h2>'
            + (f'<p>{esc(page["pickup_intro"])}</p>' if page.get("pickup_intro") else
               f'<p>If you can\'t use the city option, or you have more than a {esc(page["item"].lower())} to clear out, '
               'a paid junk-removal service may be easier. Confirm they serve your area and check the price before you book.</p>')
            + f'<ul>{"".join(items)}</ul>'
            '<p class="small">Paid links. We may earn a commission if you book, at no extra cost to you. '
            '<a href="/disclosure/">Disclosure</a></p>'
            '</aside>')
    return render


def page_html(*, title, description, path, body, jsonld=None, extra_head=""):
    canonical = BASE + path
    ld = ""
    for block in (jsonld or []):
        ld += '<script type="application/ld+json">' + json.dumps(block, ensure_ascii=False).replace("</", "<\\/") + "</script>\n"
    out = TEMPLATE
    repl = {
        "{{lang}}": esc(CONFIG.get("language", "en-US")),
        "{{title}}": esc(title),
        "{{description}}": esc(description),
        "{{canonical}}": esc(canonical),
        "{{site_name}}": esc(CONFIG["site_name"]),
        "{{tagline}}": esc(CONFIG["tagline"]),
        "{{jsonld}}": ld,
        "{{extra_head}}": extra_head,
        "{{body}}": body,
        "{{year}}": str(dt.date.today().year),
    }
    for k, v in repl.items():
        out = out.replace(k, v)
    return out


def write(path, content):
    f = OUT / path.lstrip("/")
    if path.endswith("/"):
        f = f / "index.html"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(with_base(content))


def fmt_date(iso):
    d = dt.date.fromisoformat(iso)
    return d.strftime("%b %-d, %Y")


def render_page(p, all_pages):
    sources = {}
    for i, s in enumerate(p["sources"], 1):
        s = dict(s)
        s["_n"] = i
        s["_checked"] = fmt_date(s.get("checked", p["last_checked"]))
        sources[s["id"]] = s
    used, toc = set(), []
    has_aff = "{{pickup-box}}" in p["body"]
    shortcodes = {"pickup-box": pickup_box(p)}
    body_html = markdown(p["body"], sources, used, shortcodes, toc)

    facts = ""
    if p.get("quick_facts"):
        lis = "".join(f"<li>{inline(f, sources, used)}</li>" for f in p["quick_facts"])
        facts = f'<section class="facts" aria-label="Quick facts"><h2>Quick answer</h2><ul>{lis}</ul></section>'

    faq_html, faq_ld = "", None
    if p.get("faq"):
        toc.append(("faq", "FAQ"))
        qa = []
        for f in p["faq"]:
            qa.append(f'<details><summary>{esc(f["q"])}</summary><div>{inline(f["a"], sources, used)}</div></details>')
        faq_html = '<section class="faq"><h2 id="faq">Frequently asked questions</h2>' + "".join(qa) + "</section>"
        faq_ld = {
            "@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": f["q"],
                            "acceptedAnswer": {"@type": "Answer",
                                               "text": re.sub(r"<[^>]+>", "", inline(f["a"], sources)).replace("&amp;", "&")}}
                           for f in p["faq"]]}

    for sid in sources:
        if sid not in used:
            ERRORS.append(f"{p['_path'].name}: source '{sid}' is listed but never cited")
    toc.append(("sources", "Sources"))
    src_lis = "".join(
        f'<li id="src-{s["_n"]}"><a href="{esc(s["url"])}" rel="noopener">{esc(s["title"])}</a> '
        f'&mdash; {esc(s["publisher"])}. <span class="checked">Last checked {esc(s["_checked"])}.</span></li>'
        for s in sources.values())
    sources_html = (f'<section class="sources"><h2 id="sources">Sources</h2>'
                    f'<p class="small">{esc(p.get("sources_note", SOURCES_NOTE))}</p><ol>{src_lis}</ol></section>')

    related = [o for o in all_pages if o is not p and (o["city"] == p["city"] or o["item"] == p["item"])]
    rel_html = ""
    if related:
        rel_html = '<section class="related"><h2>Related guides</h2><ul>' + "".join(
            f'<li><a href="{o["url_path"]}">{esc(o["title"])}</a></li>' for o in related) + "</ul></section>"

    toc_items = []
    for hid, t in toc:
        label = inline(re.sub(r"\[\[.*?\]\]", "", t)).strip()
        toc_items.append(f'<li><a href="#{hid}">{label}</a></li>')
    toc_html = ('<nav class="toc" aria-label="On this page"><strong>On this page</strong><ul>'
                + "".join(toc_items) + "</ul></nav>")

    disclosure = ('<p class="disclosure"><strong>Disclosure:</strong> This page contains paid links to junk-removal services. '
                  'If you book through them we may earn a commission, at no extra cost to you. It never affects the rules we report, '
                  'which come only from official sources. <a href="/disclosure/">Learn more</a>.</p>') if has_aff else ""

    crumbs = (f'<nav class="crumbs" aria-label="Breadcrumb"><a href="/">Home</a> &rsaquo; '
              f'<a href="/{p["city_slug"]}/">{esc(p["city"])}, {esc(p["state"])}</a> &rsaquo; <span>{esc(p["item"])}</span></nav>')

    body = f"""{crumbs}
<article>
<header class="page-head">
<h1>{esc(p["title"])}</h1>
<p class="lede">{esc(p["description"])}</p>
<p class="meta">Last checked against official sources: <time datetime="{p["last_checked"]}">{fmt_date(p["last_checked"])}</time> &middot; Updated <time datetime="{p["updated"]}">{fmt_date(p["updated"])}</time></p>
{disclosure}
</header>
{facts}
{toc_html}
{body_html}
{faq_html}
{sources_html}
</article>
{rel_html}"""

    article_ld = {
        "@context": "https://schema.org", "@type": "Article",
        "headline": p["title"], "description": p["description"],
        "datePublished": p["published"], "dateModified": p["updated"],
        "mainEntityOfPage": BASE + p["url_path"],
        "author": {"@type": "Organization", "name": CONFIG["site_name"], "url": BASE + "/about/"},
        "publisher": {"@type": "Organization", "name": CONFIG["site_name"], "url": BASE + "/"},
        "about": {"@type": "City", "name": f'{p["city"]}, {p["state"]}'},
        "citation": [s["url"] for s in sources.values()],
    }
    crumbs_ld = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": f'{p["city"]}, {p["state"]}', "item": BASE + f'/{p["city_slug"]}/'},
            {"@type": "ListItem", "position": 3, "name": p["item"], "item": BASE + p["url_path"]}]}
    lds = [article_ld, crumbs_ld] + ([faq_ld] if faq_ld else [])
    write(p["url_path"], page_html(title=p.get("seo_title", p["title"]), description=p["description"],
                                   path=p["url_path"], body=body, jsonld=lds))


def render_static_page(path, src_file, title, description):
    md = (ROOT / "content" / src_file).read_text()
    md = md.replace("{{site_name}}", CONFIG["site_name"])
    contact = CONFIG.get("contact_email")
    md = md.replace("{{contact}}", f"Spotted an error? Email [{contact}](mailto:{contact})." if contact else
                    "Spotted an error? A corrections address is coming soon.")
    body = f'<article><header class="page-head"><h1>{esc(title)}</h1></header>{markdown(md)}</article>'
    write(path, page_html(title=f"{title} | {CONFIG['site_name']}", description=description, path=path, body=body))


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    pages = [p for p in (load_page(f) for f in sorted((ROOT / "content" / "pages").glob("*/*.md"))) if p]
    seen = {}
    for p in pages:
        for k in ("title", "description"):
            if p[k] in seen:
                ERRORS.append(f"duplicate {k}: {p[k]!r}")
            seen[p[k]] = 1
    for p in pages:
        render_page(p, pages)

    # city hubs
    cities = {}
    for p in pages:
        cities.setdefault((p["city"], p["state"], p["city_slug"]), []).append(p)
    for (city, state, cslug), plist in sorted(cities.items()):
        def hub_lis(qs):
            return "".join(f'<li><a href="{q["url_path"]}">{esc(q["title"])}</a> <span class="small">Checked {fmt_date(q["last_checked"])}</span></li>' for q in qs)
        trash = [q for q in plist if not q.get("category")]
        extra = ""
        for cat, label in CATEGORY_LABELS.items():
            qs = [q for q in plist if q.get("category") == cat]
            if qs:
                extra += f'<h2 id="{slugify(label)}">{esc(label)}</h2><ul class="guide-list">{hub_lis(qs)}</ul>'
        body = (f'<nav class="crumbs" aria-label="Breadcrumb"><a href="/">Home</a> &rsaquo; <span>{esc(city)}, {esc(state)}</span></nav>'
                f'<article><header class="page-head"><h1>Bulk trash and junk disposal in {esc(city)}, {esc(state)}</h1>'
                f'<p class="lede">Item-by-item guides to getting rid of large items in {esc(city)}, built from official city sources.</p></header>'
                f'<ul class="guide-list">{hub_lis(trash)}</ul>{extra}</article>')
        write(f"/{cslug}/", page_html(
            title=f"{city}, {state} Bulk Trash & Junk Disposal Guides | {CONFIG['site_name']}",
            description=f"How to get rid of mattresses, furniture, appliances and other bulky items in {city}, {state}, using official city rules.",
            path=f"/{cslug}/", body=body))

    # homepage
    groups = ""
    for (city, state, cslug), plist in sorted(cities.items()):
        lis = "".join(f'<li><a href="{q["url_path"]}">{esc(q["item"])}</a>'
                      + (f' <span class="small">({esc(CATEGORY_LABELS[q["category"]])})</span>' if q.get("category") in CATEGORY_LABELS else "")
                      + '</li>' for q in plist)
        groups += f'<section class="city"><h3><a href="/{cslug}/">{esc(city)}, {esc(state)}</a></h3><ul>{lis}</ul></section>'
    latest = sorted(pages, key=lambda q: q["published"], reverse=True)[:10]
    latest_html = "".join(f'<li><a href="{q["url_path"]}">{esc(q["title"])}</a></li>' for q in latest)
    home_body = f"""<section class="hero"><h1>{esc(CONFIG["site_name"])}</h1>
<p class="lede">{esc(CONFIG["tagline"])} Every rule, fee and phone number comes from official city or state pages, with links and a last-checked date.</p></section>
<section><h2>Latest guides</h2><ul class="guide-list">{latest_html}</ul></section>
<section><h2>All cities</h2><div class="cities">{groups}</div>
<p class="small">New city guides are added regularly. Don't see yours yet? Check back soon.</p></section>"""
    site_ld = {"@context": "https://schema.org", "@type": "WebSite", "name": CONFIG["site_name"], "url": BASE + "/",
               "description": CONFIG["tagline"]}
    write("/", page_html(title=f"{CONFIG['site_name']}: Bulk Trash & Junk Disposal Rules by City",
                         description="How to get rid of mattresses, couches, appliances and other bulky trash in your city. Official rules, fees and schedules, with sources.",
                         path="/", body=home_body, jsonld=[site_ld]))

    render_static_page("/about/", "about.md", "About " + CONFIG["site_name"],
                       f"Who runs {CONFIG['site_name']}, how we research city bulk trash rules, and how we make money.")
    render_static_page("/disclosure/", "disclosure.md", "Affiliate Disclosure",
                       f"How {CONFIG['site_name']} earns money from paid links to junk-removal services.")

    # 404
    write("/404.html", page_html(title=f"Page not found | {CONFIG['site_name']}", description="Page not found.",
                                 path="/404.html", body='<article><h1>Page not found</h1><p><a href="/">Back to all cities</a></p></article>',
                                 extra_head='<meta name="robots" content="noindex">'))

    # sitemap + robots
    urls = [("/", max([p["updated"] for p in pages] or [dt.date.today().isoformat()]))]
    urls += [(f"/{c[2]}/", max(q["updated"] for q in pl)) for c, pl in sorted(cities.items())]
    urls += [(p["url_path"], p["updated"]) for p in pages]
    urls += [("/about/", None), ("/disclosure/", None)]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u, lm in urls:
        sm.append(f"  <url><loc>{esc(BASE + u)}</loc>" + (f"<lastmod>{lm}</lastmod>" if lm else "") + "</url>")
    sm.append("</urlset>")
    (OUT / "sitemap.xml").write_text("\n".join(sm) + "\n")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n")

    for f in (ROOT / "static").iterdir():
        shutil.copy(f, OUT / f.name)
    (OUT / ".nojekyll").write_text("")

    if not BASE.endswith(BASE_PATH.rstrip("/")):
        print(f"WARNING: base_url ({BASE}) doesn't end with base_path ({BASE_PATH}); canonicals and links may disagree.")
    if "REPLACE-WITH-YOUR-DOMAIN" in BASE:
        print("WARNING: base_url in site.config.json is still a placeholder; set it before deploying.")
    if ERRORS:
        print("BUILD ERRORS:\n  " + "\n  ".join(ERRORS))
        sys.exit(1)
    print(f"Built {len(pages)} guide page(s), {len(cities)} city hub(s) -> {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
