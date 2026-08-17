"""Gemeinsame Scoring-Logik für den Aktien-Screener (largecap & smallcap Profile).

Reine Funktionen, kein Netzwerk-/Dateizugriff -- importierbar von update.py und deep_analysis.py.
"""
from __future__ import annotations

SCORE_LABELS = [
    (80, 100, "Stark positiv"),
    (65, 79, "Positiv"),
    (45, 64, "Neutral"),
    (30, 44, "Zurückhaltend"),
    (0, 29, "Negativ"),
]


def score_label(score: float) -> str:
    for lo, hi, label in SCORE_LABELS:
        if lo <= score <= hi:
            return label
    return "Neutral"


def lin(x, worst, best) -> float | None:
    """Lineare Skalierung auf 0-100, geclamped. worst>best => invertiert automatisch."""
    if x is None:
        return None
    if worst == best:
        return 50.0
    t = (x - worst) / (best - worst)
    return max(0.0, min(100.0, t * 100.0))


def _avg(scores: list[float]) -> float | None:
    vals = [s for s in scores if s is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _setup_score(price, low, high) -> float | None:
    """Position im 52W-Range: Plateau (100) bei 5-35% der Range über dem Tief, sonst abfallend."""
    if price is None or low is None or high is None or high <= low:
        return None
    pos = (price - low) / (high - low)
    pos = max(0.0, min(1.0, pos))
    if pos < 0.05:
        return lin(pos, 0.0, 0.05)
    if pos <= 0.35:
        return 100.0
    return lin(pos, 1.0, 0.35)


def compute_derived_metrics(raw: dict) -> dict:
    """Erwartet ein dict mit den yfinance-Feldnamen (best effort, alle optional)."""
    g = raw.get

    price = g("currentPrice") or g("regularMarketPrice")
    previous_close = g("previousClose")
    change_pct = None
    if price is not None and previous_close:
        change_pct = (price - previous_close) / previous_close * 100

    market_cap = g("marketCap")
    fcf = g("freeCashflow")
    revenue = g("totalRevenue")
    ebitda_margin = g("ebitdaMargins")
    ebitda = revenue * ebitda_margin if revenue is not None and ebitda_margin is not None else None
    total_debt = g("totalDebt")
    total_cash = g("totalCash")
    net_debt = (total_debt - total_cash) if total_debt is not None and total_cash is not None else None

    fwd_pe = g("forwardPE")
    earn_growth = g("earningsGrowth")
    peg = g("pegRatio")
    if peg is None and fwd_pe is not None and earn_growth and earn_growth > 0:
        peg = fwd_pe / (earn_growth * 100)

    fcf_yield = fcf / market_cap if fcf is not None and market_cap else None
    fcf_margin = fcf / revenue if fcf is not None and revenue else None
    net_debt_ebitda = net_debt / ebitda if net_debt is not None and ebitda else None
    cash_cover = (total_cash / total_debt) if total_debt else None

    target_mean = g("targetMeanPrice")
    upside = None
    if target_mean is not None and price:
        upside = (target_mean - price) / price

    return {
        "price": price,
        "previousClose": previous_close,
        "changePct": change_pct,
        "currency": g("currency"),
        "name": g("shortName") or g("longName"),
        "marketCap": market_cap,
        "sector": g("sector"),
        "industry": g("industry"),
        "summary": g("longBusinessSummary"),
        "pe": g("trailingPE"),
        "fwdPe": fwd_pe,
        "peg": peg,
        "pb": g("priceToBook"),
        "evEbitda": g("enterpriseToEbitda"),
        "fcf": fcf,
        "fcfYield": fcf_yield,
        "fcfMargin": fcf_margin,
        "roe": g("returnOnEquity"),
        "grossMargin": g("grossMargins"),
        "opMargin": g("operatingMargins"),
        "netDebtEbitda": net_debt_ebitda,
        "cashCover": cash_cover,
        "revGrowth": g("revenueGrowth"),
        "earnGrowth": earn_growth,
        "beta": g("beta"),
        "week52High": g("fiftyTwoWeekHigh"),
        "week52Low": g("fiftyTwoWeekLow"),
        "targetMean": target_mean,
        "upside": upside,
        "analystCount": g("numberOfAnalystOpinions"),
        "recommendationKey": g("recommendationKey"),
        "dividendYield": g("dividendYield"),
        "forwardEps": g("forwardEps"),
        "sharesOutstanding": g("sharesOutstanding"),
    }


REC_SCORES = {
    "strong_buy": 100, "buy": 80, "outperform": 75,
    "hold": 50, "underperform": 30, "sell": 20, "strong_sell": 0,
}


def _analyst_category(m: dict) -> tuple[float | None, dict]:
    rec_key = m.get("recommendationKey")
    rec_score = REC_SCORES.get(rec_key)
    upside_score = lin(m.get("upside"), -0.10, 0.40)
    parts = [s for s in (rec_score, upside_score) if s is not None]
    if not parts:
        return None, {}
    if rec_score is not None and upside_score is not None:
        score = 0.6 * rec_score + 0.4 * upside_score
    else:
        score = parts[0]
    return score, {"recommendation": rec_score, "upside": upside_score}


LARGECAP_WEIGHTS_BASE = {
    "Qualität/Moat": 0.30, "Bewertung": 0.25, "Wachstum": 0.15,
    "Bilanz": 0.15, "Analysten": 0.15,
}
SMALLCAP_WEIGHTS_BASE = {
    "Qualität/Burggraben": 0.30, "Bilanz / Überlebensfähigkeit": 0.25,
    "Bewertungsabschlag": 0.30, "Setup/Stabilisierung": 0.15,
}


def _renormalize(weights: dict) -> dict:
    total = sum(weights.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in weights.items()}


def _score_largecap(m: dict) -> tuple[dict, dict, list[str]]:
    flags = []
    categories = {
        "Qualität/Moat": _avg([
            lin(m.get("roe"), 0.05, 0.25),
            lin(m.get("grossMargin"), 0.20, 0.60),
            lin(m.get("opMargin"), 0.05, 0.30),
            lin(m.get("fcfMargin"), 0.0, 0.20),
        ]),
        "Bewertung": _avg([
            lin(m.get("fwdPe"), 40, 10),
            lin(m.get("peg"), 3.0, 0.5),
            lin(m.get("evEbitda"), 25, 6),
            lin(m.get("fcfYield"), 0.02, 0.08),
            lin(m.get("upside"), -0.10, 0.40),
        ]),
        "Wachstum": _avg([
            lin(m.get("revGrowth"), 0.0, 0.25),
            lin(m.get("earnGrowth"), 0.0, 0.30),
        ]),
        "Bilanz": _avg([
            lin(m.get("netDebtEbitda"), 4, -1),
            lin(m.get("cashCover"), 0.2, 2.0),
        ]),
    }
    analyst_score, _ = _analyst_category(m)
    categories["Analysten"] = analyst_score

    weights = dict(LARGECAP_WEIGHTS_BASE)
    analyst_count = m.get("analystCount")
    if analyst_count is not None and analyst_count < 3:
        weights["Analysten"] = 0.0
        flags.append("Analysten-Coverage fehlt (<3) - Kategorie ausgeschlossen")
    elif analyst_count is None or analyst_count < 15:
        weights["Analysten"] = 0.10
        weights["Bewertung"] += 0.025
        weights["Qualität/Moat"] += 0.025
        flags.append(f"Dünn-Coverage-Variante angewendet (Analysten={analyst_count})")
    else:
        flags.append(f"Analysten-Coverage voll ({analyst_count})")

    for cat, score in list(categories.items()):
        if score is None and weights.get(cat, 0) > 0:
            weights[cat] = 0.0
            flags.append(f"Kategorie '{cat}' fehlt mangels Daten - ausgeschlossen")

    weights = _renormalize(weights)
    return categories, weights, flags


def _score_smallcap(m: dict) -> tuple[dict, dict, list[str]]:
    flags = []
    drawdown = None
    if m.get("week52High") and m.get("price") is not None:
        drawdown = (m["week52High"] - m["price"]) / m["week52High"]

    categories = {
        "Qualität/Burggraben": _avg([
            lin(m.get("roe"), 0.05, 0.25),
            lin(m.get("grossMargin"), 0.20, 0.60),
            lin(m.get("fcfMargin"), 0.0, 0.20),
        ]),
        "Bilanz / Überlebensfähigkeit": _avg([
            lin(m.get("netDebtEbitda"), 4, -1),
            lin(m.get("cashCover"), 0.2, 2.0),
        ]),
        "Bewertungsabschlag": _avg([
            lin(drawdown, 0.0, 0.50),
            lin(m.get("pb"), 3, 0.5),
            lin(m.get("fwdPe"), 20, 6),
            lin(m.get("fcfYield"), 0.03, 0.10),
            lin(m.get("upside"), 0.0, 0.50),
        ]),
        "Setup/Stabilisierung": _setup_score(m.get("price"), m.get("week52Low"), m.get("week52High")),
    }

    weights = dict(SMALLCAP_WEIGHTS_BASE)
    for cat, score in list(categories.items()):
        if score is None and weights.get(cat, 0) > 0:
            weights[cat] = 0.0
            flags.append(f"Kategorie '{cat}' fehlt mangels Daten - ausgeschlossen")

    weights = _renormalize(weights)
    flags.append("⚑ Temporär-vs-struktureller Auslöser & Katalysator nur via KI-Analyse beurteilbar")
    return categories, weights, flags


def _fair_value(m: dict, profile: str) -> tuple[float | None, str]:
    analyst_count = m.get("analystCount")
    target_mean = m.get("targetMean")
    if analyst_count is not None and analyst_count >= 3 and target_mean is not None:
        return target_mean, "Analysten-Kursziel"

    forward_eps = m.get("forwardEps")
    fair_pe = 20 if profile == "largecap" else 14
    if forward_eps is not None and forward_eps > 0:
        return forward_eps * fair_pe, "Forward-KGV-Multiple"

    fcf = m.get("fcf")
    shares = m.get("sharesOutstanding")
    mult = 18 if profile == "largecap" else 13
    if fcf is not None and shares is not None and shares > 0:
        return fcf * mult / shares, "FCF-Multiple"

    return None, "nicht berechenbar"


def compute_score(raw: dict, profile: str) -> dict:
    """Nimmt yfinance-info-dict + Profil ('largecap'/'smallcap'), liefert komplettes Ergebnis-dict."""
    m = compute_derived_metrics(raw)

    if profile == "smallcap":
        categories, weights, flags = _score_smallcap(m)
    else:
        categories, weights, flags = _score_largecap(m)

    total = sum(weights.get(cat, 0) * score for cat, score in categories.items() if score is not None)
    total = round(total)

    sub_scores = {cat: round(score) for cat, score in categories.items() if score is not None}

    fair_value, fv_method = _fair_value(m, profile)
    flags.append(f"Fairwert-Methode: {fv_method}")

    quality_key = "Qualität/Moat" if profile == "largecap" else "Qualität/Burggraben"
    quality_score = sub_scores.get(quality_key)

    if profile == "largecap":
        mos = 0.15 if (quality_score is not None and quality_score >= 70) else 0.25
    else:
        mos = 0.30

    buy_zone = fair_value * (1 - mos) if fair_value else None
    conservative_fair_value = fair_value * 0.85 if fair_value else None
    sell_threshold = fair_value * 1.15 if fair_value else None
    safety_margin_pct = None
    if fair_value and m.get("price") is not None:
        safety_margin_pct = (fair_value - m["price"]) / fair_value

    price = m.get("price")
    verdict = "HALTEN"
    if total < 45 or (sell_threshold is not None and price is not None and price >= sell_threshold):
        verdict = "VERKAUFEN"
    elif total >= 65 and buy_zone is not None and price is not None and price <= buy_zone:
        verdict = "KAUFEN"

    return {
        "metrics": m,
        "score": total,
        "scoreLabel": score_label(total),
        "subScores": sub_scores,
        "fairValue": round(fair_value, 2) if fair_value else None,
        "conservativeFairValue": round(conservative_fair_value, 2) if conservative_fair_value else None,
        "safetyMarginPct": round(safety_margin_pct, 4) if safety_margin_pct is not None else None,
        "buyZone": round(buy_zone, 2) if buy_zone else None,
        "sellThreshold": round(sell_threshold, 2) if sell_threshold else None,
        "verdict": verdict,
        "dataFlags": flags,
    }
