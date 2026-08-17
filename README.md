# Aktien Watchlist PWA

Täglich aktualisierter Aktien-Screener als installierbare PWA. Reines Vanilla
HTML/CSS/JS (kein Build-Step) auf GitHub Pages, Backend = GitHub Actions.

- **Repo:** https://github.com/simokus/aktien-watchlist (öffentlich — GitHub Pages
  erfordert auf dem kostenlosen Plan ein öffentliches Repo; im Code/Secrets steht nichts
  Sensibles)
- **Live-App:** https://simokus.github.io/aktien-watchlist/
- **Kennzahlen-Score** (0–100, KAUFEN/HALTEN/VERKAUFEN): täglicher Cron-Job (Python, yfinance),
  deterministisch, kein LLM.
- **KI-Tiefenanalyse**: auf Tap, via Anthropic-API mit Websuche, läuft serverseitig in einer
  GitHub Action. Der API-Key verlässt GitHub nie.

## Setup — bereits erledigt

Repo angelegt, Code gepusht (inkl. Workflow-Dateien), GitHub Pages aktiviert, erster
Daily-Update-Lauf erfolgreich durchgeführt (`data.json` ist befüllt), Trigger-Kette für
die KI-Tiefenanalyse End-to-End getestet.

## Setup — noch von dir zu erledigen

Siehe die separate **[SETUP-ANLEITUNG](SETUP-ANLEITUNG.md)** für die exakten,
Schritt-für-Schritt-Anweisungen (Anthropic-Key hinterlegen, eigenes GitHub-Token
erstellen, App installieren). Kurzfassung:

1. **Settings → Secrets and variables → Actions** → `ANTHROPIC_API_KEY` anlegen
   (Pflicht für die KI-Tiefenanalyse). Optional zusätzlich `FMP_API_KEY`.
2. **Fine-grained Personal Access Token** erstellen (github.com/settings/tokens?type=beta),
   Scope nur auf `aktien-watchlist`, Permission **Contents: Read and write** — dann in der
   App unter ⚙️ Einstellungen eintragen (Owner `simokus`, Repo `aktien-watchlist`, Token).
   Der Token bleibt ausschliesslich im Browser-`localStorage`.
3. **Auf dem Handy installieren**: https://simokus.github.io/aktien-watchlist/ in Chrome
   öffnen → Menü → „Zum Startbildschirm hinzufügen".
4. **Watchlists anpassen**: `largecaps`/`smallcaps` sind vorbefüllt (`watchlists.json`).
   Über „📋 Watchlists verwalten" in der App änderbar (Token erforderlich) — jede Änderung
   schreibt `watchlists.json` direkt ins Repo und stösst dank des `push`-Triggers sofort
   ein Daily-Update für die neuen Ticker an.

## Architektur-Entscheidungen (kurz)

- **Ticker-Profil-Zuordnung**: Kommt ein Ticker in mehreren Watchlists mit unterschiedlichem
  Profil vor, gewinnt die zuerst in `watchlists.json` gelistete Watchlist.
- **yfinance-Robustheit**: Ticker-Fetch läuft mit eigenem `User-Agent` + kurzen Sleeps zwischen
  Requests. Schlägt ein Ticker fehl, bleibt der letzte gute Eintrag aus `data.json` erhalten
  (`stale: true` + Flag), der Lauf bricht nicht ab.
- **FMP-Upgrade-Pfad**: Best-effort-Mapping auf die yfinance-Feldnamen aus `quote`/`profile`/
  `key-metrics-ttm`/`ratios-ttm`. Nicht abgedeckte Felder bleiben `null` und werden von
  `scoring.py` automatisch aus der Gewichtung ausgeschlossen (Renormierung + `dataFlags`).
  Schlägt FMP für einen Ticker fehl, fällt der Lauf für diesen Ticker automatisch auf
  yfinance zurück.
- **`dividendYield`-Quirk**: Aktuelle yfinance-Versionen liefern `dividendYield` bereits als
  fertigen Prozentwert (z. B. `3.83` = 3.83 %), nicht als Bruch wie die übrigen Kennzahlen.
  Frontend und KI-Prompt formatieren das Feld entsprechend ohne zusätzliche `×100`-Umrechnung.
- **KI-Modell**: Standard ist `claude-sonnet-5` (gutes Kosten-/Qualitäts-Verhältnis für die
  websuche-gestützte Tiefenanalyse). Für noch tiefere Analysen kann in
  `scripts/deep_analysis.py` auf `claude-opus-5` gewechselt werden (aktuell leistungsfähigstes
  Opus-Modell, Stand dieses Setups). **Modell-Strings vor Nutzung immer gegen
  [docs.claude.com](https://docs.claude.com) prüfen** — sie ändern sich mit neuen Releases.
- **Markdown-Renderer**: bewusst eine ~50-zeilige Eigenimplementierung (`renderMarkdown` in
  `app.js`) statt einer CDN-Bibliothek wie `marked` — deckt Überschriften, Tabellen, Listen,
  Bold/Italic/Code ab (das Format, das die KI-Prompts erzeugen) und funktioniert damit auch
  offline ohne zusätzliche Netzwerk-Abhängigkeit im Service Worker.
- **Pull-to-Refresh**: einfacher Touch-Schwellenwert (>80 px Pull von `scrollY===0`), kein
  visuelles Indikator-Widget. Auf Android-Chrome im installierten PWA-Modus greift zusätzlich
  das native Pull-to-Refresh des Browsers.
- **Dark Mode**: folgt automatisch `prefers-color-scheme` (System-Einstellung), kein manueller
  Umschalter.

## Manuelles Testen der KI-Tiefenanalyse

Im Actions-Tab kann der Workflow „Deep Analysis" auch manuell mit `ticker`/`profile`-Eingabe
gestartet werden (`workflow_dispatch`), ohne den Umweg über die App.

## Grenzen / bekannte Vereinfachungen

- Score-Formel ist eine Näherung an das Analyse-Rubric, kein Ersatz für die KI-Tiefenanalyse.
- FMP-Anbindung deckt nur Basiskennzahlen ab (Kurs, Bewertung teilweise) — für volle
  Kennzahlentiefe bleibt yfinance die verlässlichere Quelle.
- Kein automatisches Update-Retry bei GitHub-Actions-Rate-Limits — bei sehr grossen
  Watchlists ggf. `time.sleep`-Wert in `scripts/update.py` erhöhen.

---

Dies ist keine Anlageberatung.
