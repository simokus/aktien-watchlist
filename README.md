# Aktien Watchlist PWA

Täglich aktualisierter Aktien-Screener als installierbare PWA. Reines Vanilla
HTML/CSS/JS (kein Build-Step) auf GitHub Pages, Backend = GitHub Actions.

- **Repo:** https://github.com/simokus/aktien-watchlist (öffentlich — GitHub Pages
  erfordert auf dem kostenlosen Plan ein öffentliches Repo; im Code/Secrets steht nichts
  Sensibles)
- **Live-App:** https://simokus.github.io/aktien-watchlist/
- **Kennzahlen-Score** (0–100, KAUFEN/HALTEN/VERKAUFEN): täglicher Cron-Job (Python, yfinance),
  deterministisch, kein LLM.
- **KI-Tiefenanalyse**: auf Tap, via Claude-Code-CLI (Headless-Modus) mit Websuche, läuft
  serverseitig in einer GitHub Action gegen das **Claude Pro/Max-Abo-Kontingent** (kein
  separates Pay-per-Token-API-Billing). Das Auth-Token verlässt GitHub nie.

## Setup — bereits erledigt

Repo angelegt, Code gepusht (inkl. Workflow-Dateien), GitHub Pages aktiviert, erster
Daily-Update-Lauf erfolgreich durchgeführt (`data.json` ist befüllt), Trigger-Kette für
die KI-Tiefenanalyse End-to-End getestet.

## Setup — noch von dir zu erledigen

Siehe die separate **[SETUP-ANLEITUNG](SETUP-ANLEITUNG.md)** für die exakten,
Schritt-für-Schritt-Anweisungen (Claude-Code-Token erstellen, eigenes GitHub-Token
erstellen, App installieren). Kurzfassung:

1. Lokal `claude setup-token` ausführen (Claude Pro/Max-Abo vorausgesetzt) → erzeugten
   Token als Secret `CLAUDE_CODE_OAUTH_TOKEN` unter **Settings → Secrets and variables →
   Actions** anlegen (Pflicht für die KI-Tiefenanalyse). Optional zusätzlich `FMP_API_KEY`.
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
- **KI-Modell & Abrechnung**: `scripts/deep_analysis.py` ruft die **Claude-Code-CLI** im
  Headless-Modus (`claude -p ... --tools "WebSearch" --allowedTools "WebSearch"`) als
  Subprozess auf statt der Anthropic-Python-SDK direkt — dadurch läuft die Analyse gegen das
  **Claude Pro/Max-Abo-Kontingent** (`CLAUDE_CODE_OAUTH_TOKEN`, per `claude setup-token`
  erzeugt) statt gegen separate Pay-per-Token-API-Abrechnung. Das Token ist ein Jahr gültig
  und teilt sich das Nutzungslimit (rollierendes 5-Stunden-/Wochenlimit) mit der normalen
  Claude-Code-/claude.ai-Nutzung des Accounts. Wer stattdessen die klassische, unabhängig
  abgerechnete API bevorzugt (eigenes Kontingent, aber Kosten pro Aufruf), kann
  `run_claude_code()` wieder auf die Anthropic-Python-SDK zurückbauen — Modell bleibt
  `claude-sonnet-5`. Für tiefere Analysen: `--model claude-opus-5` in `run_claude_code()`
  setzen (aktuell leistungsfähigstes Opus-Modell, Stand dieses Setups). **Modell-Strings vor
  Nutzung immer gegen [docs.claude.com](https://docs.claude.com) prüfen** — sie ändern sich
  mit neuen Releases.
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
