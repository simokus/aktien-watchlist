"""Täglicher Kennzahlen-Score-Job. Liest watchlists.json, holt Daten via yfinance
(oder FMP falls FMP_API_KEY gesetzt), berechnet Scores via scoring.py, schreibt data.json.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yfinance as yf

import scoring

ROOT = Path(__file__).resolve().parent.parent
WATCHLISTS_PATH = ROOT / "watchlists.json"
DATA_PATH = ROOT / "data.json"

USER_AGENT = "Mozilla/5.0 (compatible; AktienScreenerBot/1.0; +https://github.com)"


def load_watchlists() -> dict:
    with open(WATCHLISTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def collect_tickers(watchlists: dict) -> dict[str, str]:
    """Ticker -> Profil. Bei Mehrfachvorkommen in versch. Watchlists gewinnt die erste."""
    ticker_profile: dict[str, str] = {}
    for wl in watchlists.get("watchlists", []):
        profile = wl.get("profile", "largecap")
        for ticker in wl.get("tickers", []):
            ticker_profile.setdefault(ticker, profile)
    return ticker_profile


def fetch_yfinance(ticker: str, session: requests.Session) -> dict:
    t = yf.Ticker(ticker, session=session)
    info = t.info
    if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
        raise ValueError(f"Keine Kursdaten für {ticker}")
    return info


def fetch_fmp(ticker: str, api_key: str) -> dict:
    """Best-effort FMP-Mapping auf yfinance-Feldnamen. Nicht abgedeckte Felder bleiben None."""
    base = "https://financialmodelingprep.com/api/v3"
    quote = requests.get(f"{base}/quote/{ticker}", params={"apikey": api_key}, timeout=15).json()
    profile = requests.get(f"{base}/profile/{ticker}", params={"apikey": api_key}, timeout=15).json()
    q = quote[0] if quote else {}
    p = profile[0] if profile else {}
    if q.get("price") is None:
        raise ValueError(f"Keine FMP-Kursdaten für {ticker}")

    metrics = {}
    try:
        km = requests.get(f"{base}/key-metrics-ttm/{ticker}", params={"apikey": api_key}, timeout=15).json()
        ratios = requests.get(f"{base}/ratios-ttm/{ticker}", params={"apikey": api_key}, timeout=15).json()
        metrics = {**(km[0] if km else {}), **(ratios[0] if ratios else {})}
    except Exception:
        pass

    return {
        "currentPrice": q.get("price"),
        "regularMarketPrice": q.get("price"),
        "previousClose": q.get("previousClose"),
        "currency": p.get("currency"),
        "shortName": p.get("companyName"),
        "longName": p.get("companyName"),
        "marketCap": q.get("marketCap"),
        "sector": p.get("sector"),
        "industry": p.get("industry"),
        "longBusinessSummary": p.get("description"),
        "trailingPE": q.get("pe"),
        "forwardPE": None,
        "pegRatio": metrics.get("peRatioTTM") and metrics.get("priceEarningsToGrowthRatioTTM"),
        "priceToBook": metrics.get("pbRatioTTM"),
        "enterpriseToEbitda": metrics.get("evToEbitdaTTM") or metrics.get("enterpriseValueOverEBITDATTM"),
        "returnOnEquity": metrics.get("roeTTM"),
        "grossMargins": metrics.get("grossProfitMarginTTM"),
        "operatingMargins": metrics.get("operatingProfitMarginTTM"),
        "profitMargins": metrics.get("netProfitMarginTTM"),
        "ebitdaMargins": metrics.get("ebitdaMarginTTM"),
        "freeCashflow": metrics.get("freeCashFlowPerShareTTM") and q.get("sharesOutstanding")
        and metrics.get("freeCashFlowPerShareTTM") * q.get("sharesOutstanding"),
        "totalRevenue": None,
        "totalDebt": None,
        "totalCash": None,
        "sharesOutstanding": q.get("sharesOutstanding"),
        "revenueGrowth": None,
        "earningsGrowth": None,
        "forwardEps": q.get("eps"),
        "beta": p.get("beta"),
        "fiftyTwoWeekHigh": q.get("yearHigh"),
        "fiftyTwoWeekLow": q.get("yearLow"),
        "targetMeanPrice": None,
        "numberOfAnalystOpinions": None,
        "recommendationKey": None,
        "dividendYield": None,
    }


def build_stock_entry(ticker: str, profile: str, raw: dict, now_iso: str) -> dict:
    result = scoring.compute_score(raw, profile)
    m = result["metrics"]

    price_time = now_iso
    try:
        ts = raw.get("regularMarketTime")
        if ts:
            price_time = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        pass

    return {
        "ticker": ticker,
        "name": m.get("name") or ticker,
        "currency": m.get("currency"),
        "price": m.get("price"),
        "previousClose": m.get("previousClose"),
        "changePct": round(m["changePct"], 2) if m.get("changePct") is not None else None,
        "marketCap": m.get("marketCap"),
        "sector": m.get("sector"),
        "industry": m.get("industry"),
        "summary": (m.get("summary") or "")[:300],
        "profileUsed": profile,
        "metrics": {
            "pe": m.get("pe"), "fwdPe": m.get("fwdPe"), "peg": m.get("peg"), "pb": m.get("pb"),
            "evEbitda": m.get("evEbitda"), "fcfYield": m.get("fcfYield"), "roe": m.get("roe"),
            "grossMargin": m.get("grossMargin"), "opMargin": m.get("opMargin"),
            "netDebtEbitda": m.get("netDebtEbitda"), "revGrowth": m.get("revGrowth"),
            "earnGrowth": m.get("earnGrowth"), "beta": m.get("beta"),
            "week52High": m.get("week52High"), "week52Low": m.get("week52Low"),
            "targetMean": m.get("targetMean"), "analystCount": m.get("analystCount"),
            "recommendationKey": m.get("recommendationKey"), "dividendYield": m.get("dividendYield"),
        },
        "score": result["score"],
        "scoreLabel": result["scoreLabel"],
        "subScores": result["subScores"],
        "fairValue": result["fairValue"],
        "conservativeFairValue": result["conservativeFairValue"],
        "safetyMarginPct": result["safetyMarginPct"],
        "buyZone": result["buyZone"],
        "sellThreshold": result["sellThreshold"],
        "verdict": result["verdict"],
        "dataFlags": result["dataFlags"],
        "stale": False,
        "priceTime": price_time,
    }


def main() -> None:
    watchlists = load_watchlists()
    ticker_profile = collect_tickers(watchlists)

    previous_data = {}
    if DATA_PATH.exists():
        try:
            previous_data = json.loads(DATA_PATH.read_text(encoding="utf-8")).get("stocks", {})
        except Exception:
            previous_data = {}

    fmp_key = os.environ.get("FMP_API_KEY", "").strip()
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    now_zurich = datetime.now(ZoneInfo("Europe/Zurich"))
    now_iso = now_zurich.isoformat()

    stocks: dict[str, dict] = {}
    for ticker, profile in ticker_profile.items():
        try:
            if fmp_key:
                try:
                    raw = fetch_fmp(ticker, fmp_key)
                except Exception as fmp_err:
                    print(f"[{ticker}] FMP fehlgeschlagen ({fmp_err}), Fallback yfinance", file=sys.stderr)
                    raw = fetch_yfinance(ticker, session)
            else:
                raw = fetch_yfinance(ticker, session)

            entry = build_stock_entry(ticker, profile, raw, now_iso)
            stocks[ticker] = entry
            print(f"[{ticker}] Score {entry['score']} ({entry['verdict']})")
        except Exception as e:
            print(f"[{ticker}] Fehler: {e}", file=sys.stderr)
            if ticker in previous_data:
                stale_entry = dict(previous_data[ticker])
                stale_entry["stale"] = True
                flags = list(stale_entry.get("dataFlags", []))
                flags.append("Aktualisierung fehlgeschlagen, letzte bekannte Daten")
                stale_entry["dataFlags"] = flags
                stocks[ticker] = stale_entry
            else:
                print(f"[{ticker}] Kein vorheriger Datensatz, Ticker wird ausgelassen", file=sys.stderr)

        time.sleep(0.6)

    output = {
        "lastUpdated": now_iso,
        "source": "fmp" if fmp_key else "yfinance",
        "stocks": stocks,
    }
    DATA_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"data.json geschrieben mit {len(stocks)} Tickern")


if __name__ == "__main__":
    main()
