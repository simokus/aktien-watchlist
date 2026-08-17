"""KI-Tiefenanalyse via Claude-Code-CLI (Headless-Modus) mit Websuche. Laeuft gegen das
Claude Pro/Max-Abo-Kontingent (CLAUDE_CODE_OAUTH_TOKEN aus `claude setup-token`), nicht
gegen Pay-per-Token-API-Abrechnung. Wird durch die deep-analysis GitHub Action angestossen
(repository_dispatch). Schreibt analyses/<TICKER>.json.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, date, timezone
from pathlib import Path

import requests
import yfinance as yf

import scoring

ROOT = Path(__file__).resolve().parent.parent
ANALYSES_DIR = ROOT / "analyses"
MODEL = "claude-sonnet-5"
JSON_MARKER = "###JSON###"
CLAUDE_TIMEOUT_SECONDS = 600


def fetch_metrics(ticker: str) -> dict:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; AktienScreenerBot/1.0)"})
    info = yf.Ticker(ticker, session=session).info
    return scoring.compute_derived_metrics(info)


def format_metrics_de(m: dict) -> str:
    def pct(v):
        return f"{v * 100:.1f} %" if v is not None else "n/v"

    def num(v, digits=2):
        return f"{v:.{digits}f}" if v is not None else "n/v"

    lines = [
        f"- Kurs: {num(m.get('price'))} {m.get('currency') or ''} (Vortag: {num(m.get('previousClose'))})",
        f"- Marktkap.: {num(m.get('marketCap'), 0)}",
        f"- Sektor/Branche: {m.get('sector') or 'n/v'} / {m.get('industry') or 'n/v'}",
        f"- KGV (trailing/forward): {num(m.get('pe'))} / {num(m.get('fwdPe'))}",
        f"- PEG: {num(m.get('peg'))} · P/B: {num(m.get('pb'))} · EV/EBITDA: {num(m.get('evEbitda'))}",
        f"- FCF-Yield: {pct(m.get('fcfYield'))} · ROE: {pct(m.get('roe'))}",
        f"- Bruttomarge: {pct(m.get('grossMargin'))} · Op-Marge: {pct(m.get('opMargin'))}",
        f"- Net Debt/EBITDA: {num(m.get('netDebtEbitda'))} · Cash-Cover: {num(m.get('cashCover'))}",
        f"- Umsatzwachstum: {pct(m.get('revGrowth'))} · Gewinnwachstum: {pct(m.get('earnGrowth'))}",
        f"- Beta: {num(m.get('beta'))}",
        f"- 52W-Range: {num(m.get('week52Low'))} - {num(m.get('week52High'))}",
        f"- Analysten-Kursziel: {num(m.get('targetMean'))} ({m.get('analystCount') or 0} Analysten, "
        f"Empfehlung: {m.get('recommendationKey') or 'n/v'})",
        # yfinance liefert dividendYield bereits als Prozentwert (z.B. 3.83 = 3.83%), nicht als Bruch
        f"- Dividendenrendite: {num(m.get('dividendYield'))} %",
    ]
    return "\n".join(lines)


DISCLAIMER = "Dies ist keine Anlageberatung."

LARGECAP_INSTRUCTIONS = f"""
Erstelle eine vollständige Aktien-Analyse für {{ticker}} nach folgendem Rubric. Nutze die
Websuche aktiv für aktuelle Kurse, Analysten-Meinungen, News (letzte 4-8 Wochen) und
Reddit/Foren-Stimmung. Schreibe auf Deutsch, kompakt, mit Tabellen statt Fliesstext,
lege Annahmen offen und nenne das heutige Datum ({{today}}).

Gliederung:
A. Executive Summary (Gesamt-Score 0-100 + Label, innerer Wert vs. Kurs + Sicherheitsmarge %,
   Einstiegskurs/12M-Kursziel/Verkaufsschwelle, Kernkennzahlen-Tabelle)
B. Score-Aufschlüsselung: 7 Kategorien - Analysten 20% · Burggraben/Qualität 20% ·
   Bewertung 15% · Peer-Vergleich 15% · Szenario 15% · News/Stimmung 10% · Risiko 5%.
   Wende die Dünn-Coverage-Variante an, falls unter 15 Analysten covern (Analysten-Gewicht
   auf 10%, je +2.5pp auf Bewertung und Qualität).
C. Bewertung & innerer Wert: DCF-Grundgerüst mit sichtbaren Annahmen (Owner-Earnings-Basis,
   Wachstum, WACC, Terminal-Wert), Sicherheitsmarge & Einstiegskurs.
D. Burggraben & Qualitäts-Checkliste (6 Kriterien: Moat, ROE, FCF, Preissetzungsmacht,
   Management, Verständlichkeit) - je "erfüllt"/"teilweise"/"nicht" mit Begründung.
E. Peer-Vergleich (3-5 vergleichbare Unternehmen, Tabelle).
F. Analysten-Meinungen (Konsens, Kursziel-Spanne, jüngste Änderungen).
G. Szenario-Analyse 12 Monate (Bull/Base/Bear mit Kurszielen).
H. News & Marktstimmung (4-8 Wochen), Reddit-Stimmung, Crowded-Trade-Flag.
I. Risiko & Positionsgrösse (Beta, Klumpenrisiko, Vorschlag Max-Position in %).
J. Verkaufskriterien/Exit (vor dem Kauf definiert).
K. Ausblick 6-12 Monate.
L. Stärkstes Gegenargument gegen einen Kauf.

Ganz am Ende der Analyse (nach Abschnitt L): "{DISCLAIMER}"
"""

SMALLCAP_INSTRUCTIONS = f"""
Erstelle eine "Salatöl-Score"-Analyse für {{ticker}} (Small Cap) nach folgendem Rubric.
Nutze die Websuche aktiv für aktuelle Kurse, News (letzte 4-8 Wochen), Analysten-Meinungen
und Reddit/Foren-Stimmung. Schreibe auf Deutsch, kompakt, mit Tabellen statt Fliesstext,
lege Annahmen offen und nenne das heutige Datum ({{today}}).

Gliederung:
A. Salatöl-Score (0-100) gewichtet aus: (1) Qualität/Burggraben, (2) temporärer vs.
   struktureller Auslöser der aktuellen Schwäche, (3) Bilanz-/Überlebensfähigkeit,
   (4) Bewertungsabschlag, (5) sichtbarer Katalysator. Begründe jede Kategorie.
B. Salatöl-Test: Ist das Grundgeschäft intakt trotz schlechter Schlagzeile? Explizit
   durchführen und begründen.
C. Turnaround-Risiko: konkret benennen, was schiefgehen kann.
D. Kern-Bausteine der Aktien-Analyse: DCF-Grundgerüst/innerer Wert, Sicherheitsmarge
   (mind. 30% wg. Turnaround-Unsicherheit), Kaufzone, Verkaufsschwelle.
E. Peer-Vergleich (2-4 vergleichbare Unternehmen).
F. Szenario-Analyse 12 Monate (Bull/Base/Bear).
G. News & Marktstimmung (4-8 Wochen), Reddit-Stimmung.
H. Risiko & Positionsgrösse (klein halten - spekulativer Sleeve, % Vorschlag).
I. Verkaufskriterien/Exit.
J. Stärkstes Gegenargument gegen einen Kauf.

Ganz am Ende der Analyse (nach Abschnitt J): "{DISCLAIMER}"
"""

JSON_INSTRUCTIONS = f"""
Gib nach dem vollständigen Bericht eine neue Zeile aus, die exakt "{JSON_MARKER}" lautet,
gefolgt von ausschliesslich einem maschinenlesbaren JSON-Objekt (keine Markdown-Backticks,
kein weiterer Text danach) mit exakt diesen Feldern:
{{"score": <0-100 int>, "scoreLabel": "<string>", "fairValue": <number|null>,
"buyPrice": <number|null>, "sellPrice": <number|null>, "verdict": "KAUFEN"|"HALTEN"|"VERKAUFEN",
"flags": [<string>, ...]}}
"""


def build_prompt(ticker: str, profile: str, metrics_text: str) -> str:
    today = date.today().isoformat()
    instructions = SMALLCAP_INSTRUCTIONS if profile == "smallcap" else LARGECAP_INSTRUCTIONS
    instructions = instructions.format(ticker=ticker, today=today)

    return (
        f"{instructions}\n\n{JSON_INSTRUCTIONS}\n\n"
        f"Bekannte Kennzahlen (Stand yfinance, ggf. via Websuche aktualisieren):\n{metrics_text}"
    )


def run_claude_code(prompt: str) -> str:
    """Ruft die Claude-Code-CLI im Headless-Modus (-p) auf statt der Anthropic-API direkt.

    Auth laeuft ueber CLAUDE_CODE_OAUTH_TOKEN (Claude Pro/Max-Abo, via `claude setup-token`
    erzeugt) statt ueber ANTHROPIC_API_KEY - kostet damit nichts extra. --tools schraenkt
    die verfuegbaren Tools hart auf Websuche ein (kein Bash/Datei-Zugriff im CI-Runner
    noetig oder gewuenscht); --allowedTools bestaetigt sie zusaetzlich vorab, damit der
    Non-Interactive-Modus nicht auf eine Rueckfrage wartet. Flags gegen die real
    installierte CLI (2.1.233) verifiziert, nicht nur aus der Doku uebernommen.
    """
    result = subprocess.run(
        [
            "claude", "-p", prompt,
            "--model", MODEL,
            "--tools", "WebSearch",
            "--allowedTools", "WebSearch",
            "--output-format", "text",
            "--no-session-persistence",
        ],
        capture_output=True,
        text=True,
        timeout=CLAUDE_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        # claude -p schreibt Fehlermeldungen (z.B. Auth-Fehler) nach stdout, nicht stderr -
        # beide einbeziehen, sonst bleibt die eigentliche Ursache im Log unsichtbar.
        detail = (result.stdout.strip() + "\n" + result.stderr.strip()).strip()
        raise RuntimeError(f"claude-CLI Fehler (exit {result.returncode}): {detail[:2000]}")
    return result.stdout


def parse_result(full_text: str) -> tuple[str, dict]:
    if JSON_MARKER not in full_text:
        raise ValueError("Kein JSON-Marker in der Antwort gefunden")
    markdown, _, json_part = full_text.partition(JSON_MARKER)
    json_part = json_part.strip()
    match = re.search(r"\{.*\}", json_part, re.DOTALL)
    if not match:
        raise ValueError("Kein JSON-Objekt nach dem Marker gefunden")
    data = json.loads(match.group(0))
    return markdown.strip(), data


def main() -> None:
    ticker = os.environ["TICKER"].strip().upper()
    profile = os.environ.get("PROFILE", "largecap").strip().lower()

    metrics = fetch_metrics(ticker)
    metrics_text = format_metrics_de(metrics)
    prompt = build_prompt(ticker, profile, metrics_text)

    full_text = run_claude_code(prompt)
    markdown, result = parse_result(full_text)

    output = {
        "ticker": ticker,
        "profile": profile,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "model": MODEL,
        "markdown": markdown,
        "score": result.get("score"),
        "scoreLabel": result.get("scoreLabel"),
        "fairValue": result.get("fairValue"),
        "buyPrice": result.get("buyPrice"),
        "sellPrice": result.get("sellPrice"),
        "verdict": result.get("verdict"),
        "flags": result.get("flags", []),
    }

    ANALYSES_DIR.mkdir(exist_ok=True)
    out_path = ANALYSES_DIR / f"{ticker}.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Analyse für {ticker} geschrieben nach {out_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Fehler bei der Tiefenanalyse: {e}", file=sys.stderr)
        sys.exit(1)
