#!/usr/bin/env python3
"""Collect ZCAT pool volume from DexScreener and append an hourly snapshot.

Writes data/history.json. Designed to be idempotent and safe to re-run:
if a snapshot for the current hour already exists it is overwritten rather
than duplicated, so a retried workflow run doesn't double-count.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

MINT = "HcRLc9VDgjLeK154xDawfb1dmVJ98DoSqcwTHGqiDeJR"
ENDPOINT = f"https://api.dexscreener.com/latest/dex/tokens/{MINT}"

# A pool joins the tracked set the first time its 24h volume crosses this.
# Once it has joined it keeps being recorded, so the time series stays
# continuous instead of gapping out on a quiet hour.
VOLUME_THRESHOLD = 900_000

# 30 days of hourly points.
MAX_SNAPSHOTS = 720

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_PATH = os.path.join(ROOT, "data", "history.json")


def fetch():
    req = urllib.request.Request(
        ENDPOINT,
        headers={"User-Agent": "zcat-pool-monitor (github actions)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            raise RuntimeError(f"DexScreener returned HTTP {resp.status}")
        return json.load(resp)


def load_history():
    if not os.path.exists(HISTORY_PATH):
        return {"mint": MINT, "threshold": VOLUME_THRESHOLD, "pools": {}, "snapshots": []}
    with open(HISTORY_PATH) as f:
        return json.load(f)


def num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def main():
    payload = fetch()
    pairs = payload.get("pairs") or []
    if not pairs:
        print("No pairs returned; leaving history untouched.", file=sys.stderr)
        return 1

    history = load_history()
    pools = history.setdefault("pools", {})
    snapshots = history.setdefault("snapshots", [])

    stamp = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    stamp_iso = stamp.isoformat().replace("+00:00", "Z")

    # The collector runs several times an hour so a dropped GitHub run doesn't
    # cost a data point. The first success in an hour is kept and later
    # attempts do nothing, which keeps every reading's 1h window at a
    # consistent offset instead of wandering with retry timing.
    force = os.environ.get("FORCE_REFRESH") == "1"
    if not force and any(s.get("t") == stamp_iso for s in snapshots):
        print(f"{stamp_iso}: already captured this hour, nothing to do.")
        return 0

    reading = {}
    for pair in pairs:
        # The mint is Solana-native, but guard anyway so an unrelated
        # same-ticker listing on another chain can never enter the data.
        if pair.get("chainId") != "solana":
            continue

        addr = pair.get("pairAddress")
        if not addr:
            continue

        vol_24h = num((pair.get("volume") or {}).get("h24"))
        vol_1h = num((pair.get("volume") or {}).get("h1"))
        liquidity = num((pair.get("liquidity") or {}).get("usd"))
        price = num(pair.get("priceUsd"))

        # An hour sits inside its own day, so a 1h figure above the 24h
        # figure can only be a feed error. Large-but-consistent spikes are
        # left alone: violent hours are real and are the point of this chart.
        if vol_24h > 0 and vol_1h > vol_24h * 1.05:
            print(f"  dropped impossible 1h reading for {addr}: "
                  f"{vol_1h:,.0f} > 24h {vol_24h:,.0f}", file=sys.stderr)
            vol_1h = -1.0

        known = pools.get(addr)
        qualifies = vol_24h >= VOLUME_THRESHOLD

        if known is None:
            if not qualifies:
                continue  # never met the bar, don't start tracking it
            pools[addr] = {
                "dex": pair.get("dexId", "unknown"),
                "labels": pair.get("labels") or [],
                "base": (pair.get("baseToken") or {}).get("symbol", "?"),
                "quote": (pair.get("quoteToken") or {}).get("symbol", "?"),
                "url": pair.get("url", ""),
                "firstSeen": stamp_iso,
            }

        reading[addr] = {
            # -1 marks "no valid reading this hour" and is skipped by the page.
            "v1": round(vol_1h, 2) if vol_1h >= 0 else -1,
            "v24": round(vol_24h, 2),
            "liq": round(liquidity, 2),
            "px": price,
        }

    if not reading:
        print("No pool cleared the threshold; leaving history untouched.", file=sys.stderr)
        return 1

    snapshot = {"t": stamp_iso, "pools": reading}

    # Replace an existing snapshot for this hour rather than appending twice.
    snapshots = [s for s in snapshots if s.get("t") != stamp_iso]
    snapshots.append(snapshot)
    snapshots.sort(key=lambda s: s["t"])
    history["snapshots"] = snapshots[-MAX_SNAPSHOTS:]
    history["updated"] = stamp_iso
    history["threshold"] = VOLUME_THRESHOLD
    history["mint"] = MINT

    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=1, sort_keys=True)
        f.write("\n")

    total = sum(r["v24"] for r in reading.values())
    print(f"{stamp_iso}: {len(reading)} pools, ${total:,.0f} combined 24h volume")
    return 0


if __name__ == "__main__":
    sys.exit(main())
