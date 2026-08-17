# Setup-Anleitung — die letzten Schritte

Alles Technische ist bereits erledigt: Repo erstellt, Code gepusht, GitHub Pages aktiv,
erster Daten-Lauf erfolgreich. Es bleiben nur **3 Dinge**, die nur du machen kannst (weil sie
deinen eigenen Anthropic-Account bzw. dein Handy brauchen). Jeder Schritt dauert 2–5 Minuten.

**Aktueller Stand:**
- Repo: https://github.com/simokus/aktien-watchlist
- Live-App: **https://simokus.github.io/aktien-watchlist/**
- `data.json` ist bereits befüllt (MSFT, NVDA, GOOGL, NESN.SW, ASML.AS, VYX) — du kannst die
  Seite jetzt schon öffnen und die Übersicht + Scores ansehen, nur „KI-Tiefenanalyse" und
  „Ticker hinzufügen" fehlen noch die Schritte unten.

---

## Schritt 1 — Anthropic-API-Key erstellen und in GitHub hinterlegen

Ohne diesen Schritt funktioniert nur die „KI-Tiefenanalyse"-Funktion nicht — der Rest der App
läuft schon.

1. Gehe zu **https://console.anthropic.com/settings/keys** (mit deinem Anthropic-Account
   einloggen, falls noch keiner existiert: dort registrieren).
2. Klicke **„Create Key"**, gib ihr einen Namen (z. B. `aktien-watchlist`), klicke **„Create Key"**.
3. **Kopiere den angezeigten Key sofort** (beginnt mit `sk-ant-...`) — er wird danach nie
   wieder im Klartext angezeigt.
4. Gehe zu **https://github.com/simokus/aktien-watchlist/settings/secrets/actions**.
5. Klicke **„New repository secret"**.
6. Name: `ANTHROPIC_API_KEY` (exakt so, Gross-/Kleinschreibung beachten).
7. Secret: den kopierten Key einfügen.
8. Klicke **„Add secret"**.

> 💰 **Kosten:** Jede KI-Tiefenanalyse kostet ein paar Cent bis niedrige zweistellige Cent-Beträge
> (Modell `claude-sonnet-5` + Websuche). Es gibt keine automatische Obergrenze — der Key wird
> nur aktiv, wenn du in der App „KI-Tiefenanalyse starten" antippst.

---

## Schritt 2 — Eigenes GitHub-Token erstellen (für die App selbst)

Die App braucht ein eigenes, auf **nur dieses eine Repo** beschränktes Token, um Watchlists zu
speichern und KI-Analysen anzustossen. Das ist etwas anderes als dein Login bei GitHub selbst.

> ⚠️ **Achtung, Account-Falle:** Falls du mehrere GitHub-Accounts hast (bei uns z. B.
> `simokus` und `skuvert`) — stelle **unbedingt sicher, dass du im Browser bei `simokus`
> eingeloggt bist**, bevor du das Token erstellst. Prüfen: oben rechts auf github.com auf dein
> Profilbild klicken, der Name muss `simokus` sein. Falls nicht: erst ausloggen bzw. Account
> wechseln.

1. Gehe zu **https://github.com/settings/personal-access-tokens/new**
   (das ist der „Fine-grained token"-Bereich, **nicht** „Tokens (classic)").
2. **Token name:** z. B. `aktien-watchlist-app`
3. **Expiration:** z. B. 1 Jahr (oder „No expiration", falls verfügbar).
4. **Resource owner:** `simokus` auswählen.
5. **Repository access:** „Only select repositories" wählen → `simokus/aktien-watchlist`
   auswählen.
6. Runterscrollen zu **„Permissions" → „Repository permissions"**.
7. Bei **„Contents"** auf das Dropdown klicken und **„Read and write"** wählen.
   (Alles andere kann auf „No access" bleiben.)
8. Ganz unten **„Generate token"** klicken.
9. **Token sofort kopieren** (beginnt mit `github_pat_...`) — wird danach nie wieder
   angezeigt.

---

## Schritt 3 — Token in der App eintragen

1. Öffne **https://simokus.github.io/aktien-watchlist/**
2. Tippe auf das **⚙️-Zahnrad** oben rechts.
3. Trage ein:
   - **GitHub Owner:** `simokus`
   - **Repository:** `aktien-watchlist`
   - **Fine-grained Personal Access Token:** der Token aus Schritt 2
4. **„Speichern"** tippen.

Ab jetzt sind „Watchlists verwalten" (Ticker hinzufügen/entfernen, neue Watchlists) und
„KI-Tiefenanalyse starten" freigeschaltet (vorher ausgegraut).

---

## Schritt 4 — Auf dem Galaxy Z Fold 6 installieren

1. **https://simokus.github.io/aktien-watchlist/** in **Chrome** öffnen.
2. Auf die **drei Punkte** oben rechts tippen (Menü).
3. **„App installieren"** bzw. **„Zum Startbildschirm hinzufügen"** antippen.
4. Bestätigen.

Die App liegt danach als eigenes Icon auf dem Homescreen, startet ohne Browser-Leiste und
passt sich beim Aufklappen automatisch auf zwei Spalten an.

---

## Schritt 5 — Kurz testen

1. In der App eine Aktie antippen (z. B. NVDA) → runterscrollen zu „KI-Tiefenanalyse" →
   **„KI-Tiefenanalyse starten/aktualisieren"** tippen.
2. Status wechselt zu „Läuft im Hintergrund …". Das dauert **2–5 Minuten** (Websuche +
   Berichtserstellung). Die App fragt automatisch alle 20 Sekunden nach — einfach die App
   offen lassen oder später wieder reinschauen.
3. Fertiger Bericht erscheint automatisch inkl. „Dies ist keine Anlageberatung."-Hinweis.
4. Optional: unter „📋 Watchlists verwalten" einen neuen Ticker hinzufügen (z. B. `AAPL`) →
   „In GitHub speichern" → nach ca. 1 Minute läuft automatisch ein Update-Workflow und die
   Aktie erscheint mit Score in der Liste.

---

## Problembehebung

| Problem | Lösung |
|---|---|
| Button „KI-Tiefenanalyse starten" bleibt ausgegraut | Owner/Repo/Token in ⚙️ Einstellungen nochmal prüfen — alle drei Felder müssen ausgefüllt sein. |
| Fehlermeldung „401: GitHub-Token ungültig" | Token in Schritt 2 neu erstellen (evtl. abgelaufen oder falscher Account) und in ⚙️ neu eintragen. |
| Fehlermeldung „409: Datei zwischenzeitlich geändert" | Seite neu laden (🔄-Button oder Pull-to-Refresh) und Änderung erneut versuchen. |
| KI-Tiefenanalyse läuft länger als 8 Minuten / „Zeitüberschreitung" | Im Repo unter **Actions** (https://github.com/simokus/aktien-watchlist/actions) den Lauf „Deep Analysis" ansehen — meist fehlt der `ANTHROPIC_API_KEY` (Schritt 1) oder das Guthaben im Anthropic-Account ist aufgebraucht. |
| Score-Zahlen wirken komisch / Kennzahl fehlt | Normal bei sehr kleinen/exotischen Tickern — steht dann als Hinweis („dataFlags") im Detail der Aktie. |
| Watchlist-Änderung erscheint nicht in der Liste | Nach dem Speichern läuft automatisch der „Daily Update"-Workflow (dauert ~30–60 Sek.) — Seite danach neu laden. |

---

Bei Fragen: Actions-Tab (https://github.com/simokus/aktien-watchlist/actions) zeigt jeden
Lauf inkl. Fehlermeldungen im Detail.
