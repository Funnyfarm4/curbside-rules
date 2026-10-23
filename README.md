# Curbside Rules (working name)

Static directory of bulk trash and junk disposal rules by US city and item.

- `site.config.json`: site name, domain (`base_url`), affiliate links
- `content/pages/<city>/<item>.md`: one guide per file (JSON front matter + Markdown)
- `content/_templates/guide-template.md`: copy this for a new guide
- `content/about.md`, `content/disclosure.md`: static pages
- `templates/base.html`, `static/`: layout, CSS, favicon
- `build.py`: builds everything into `docs/` (stdlib only)
- `scripts/check.py`: local server + crawler QA
- `pages-queue.json`: the nightly page queue
- `PUBLISHING.md`: the nightly routine, step by step

Build: `python3 build.py && python3 scripts/check.py`
