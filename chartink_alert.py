"""
Chartink Screener -> Telegram Alert Bot
----------------------------------------
Multiple Chartink screeners check karto, results Telegram var pathvto.
Ekach stock ekach divsat FAKT EKDA alert hoto (daily reset cache) —
kal ala asel to stock aaj parat aala tar aajparynt navin mhanunach alert jail.

Env variables lagतात (GitHub Secrets madhun yetat):
    TELEGRAM_TOKEN
    TELEGRAM_CHAT_ID
"""

import os
import re
import json
import requests
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

# ---- Config: tumche 6 screeners (URL madhla shevatcha slug) ----
SCREENERS = [
    "break-down-swing-trading-screener-backtest-4-6",
    "copy-btst-1-day-ago-high-breakout-screener-201",
    "downtrend-with-good-volume-futures",
    "perfect-bearish-varad-2",
    "varad-bullish",
    "bearish-super-new",
]

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

CACHE_FILE = "seen_stocks.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=20,
    )
    if not resp.ok:
        print("Telegram send failed:", resp.text)


def today_str():
    return datetime.now(IST).strftime("%Y-%m-%d")


def load_cache():
    """Cache asa asto: {"date": "YYYY-MM-DD", "screeners": {slug: [symbols...]}}
    Jar cache madhla date aajcha nasel, tar to purna reset hoto (navin divas = navin start)."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)
        if cache.get("date") != today_str():
            return {"date": today_str(), "screeners": {}}
        return cache
    return {"date": today_str(), "screeners": {}}


def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)


def fetch_screener(slug: str):
    """Ek screener che live results ghete (list of dict: symbol, name, close, per_chg)."""
    session = requests.Session()
    page = session.get(f"https://chartink.com/screener/{slug}", headers=HEADERS, timeout=20)
    page.raise_for_status()
    html = page.text

    csrf_match = re.search(r'name="csrf-token" content="([^"]+)"', html)
    scan_match = re.search(r'"scan_clause":"(.*?)"\}', html)

    if not csrf_match or not scan_match:
        print(f"[{slug}] scan_clause / csrf-token sapadla nahi, screener page format badalla asel.")
        return []

    csrf_token = csrf_match.group(1)
    scan_clause = scan_match.group(1).encode().decode("unicode_escape")

    post_headers = dict(HEADERS)
    post_headers["x-csrf-token"] = csrf_token

    result = session.post(
        "https://chartink.com/screener/process",
        headers=post_headers,
        data={"scan_clause": scan_clause},
        timeout=20,
    )
    result.raise_for_status()
    data = result.json().get("data", [])

    return [
        {
            "symbol": row.get("nsecode", row.get("bsecode", "")),
            "name": row.get("name", ""),
            "close": row.get("close", ""),
            "chg": row.get("per_chg", ""),
        }
        for row in data
    ]


def main():
    cache = load_cache()
    any_alert = False

    for slug in SCREENERS:
        try:
            stocks = fetch_screener(slug)
        except Exception as e:
            print(f"[{slug}] error: {e}")
            continue

        seen_today = set(cache["screeners"].get(slug, []))
        new_stocks = [s for s in stocks if s["symbol"] not in seen_today]

        if new_stocks:
            any_alert = True
            lines = [f"<b>📢 {slug}</b>", ""]
            for s in new_stocks:
                lines.append(f"• <b>{s['symbol']}</b> — {s['name']} | ₹{s['close']} ({s['chg']}%)")
            send_telegram("\n".join(lines))
            print(f"[{slug}] {len(new_stocks)} navin stock(s) pathavle.")
        else:
            print(f"[{slug}] navin stock nahi (aajparynt alert zalele).")

        # aaj alert zalele sagle symbols cache madhe add karto (jene karun tyach divsat parat alert jaणar nahi)
        seen_today.update(s["symbol"] for s in new_stocks)
        cache["screeners"][slug] = list(seen_today)

    save_cache(cache)

    if not any_alert:
        print("Kontyahi screener madhe navin stock nahi ya run madhe.")


if __name__ == "__main__":
    main()
