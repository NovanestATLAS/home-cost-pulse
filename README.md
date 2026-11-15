# Home Cost Pulse

Official U.S. electricity prices for every state, refreshed automatically from the U.S. Energy Information
Administration (EIA), plus ten home cost calculators (energy and building projects). Static site: no
server, no database, free hosting. Python and Node.js standard libraries only (matplotlib is optional).

* 51 state pages (50 states + D.C.) with price, 36-month trend, average usage and bill, everyday costs, solar output
* A sortable all-states table and a monthly report for each new EIA month
* 10 calculators: electric bill, appliance cost, EV charging, solar payback, concrete, gravel/mulch,
  paint, drywall, flooring/tile, roofing (feet or meters). The project tools turn quantities into a material
  cost when the visitor types a local price; the site never guesses prices.
* A "Can you choose your supplier?" section on the 14 state pages where homes can, linking to the state
  regulator's own comparison site (`data/electric_choice.json`)
* About, methodology, privacy, terms and contact pages (needed for ad network approval)
* sitemap.xml, robots.txt, ads.txt, IndexNow key, Open Graph images and Pinterest pins

## How the automation works

Every Monday GitHub Actions runs `.github/workflows/update-and-deploy.yml`:

1. `fetch_eia.py` asks the EIA API for the latest months. If nothing changed, nothing is written.
2. `fetch_pvwatts.py` refreshes solar output once a year.
3. `validate_data.py` checks every number. **If anything looks wrong the run stops** and the live site keeps the last good version.
4. New data is committed to the repository (this also keeps GitHub's scheduled runs active).
5. Tests run (`tests/`), the site is built (`build_site.py`), and every internal link is checked (`check_links.py`).
6. The site is published to GitHub Pages (or Cloudflare Pages), then Bing and other IndexNow engines are told which pages changed.

EIA publishes a new month roughly 8 weeks after it ends (for example, August 2026 data came out on October 23, 2026).

## Files

| Path | What it does |
|---|---|
| `site.config.json` | Site name, address, contact form key, ad code, analytics, verification codes |
| `data/states_meta.json` | 51 jurisdictions with slug, region and the city used for solar |
| `data/electric_choice.json` | States with supplier choice and each regulator's official site (review once a year) |
| `data/seed/eia_seed_2026-07.json` | Real EIA numbers used until your EIA key is added |
| `data/eia_residential_monthly.json` | Written by `fetch_eia.py` (committed by the workflow) |
| `data/solar_pvwatts.json` | Written by `fetch_pvwatts.py` |
| `content/calculators.json` | Calculator fields, texts, tips and questions |
| `assets/calc-core.js` | All calculator math (browser + worked examples use the same file) |
| `assets/site.js`, `assets/style.css` | Page behaviour and design |
| `scripts/build_site.py` | Builds everything into `dist/` |
| `scripts/summaries.py` | Turns raw data into per-state numbers |
| `scripts/share_images.py` | Open Graph images and Pinterest pins (needs matplotlib) |
| `scripts/check_links.py` | Fails the build on any broken internal link |
| `scripts/indexnow_ping.py` | Notifies IndexNow after a data update |
| `tests/` | `python -m unittest discover -s tests` and `node --test tests/calc.test.js` |
| `colab/test_api_keys.ipynb` | Test your two API keys in Google Colab before adding them to GitHub |
| `PROMPTS.md` | Copy-paste prompts for Antigravity, Claude, NotebookLM, Colab and Flow |

## Run it on your Windows PC (optional)

Install Python 3.12 (tick "Add python.exe to PATH") and Node.js 22 LTS, then in the project folder:

```
python scripts\build_site.py
python -m http.server 8000 -d dist
```

Open http://localhost:8000. Run the tests with `python -m unittest discover -s tests` and `node --test tests\calc.test.js`.

## Put it online

1. **Free API keys.** EIA: https://www.eia.gov/opendata/register.php (key arrives by email).
   NLR PVWatts: https://developer.nlr.gov/signup/ (key shown on screen and emailed). The old developer.nrel.gov address stopped working on May 29, 2026; old keys still work on the new address.
2. **Test the keys** (optional): open `colab/test_api_keys.ipynb` in Google Colab and run it.
3. **Create a GitHub repository** named `home-cost-pulse` (public is fine) and upload every file in this folder,
   including the hidden `.github` folder. Or ask Antigravity to do it with prompt 1 in `PROMPTS.md`.
4. **Add the keys as secrets:** Settings > Secrets and variables > Actions > New repository secret:
   `EIA_API_KEY` and `NLR_API_KEY`.
5. **Turn on GitHub Pages:** Settings > Pages > Build and deployment > Source: **GitHub Actions**.
6. **Run it:** Actions > Update data and deploy > Run workflow. Tick "Refresh the PVWatts solar data now" the first time.
   About 3 minutes later your site is live at `https://<your-user>.github.io/home-cost-pulse/`.

## Your own domain and hosting

`homecostpulse.com` was available for $9.08 at Spaceship on October 24, 2026. After buying a domain, set
`site_url` in `site.config.json` to `https://yourdomain.com`.

**GitHub Pages (quick start).** Settings > Pages > Custom domain. At your registrar add four A records for the
bare domain: `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`, and a CNAME record
`www` pointing to `<your-user>.github.io`. Tick "Enforce HTTPS" once it is offered.

**Cloudflare Pages (recommended before you add ads).** GitHub's terms say Pages is not meant to host an online
business; Cloudflare's free plan allows commercial sites and has no bandwidth cap.
1. Cloudflare dashboard > Workers & Pages > Create > Pages > Connect to Git > pick the repository.
2. Build command: `pip install matplotlib && python3 scripts/build_site.py`. Build output directory: `dist`.
3. Add your domain under Custom domains (move the domain's nameservers to Cloudflare when asked).
4. In GitHub add a repository variable `DEPLOY_TARGET` = `cloudflare` (Settings > Secrets and variables > Actions > Variables).
   The weekly workflow keeps fetching and committing data; each data commit triggers a Cloudflare rebuild.
5. Free email at your domain: Cloudflare > Email > Email Routing, forward `hello@yourdomain.com` to your Gmail.

## Contact form

The contact page uses a Web3Forms form (`contact_form.web3forms_access_key` in `site.config.json`), so no email
address appears anywhere on the site. Messages arrive in the inbox the key belongs to. Create a separate key at
https://web3forms.com if you want this site's messages kept apart from your other sites.

## Search engines

* Google Search Console: add the domain, paste the HTML-tag code into `google_site_verification`, submit `/sitemap.xml`.
* Bing Webmaster Tools: import from Search Console, or paste its code into `bing_site_verification`.
* IndexNow pings run automatically after each data update (key already in `site.config.json`).

## Partner (affiliate) links

Lead-generation links usually pay more per visitor than display ads, and they do not need a traffic minimum.
The buttons are built in and stay hidden until you paste a link into `partners` in `site.config.json`:

* `solar_quotes`: under the solar payback result and in each state's solar section.
* `electricity_plans`: in the supplier-choice section of the 14 state pages. `state_urls` sets a different link
  for one state, for example `{"TX": "https://..."}`.
* `contractor_quotes`: under the result of the roofing, flooring, drywall, concrete and paint calculators.

Every button is marked `rel="sponsored nofollow"` and shows the disclosure line, and the About page then says the
site uses partner links. Apply to a program first (most want a live site with real content, which you now have),
then paste the tracking link they give you. Checked on November 15, 2026: EnergySage pays $9.60 per approved solar
lead through FlexOffers; Angi pays 10% of completed service through Impact; ComparePower (Texas) and
ElectricityRates.com run affiliate programs with rates shown after approval; Choose Energy / SaveOnEnergy take
partners by email and ask for your traffic volume.

## Ads

Paste the code your network gives you into `site.config.json`:

After editing texts or calculators, set `content_updated` in `site.config.json` to that day's date: it is the
sitemap date for pages that do not depend on EIA data.

* `ads.head_html`: the script tag that goes in `<head>` (Monetag, AdSense, or Journey/Grow).
* `ads.slots.top / in_content / bottom`: optional manual placements.
* `ads.ads_txt_lines`: the exact lines the network gives you for ads.txt.

Recommended order: **no ads at first.** Below about 1,000 visits a month any network pays a few dollars while
its scripts slow the pages, and AdSense does not allow pop-ups or pop-unders that interfere with navigation.

* Day 4: connect Google Analytics 4 (`analytics.ga4_id`). Mediavine's application reads your traffic from it.
* Grow by Mediavine has been optional since August 2026, but it is free and shows no ads, so paste its script into
  `ads.head_html` anyway.
* Journey by Mediavine needs about 1,000 premium sessions a month (U.S., UK, Canada, Australia), and its guide asks
  for at least 4 months of domain history. AdSense is the fallback.
* Later, Raptive at 25,000 pageviews a month.

## Troubleshooting

* **Run failed at "Check the data":** read the DATA ERROR lines. Usually an EIA outage or revision; re-run later.
* **Warning "EIA_API_KEY is not set":** the secret name must match exactly.
* **Scheduled runs stopped:** GitHub pauses schedules in repos with no activity for 60 days. Any commit restarts them.
* **Page looks unstyled under github.io:** run the workflow again; it reads the Pages address automatically.
* **A GitHub "Node.js version" notice on an action:** ask Antigravity to update the action versions in the workflow.

Data: U.S. Energy Information Administration (public domain, https://www.eia.gov/about/copyrights_reuse.php).
Solar: PVWatts v8, National Laboratory of the Rockies (formerly NREL).
