# Publishing a new nightly page

One page per night. Target time: 45-60 minutes. Only Python 3 is required (no packages).

## 1. Pick the page

Open `pages-queue.json` and take the first entry with `"status": "queued"`. Note its `city`, `state`, `item`, `slug` and `start_with_agency`.

## 2. Research checklist (official sources only)

Use only **official** sources: the city's `.gov` site (or the county's, if the county runs trash), its public works or sanitation department, its 311 site, the state environmental agency, or a city-contracted hauler's page **for that city**. News articles, Reddit and blogs are fine for ideas but are never cited.

Fetch each page yourself on the day you publish, and record:

- [ ] Can the item go out with regular trash? Any state disposal ban?
- [ ] City curbside option: who qualifies (building size, housing type, service area)
- [ ] How to schedule: online tool URL, phone number(s), app, lead time
- [ ] Cost: exact fee, or "free" **only if an official page says free**
- [ ] Limits: items per pickup or per year
- [ ] Prep rules: set-out time, placement, bagging/wrapping, size or weight limits, prohibited items
- [ ] Cancel / missed-pickup rules
- [ ] What to do if you don't qualify (large buildings, commercial, outside service area)
- [ ] Official drop-off sites: address, hours, fee, residency proof
- [ ] Donation or retailer take-back, only if an official page mentions it
- [ ] 3-6 real FAQ questions (check Google autocomplete and "People also ask" for wording)

**If you can't verify something on an official page, leave it out.** Don't fill gaps from memory or third-party sites. If two official pages disagree (e.g. "6 units or fewer" vs "more than 7 units"), use the stricter or more specific statement and note the conflict in your report.

## 3. Write the source file

```
cp content/_templates/guide-template.md content/pages/<city-slug>/<item-slug>.md
```

- `<city-slug>` is the lowercase hyphenated city (`new-york-city`, `washington`). The build derives it from `"city"`, so keep them in sync.
- Front matter is JSON between `---json` and `---`. Required keys: `title, description, city, state, item, slug, published, updated, last_checked, sources`. Optional: `seo_title, quick_facts, faq`.
- `description` must be 160 characters or fewer and unique.
- Every source gets an `id`. Cite it inline as `[[id]]`. The build renders a linked citation and a numbered Sources list with "Last checked <date>". The build **fails** if a source is never cited or a `[[id]]` doesn't exist.
- Body Markdown supports: `##`/`###` headings, paragraphs, `-` and `1.` lists, `**bold**`, `*italic*`, `[text](url)`, `> note` callouts, and `{{pickup-box}}`.
- Optional `partners`: list of affiliate keys from `site.config.json` that actually serve the city (check each partner's public service-area page). Without it, every partner is shown. Example: Indianapolis pages use `["loadup"]` because JeteLi only serves South Florida (Palm Beach, Martin, Broward) as of Oct 24, 2026.
- Optional `category`: `"housing"` lists the page under a "Moving & housing" heading on the city hub (and labels it on the homepage) instead of with the trash guides. Example: `/indianapolis/cheap-rentals/`. Housing pages can also set `pickup_heading`, `pickup_intro` and `sources_note` to reword the partner box and the Sources blurb.
- Put `{{pickup-box}}` right after the "doesn't qualify" section. Any page with the box automatically gets the FTC disclosure at the top.
- Link internally to existing guides (same city or same item) where it helps. A "Related guides" block is added automatically.

## 4. Build and check

```
python3 build.py                     # writes docs/
python3 scripts/check.py             # local server + crawl: HTML, links, anchors, SEO tags, JSON-LD
python3 scripts/check.py --external  # also pings every external link (mass.gov-style 403s are warnings)
```

Preview by hand: the simplest way is `python3 scripts/check.py` (it serves under base_path). With `python3 -m http.server`, serve the folder *above* a copy named like the base path, or set `base_path` to `/` temporarily.

Fix anything listed under PROBLEMS before deploying.

## 5. Update the queue

In `pages-queue.json`, set the entry's `"status": "published"` and add it to the `published` array with `url_path` and date. Add new ideas to the end of `queue` whenever research turns them up.

## 6. Deploy (GitHub Pages: https://funnyfarm4.github.io/curbside-rules/)

The site is plain files in `docs/`. `site.config.json` has `base_url = https://funnyfarm4.github.io/curbside-rules` and `base_path = /curbside-rules/`. The build prefixes every root-relative link, the CSS and the favicon with `base_path`. `scripts/check.py` serves `docs/` only under `/curbside-rules/`, the same way GitHub Pages does, so any link that skipped the prefix fails the check.

### One-time setup (status on Oct 22, 2026: NOT DONE, needs Wesley)

Grok Bot's built-in GitHub tools can't create repositories, push files, or change Pages settings, so these steps are manual:

1. Create an **empty public** repo `Funnyfarm4/curbside-rules` at https://github.com/new. Don't add a README, license or .gitignore. Suggested description: "Bulk trash and junk disposal rules by US city, from official sources."
2. Push the local repo. `/workspace/bulk-trash-site` is already a git repo with everything committed on `main`:
   ```
   cd /workspace/bulk-trash-site
   git remote add origin https://github.com/Funnyfarm4/curbside-rules.git
   git push -u origin main
   ```
   This needs a git login on the box (for example `gh auth login`, done by Wesley) or a cloud agent with access to the repo.
3. Turn on Pages. In repo **Settings > Pages**, set Source = "Deploy from a branch", Branch = `main`, Folder = `/docs`, then Save. `docs/.nojekyll` is already committed.
4. Wait 1-10 minutes, then verify:
   ```
   for u in "" boston/mattress/ style.css sitemap.xml; do
     curl -s -o /dev/null -w "%{http_code} https://funnyfarm4.github.io/curbside-rules/$u\n" "https://funnyfarm4.github.io/curbside-rules/$u"; done
   ```
   All four should return 200.
5. Optionally grant the repo to Cursor's GitHub App (https://github.com/apps/cursor/installations/new) so Grok Bot can read the repo, commits and Pages build checks.

### Every night after setup

```
python3 build.py && python3 scripts/check.py      # must print "All checks passed."
git add -A
git commit -m "Add <City> <item> guide"
git push origin main                               # Pages redeploys docs/ automatically in ~1-2 min
```
Then curl the new page's live URL (step 4 pattern) and confirm 200.

### Moving to a custom domain later

Set `base_path` to `/` and `base_url` to `https://www.<domain>` in `site.config.json`, add `docs/CNAME` containing the domain (add it to `static/` so the build copies it), rebuild, and push. Then set the custom domain in Settings > Pages. Note that `robots.txt` only takes effect at a domain root, so it does nothing on the github.io sub-path but will work on a custom domain.

### Netlify alternative

`netlify.toml` publishes `docs/`. For Netlify, set `base_path` to `/` and `base_url` to the Netlify URL first.

## Affiliate links

Every affiliate link is rendered with `data-affiliate="<key>"` and `rel="sponsored nofollow noopener"`. To switch on tracking after joining a program, paste the tracking link into `affiliates.<key>.tracking_url` in `site.config.json` and rebuild. Every page updates at once. To add a partner, add a new key with `name`, `url`, `tracking_url` and `blurb`.

## Re-checking old pages

When you re-verify a page, update `last_checked` (and each source's `checked`), and `updated` if anything changed. The sitemap `lastmod` follows `updated`.
