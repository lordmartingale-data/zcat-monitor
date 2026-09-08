# ZCAT pool volume monitor

Tracks hourly trading volume across the ZCAT liquidity pools on Solana and
publishes a dashboard to GitHub Pages. No server, no database, no cost — a
scheduled GitHub Action fetches a snapshot each hour and commits it to
`data/history.json`, which the page reads directly.

Mint: `HcRLc9VDgjLeK154xDawfb1dmVJ98DoSqcwTHGqiDeJR`

## Setup

### 1. Create the repository

On the web: click the **+** in the top-right of github.com → **New repository**.
Give it a name (`zcat-pool-monitor`), leave it **Public** (Pages on private repos
needs a paid plan), and don't add a README or `.gitignore` — this folder already
has what it needs. Click **Create repository**.

Then, from inside this folder:

```bash
git init
git add .
git commit -m "ZCAT pool volume monitor"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/zcat-pool-monitor.git
git push -u origin main
```

If you'd rather not touch the command line, the new empty repo page has an
**uploading an existing file** link — drag this whole folder onto it. The one
catch is that browsers don't upload dotfiles reliably, so check that
`.github/workflows/collect.yml` actually arrived; if it didn't, use
**Add file → Create new file**, type `.github/workflows/collect.yml` as the
name, and paste the contents in.

With the `gh` CLI it's a one-liner instead:

```bash
gh repo create zcat-pool-monitor --public --source=. --push
```

### 2. Allow the workflow to commit

**Settings → Actions → General → Workflow permissions** → select
**Read and write permissions** → Save. Without this the hourly run fetches data
fine but fails at the push step.

### 3. Turn on Pages

**Settings → Pages → Source: Deploy from a branch**, branch `main`, folder
`/ (root)`. Save. The dashboard appears at
`https://YOUR-USERNAME.github.io/zcat-pool-monitor/` within a minute or two.

### 4. Seed the first snapshot

**Actions → Collect pool volume → Run workflow.** The dashboard needs at least
one snapshot before it shows anything, and this saves you waiting for the top of
the hour. The first-ever run in a new repo may need you to click
**I understand my workflows, go ahead and enable them** on the Actions tab.

## How it works

`scripts/collect.py` hits the DexScreener token endpoint, keeps the Solana pools,
and records four numbers per pool: 1h volume, 24h volume, liquidity, and price.
The workflow runs it at 17 past each hour and commits the result only if
something changed.

### The $900K threshold

A pool joins the tracked set the first time its 24h volume clears $900,000, and
is then recorded permanently. Applying the filter fresh each hour instead would
mean pools dropping in and out of the chart as they cross the line, leaving gaps
in the series and making decline — the thing worth watching — hardest to see
exactly when it's happening. Change `VOLUME_THRESHOLD` in `scripts/collect.py`
to adjust; to drop a pool entirely, delete its entry from the `pools` object in
`data/history.json`.

### 1h volume, not 24h

The dashboard's charts use `v1`, the trailing one-hour figure. Sampling a
trailing *24h* number every hour gives consecutive readings that share 23 hours
of data, so the line looks smooth and lags real changes by most of a day. The
24h column is kept in the table for context and for comparison against
DexScreener.

## Things to know

**The schedule is best-effort.** GitHub runs scheduled workflows on a shared
queue and delays them under load; runs can slip by 10–30 minutes or be dropped
entirely at busy times. This is fine for a trend chart but don't treat a missing
hour as a signal about the market.

**Scheduled workflows switch off after 60 days without repo activity.** GitHub
emails you first. The hourly commits from the collector itself do *not* count as
activity for this purpose. If the data goes stale, check the Actions tab first.

**Turnover in the table is 24h volume ÷ liquidity.** On a pool with $50K of
liquidity doing $1.5M a day, that ratio is doing a lot of work — it's telling
you the pool is being cycled hard, not that it's deep.

**Volume figures include the 3% transfer tax.** Every ZCAT trade is taxed at the
mint level, so reported notional and the amount actually changing hands differ
by that much. Treat cross-pool volume comparisons as directional.
