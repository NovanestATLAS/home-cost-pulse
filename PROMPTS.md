# Copy-paste prompts

Copy prompts from this file, not from the PDF: PDFs break line spacing and code indentation.

Ground rules that every prompt repeats, because they protect the site:
* Never invent numbers. Data comes from EIA, NLR or the user's input.
* All calculator math lives in `assets/calc-core.js` and is covered by `tests/calc.test.js`.
* Every change must pass `python -m unittest discover -s tests`, `node --test tests/calc.test.js`,
  `python scripts/build_site.py` and `python scripts/check_links.py`.
* No mass-produced thin pages. A new page must show real data or a working tool.

---

## 1. Antigravity: put the project on GitHub and publish it

```
You have access to my GitHub account and this local folder (home-cost-pulse).
1. Create a new public repository named home-cost-pulse and push every file in this folder,
   including the hidden .github folder, to the main branch.
2. Do not create or commit any API keys. I will add EIA_API_KEY and NLR_API_KEY as Actions secrets myself.
3. In the repository settings, set Pages > Build and deployment > Source to "GitHub Actions".
4. Trigger the workflow "Update data and deploy" with force_solar = true.
5. When it finishes, give me the live URL and a summary of each job's result. If a step fails,
   show me the exact error lines and propose a fix, but do not change the data validation limits.
```

## 2. Antigravity: port my Job Site Calc calculators

```
This repo is a static site generator (Python stdlib) for Home Cost Pulse. Calculators are defined in
content/calculators.json (fields, texts, FAQs) and their math lives ONLY in assets/calc-core.js
(function per calculator id returning {lines, total, extra, notes, raw}; inputs arrive in U.S. units;
use the units === 'metric' branch for display like the existing ones).

My Android app Job Site Calc (folder: <PATH TO MY CORDOVA PROJECT>/www) has more construction calculators.
Port these as new calculators, one at a time: <LIST, e.g. deck boards, fence posts, brick and block, stairs>.
For each one:
- add an entry in content/calculators.json with group "projects", plain-English intro, a "how" section
  that states the formula, 2 tips and 2 FAQs whose answers you verify by running the math;
- add the function in assets/calc-core.js;
- add at least one test in tests/calc.test.js with a hand-worked answer;
- run: node --test tests/calc.test.js, python -m unittest discover -s tests,
  python scripts/build_site.py, python scripts/check_links.py.
Do not change existing calculators or the page design. Show me the diff before committing.
```

## 3. Antigravity: heat pump vs gas furnace (natural gas prices from EIA)

```
Add residential natural gas prices by state from the EIA API v2 (route natural-gas/pri/sum, residential
price, monthly, by state; same EIA_API_KEY). First call the route without /data to read its facets and
units, and paste me the metadata before writing code. Then:
- scripts/fetch_eia_gas.py writing data/eia_gas_residential_monthly.json (same style as fetch_eia.py:
  no write when unchanged, atomic save);
- extend validate_data.py with sensible bounds;
- add the fetch to the workflow next to fetch_eia.py;
- new calculator "heat-pump-vs-furnace" in calculators.json + calc-core.js comparing yearly heating cost
  (inputs: heat needed in therms or BTU, furnace efficiency, heat pump COP, gas price, electricity price),
  with tests;
- show each state's gas price on its state page only if the data exists.
Keep the standard-library-only rule for Python.
```

## 4. Antigravity: utility pages from EIA-861 (top 200 utilities)

```
Add utility-level pages using EIA Form EIA-861 annual data (Sales to Ultimate Customers, residential:
revenue, sales, customers per utility). Download the latest annual zip from
https://www.eia.gov/electricity/data/eia861/ inside the workflow (yearly), parse it with openpyxl
(pip install in the workflow only), and keep only the 200 utilities with the most residential customers.
For each utility compute average price, monthly usage and monthly bill, and generate
/electricity-rates/<state>/<utility-slug>/ with: the numbers, comparison with the state and U.S. averages,
the bill calculator prefilled with the utility's price, and a clear note that the data year is <year>.
Link them from each state page. Add tests with a small fixture. Do not publish utilities with missing
or implausible values (reuse validate_data.py limits).
```

## 5. Antigravity: fix a failed workflow run

```
The GitHub Actions run "<paste the run URL>" failed. Read the logs, explain the cause in two sentences,
and fix it with the smallest change. Never loosen validate_data.py limits to make bad data pass;
if the data itself looks wrong, stop and tell me. Re-run the workflow and report the result.
```

## 6. Claude: review a page before it goes live

```
Here is the HTML of a page from my site (or its URL). Check it like a strict editor and a homeowner:
1) every number: is it consistent with the others on the page and plausible? 2) anything that could be
read as advice or a guarantee; 3) unclear wording a non-expert would trip on; 4) anything missing that
would make the page more useful than the top 3 Google results for "<target search>". Answer as a list of
fixes in priority order.
```

## 7. NotebookLM: project brain (paste as a "Copied text" source)

```
Project: Home Cost Pulse. A static website that publishes official U.S. electricity prices for 50 states
and D.C. (source: U.S. Energy Information Administration, monthly, public domain) and 10 calculators
(electric bill, appliance cost, EV charging, solar payback, concrete, gravel/mulch, paint, drywall,
flooring/tile, roofing). Audience: U.S. homeowners and renters (high-eCPM traffic); project calculators
also serve Canada, the UK and Australia (metric units).
Hosting: GitHub repository + GitHub Actions (weekly data check) + GitHub Pages or Cloudflare Pages.
Rules: no invented data; math only in assets/calc-core.js with tests; validation stops bad data;
no mass thin pages; the 30% federal solar credit (25D) ended Dec 31, 2025.
Goals: 1,000 premium sessions a month (Journey by Mediavine threshold; its guide also asks for a domain at least
4 months old, and the application reads Google Analytics, so GA4 stays connected and no ads before month 5),
then grow toward 1,000 a day.
AI answers take clicks from simple fact searches, so new pages should be tools, not facts.
Traffic plan: Pinterest pins (generated in dist/pins/), Reddit answers where allowed, monthly report
shared on social, Google and Bing through sitemap and IndexNow.
Each week I log: sessions, top pages, pins posted, new links, revenue.
```

Then ask NotebookLM each week: `Based on my notes, what is the single most valuable task for this week?`

## 8. Google Colab: test the keys

Open `colab/test_api_keys.ipynb` (File > Upload notebook in Colab) and run all cells.

## 9. Google Flow: a 20-second monthly video

```
Vertical 9:16 video, 20 seconds, clean infographic style, dark slate background (#1D2733), safety-yellow
accents (#F4C21B), large condensed numbers. Scene 1: "Electricity prices, <MONTH YEAR>". Scene 2: a
counter rolling to "<US PRICE>¢ per kWh, U.S. average". Scene 3: "Cheapest: <STATE> <PRICE>¢".
Scene 4: "Most expensive: <STATE> <PRICE>¢". Scene 5: "Biggest jump: <STATE> +<X>%".
End card: "Check your state: <yourdomain.com>". No people, no voice-over, captions on screen.
```

Take the numbers from the newest page under `/reports/`.

## 10. Pinterest pin text (one per state image in dist/pins/)

```
Title: What electricity costs in <STATE> (<MONTH YEAR>)
Description: <STATE> homes pay <PRICE>¢ per kWh, <X>% <below/above> the U.S. average. See what an AC,
space heater or EV costs to run, and estimate your own bill with a free calculator.
Link: https://<yourdomain.com>/electricity-rates/<state-slug>/
Board: Save money on electric bills
```
