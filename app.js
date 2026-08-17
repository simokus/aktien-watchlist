// Aktien Watchlist PWA — Vanilla JS, kein Build-Step.

const LS_SETTINGS = "watchlist-settings";
const LS_UI = "watchlist-ui";
const POLL_INTERVAL_MS = 20000;
const POLL_MAX_ATTEMPTS = 36; // ~12 Minuten - Claude-Code-CLI-Loop dauert tendenziell laenger als ein reiner API-Call

const state = {
  watchlists: { watchlists: [] },
  data: { lastUpdated: null, source: null, stocks: {} },
  activeWatchlistId: null,
  sortBy: "score",
  filterBy: "alle",
  selectedTicker: null,
  settings: { owner: "", repo: "", pat: "" },
  aiPoll: null,
};

// ---------- Storage ----------

function loadSettings() {
  try {
    Object.assign(state.settings, JSON.parse(localStorage.getItem(LS_SETTINGS) || "{}"));
  } catch { /* ignore */ }
}

function saveSettings() {
  localStorage.setItem(LS_SETTINGS, JSON.stringify(state.settings));
}

function loadUiPrefs() {
  try {
    const ui = JSON.parse(localStorage.getItem(LS_UI) || "{}");
    if (ui.activeWatchlistId) state.activeWatchlistId = ui.activeWatchlistId;
    if (ui.sortBy) state.sortBy = ui.sortBy;
    if (ui.filterBy) state.filterBy = ui.filterBy;
  } catch { /* ignore */ }
}

function saveUiPrefs() {
  localStorage.setItem(LS_UI, JSON.stringify({
    activeWatchlistId: state.activeWatchlistId,
    sortBy: state.sortBy,
    filterBy: state.filterBy,
  }));
}

function hasPat() {
  return !!(state.settings.pat && state.settings.owner && state.settings.repo);
}

// ---------- Formatting ----------

function fmtNum(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/v";
  return v.toLocaleString("de-CH", { minimumFractionDigits: 0, maximumFractionDigits: digits });
}

function fmtPrice(v, currency) {
  if (v === null || v === undefined) return "n/v";
  return `${fmtNum(v)} ${currency || ""}`.trim();
}

function fmtPct(v, digits = 1) {
  if (v === null || v === undefined) return "n/v";
  return `${(v * 100).toFixed(digits)} %`;
}

// yfinance liefert dividendYield als bereits fertigen Prozentwert (z.B. 3.83 = 3.83%),
// nicht als Bruch wie die übrigen Kennzahlen - daher eigener Formatter ohne *100.
function fmtRawPct(v, digits = 2) {
  if (v === null || v === undefined) return "n/v";
  return `${v.toFixed(digits)} %`;
}

function fmtMarketCap(v) {
  if (!v) return "n/v";
  if (v >= 1e12) return `${(v / 1e12).toFixed(2)} Bio.`;
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)} Mrd.`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)} Mio.`;
  return fmtNum(v, 0);
}

function scoreClass(score) {
  if (score >= 80) return "score-80";
  if (score >= 65) return "score-65";
  if (score >= 45) return "score-45";
  if (score >= 30) return "score-30";
  return "score-0";
}

function subscoreColor(score) {
  if (score >= 80) return "var(--green)";
  if (score >= 65) return "var(--lightgreen)";
  if (score >= 45) return "var(--gray)";
  if (score >= 30) return "var(--orange)";
  return "var(--red)";
}

function relTime(iso) {
  if (!iso) return "noch nie";
  const d = new Date(iso);
  return d.toLocaleString("de-CH", { dateStyle: "medium", timeStyle: "short" });
}

// ---------- Minimaler Markdown-Renderer ----------
// ponytail: deckt Überschriften/Tabellen/Listen/Bold/Italic/Code ab - reicht für
// die vom LLM erzeugten Berichte. Kein voller CommonMark-Support (kein CDN nötig).
function renderMarkdown(md) {
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = (s) => esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(?<!\*)\*([^*]+?)\*(?!\*)/g, "<em>$1</em>")
    .replace(/`([^`]+?)`/g, "<code>$1</code>");

  const lines = md.replace(/\r\n/g, "\n").split("\n");
  let html = "";
  let i = 0;
  let inList = false;

  const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };

  while (i < lines.length) {
    const line = lines[i];

    if (/^#{1,6}\s+/.test(line)) {
      closeList();
      const level = line.match(/^#+/)[0].length;
      const text = line.replace(/^#{1,6}\s+/, "");
      html += `<h${Math.min(level + 1, 6)}>${inline(text)}</h${Math.min(level + 1, 6)}>`;
      i++;
      continue;
    }

    if (/^\|.*\|\s*$/.test(line)) {
      closeList();
      const rows = [];
      while (i < lines.length && /^\|.*\|\s*$/.test(lines[i])) {
        rows.push(lines[i].trim().slice(1, -1).split("|").map((c) => c.trim()));
        i++;
      }
      if (rows.length > 1 && rows[1].every((c) => /^:?-+:?$/.test(c))) rows.splice(1, 1);
      html += "<table><thead><tr>" + rows[0].map((c) => `<th>${inline(c)}</th>`).join("") + "</tr></thead><tbody>";
      for (const r of rows.slice(1)) {
        html += "<tr>" + r.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>";
      }
      html += "</tbody></table>";
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inline(line.replace(/^[-*]\s+/, ""))}</li>`;
      i++;
      continue;
    }

    if (/^-{3,}\s*$/.test(line)) {
      closeList();
      html += "<hr>";
      i++;
      continue;
    }

    closeList();
    if (line.trim() === "") { i++; continue; }
    html += `<p>${inline(line)}</p>`;
    i++;
  }
  closeList();
  return html;
}

// ---------- Datenzugriff (relativ, GitHub Pages Origin) ----------

async function fetchJson(path) {
  const res = await fetch(`${path}?t=${Date.now()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return res.json();
}

async function loadWatchlists() {
  state.watchlists = await fetchJson("watchlists.json");
}

async function loadData() {
  state.data = await fetchJson("data.json");
}

async function loadAnalysis(ticker) {
  try {
    return await fetchJson(`analyses/${ticker}.json`);
  } catch {
    return null;
  }
}

// ---------- GitHub API (Schreiben) ----------

function utf8ToBase64(str) {
  return btoa(unescape(encodeURIComponent(str)));
}

async function githubApi(path, opts = {}) {
  const { owner, repo, pat } = state.settings;
  const res = await fetch(`https://api.github.com/repos/${owner}/${repo}${path}`, {
    ...opts,
    headers: {
      Authorization: `Bearer ${pat}`,
      Accept: "application/vnd.github+json",
      ...(opts.headers || {}),
    },
  });
  if (res.status === 401) throw new Error("401: GitHub-Token ungültig oder abgelaufen. Bitte PAT prüfen.");
  if (res.status === 409) throw new Error("409: Datei wurde zwischenzeitlich geändert (sha veraltet). Bitte neu laden.");
  if (!res.ok) throw new Error(`GitHub-API-Fehler ${res.status}: ${await res.text()}`);
  return res;
}

async function githubGetSha(path) {
  const res = await githubApi(`/contents/${path}`);
  const json = await res.json();
  return json.sha;
}

async function saveWatchlists(newWatchlists) {
  const sha = await githubGetSha("watchlists.json");
  const content = utf8ToBase64(JSON.stringify(newWatchlists, null, 2));
  await githubApi("/contents/watchlists.json", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: "chore: update watchlists via app", content, sha }),
  });
}

async function dispatchDeepAnalysis(ticker, profile) {
  await githubApi("/dispatches", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_type: "deep-analysis", client_payload: { ticker, profile } }),
  });
}

// ---------- Rendering: Tabs ----------

function renderTabs() {
  const nav = document.getElementById("tabs");
  nav.innerHTML = "";
  const lists = state.watchlists.watchlists || [];
  if (!state.activeWatchlistId || !lists.find((w) => w.id === state.activeWatchlistId)) {
    state.activeWatchlistId = lists[0]?.id || null;
  }
  for (const wl of lists) {
    const btn = document.createElement("button");
    btn.className = "tab" + (wl.id === state.activeWatchlistId ? " active" : "");
    btn.textContent = wl.name;
    btn.addEventListener("click", () => {
      state.activeWatchlistId = wl.id;
      saveUiPrefs();
      renderTabs();
      renderList();
    });
    nav.appendChild(btn);
  }
}

// ---------- Rendering: Liste ----------

function getActiveWatchlist() {
  return (state.watchlists.watchlists || []).find((w) => w.id === state.activeWatchlistId) || null;
}

function getVisibleStocks() {
  const wl = getActiveWatchlist();
  if (!wl) return [];
  let list = wl.tickers
    .map((t) => state.data.stocks[t])
    .filter(Boolean);

  if (state.filterBy !== "alle") {
    list = list.filter((s) => s.verdict === state.filterBy);
  }

  const verdictOrder = { KAUFEN: 0, HALTEN: 1, VERKAUFEN: 2 };
  const sorters = {
    score: (a, b) => b.score - a.score,
    verdict: (a, b) => verdictOrder[a.verdict] - verdictOrder[b.verdict] || b.score - a.score,
    name: (a, b) => a.name.localeCompare(b.name),
    change: (a, b) => (b.changePct ?? -999) - (a.changePct ?? -999),
  };
  list.sort(sorters[state.sortBy] || sorters.score);
  return list;
}

function renderList() {
  const panel = document.getElementById("list-panel");
  const stocks = getVisibleStocks();
  const lastUpdatedEl = document.getElementById("last-updated");
  lastUpdatedEl.textContent = state.data.lastUpdated
    ? `Zuletzt aktualisiert: ${relTime(state.data.lastUpdated)}`
    : "Noch keine Daten vorhanden - Daily-Update-Workflow ausführen.";

  if (!stocks.length) {
    panel.innerHTML = '<p class="empty-hint">Keine Aktien in dieser Ansicht.</p>';
    return;
  }

  panel.innerHTML = "";
  for (const s of stocks) {
    const card = document.createElement("div");
    card.className = "stock-card" + (s.ticker === state.selectedTicker ? " selected" : "");
    const changeClass = (s.changePct ?? 0) >= 0 ? "change-pos" : "change-neg";
    const changeSign = (s.changePct ?? 0) >= 0 ? "+" : "";
    card.innerHTML = `
      <div class="stock-main">
        <span class="stock-name">${s.name}${s.stale ? '<span class="stale-flag">⚠ veraltet</span>' : ""}</span>
        <span class="stock-ticker">${s.ticker} · ${fmtPrice(s.price, s.currency)}</span>
      </div>
      <div class="stock-price-col">
        <span class="${changeClass}">${changeSign}${fmtNum(s.changePct)}%</span>
        <div class="stock-badges">
          <span class="score-badge ${scoreClass(s.score)}">${s.score}</span>
          <span class="verdict-pill verdict-${s.verdict}">${s.verdict}</span>
        </div>
      </div>`;
    card.addEventListener("click", () => selectTicker(s.ticker));
    panel.appendChild(card);
  }
}

// ---------- Rendering: Detail ----------

function selectTicker(ticker) {
  state.selectedTicker = ticker;
  document.body.classList.add("showing-detail");
  renderList();
  renderDetail(ticker);
}

function renderDetail(ticker) {
  const panel = document.getElementById("detail-panel");
  const s = state.data.stocks[ticker];
  if (!s) {
    panel.innerHTML = '<p class="empty-hint">Keine Daten für diese Aktie.</p>';
    return;
  }
  const changeClass = (s.changePct ?? 0) >= 0 ? "change-pos" : "change-neg";
  const changeSign = (s.changePct ?? 0) >= 0 ? "+" : "";
  const m = s.metrics || {};

  const subScoreRows = Object.entries(s.subScores || {}).map(([label, val]) => `
    <div class="subscore-row">
      <div class="subscore-label"><span>${label}</span><span>${val}</span></div>
      <div class="subscore-bar-bg"><div class="subscore-bar-fill" style="width:${val}%;background:${subscoreColor(val)}"></div></div>
    </div>`).join("");

  const smallcapFlag = s.profileUsed === "smallcap"
    ? '<p class="flag-smallcap">⚑ Temporärer vs. struktureller Auslöser & sichtbarer Katalysator sind nicht im Tages-Score enthalten - nur via KI-Tiefenanalyse beurteilbar.</p>'
    : "";

  panel.innerHTML = `
    <button class="back-btn" id="btn-back">← Zurück</button>
    <div class="detail-header">
      <div>
        <h2 class="detail-title">${s.name}</h2>
        <p class="detail-sub">${s.ticker} · ${s.sector || "n/v"} / ${s.industry || "n/v"} · Marktkap. ${fmtMarketCap(s.marketCap)}</p>
      </div>
      <div class="stock-badges">
        <span class="score-badge ${scoreClass(s.score)}">${s.score}</span>
        <span class="verdict-pill verdict-${s.verdict}">${s.verdict}</span>
      </div>
    </div>
    <p class="detail-sub">${fmtPrice(s.price, s.currency)} <span class="${changeClass}">${changeSign}${fmtNum(s.changePct)}%</span> · Score-Label: ${s.scoreLabel}</p>
    ${s.summary ? `<p class="detail-summary">${s.summary}</p>` : ""}
    ${smallcapFlag}

    <table class="kv-table">
      <tr><td>KGV (trailing / forward)</td><td>${fmtNum(m.pe)} / ${fmtNum(m.fwdPe)}</td></tr>
      <tr><td>PEG</td><td>${fmtNum(m.peg)}</td></tr>
      <tr><td>P/B · EV/EBITDA</td><td>${fmtNum(m.pb)} · ${fmtNum(m.evEbitda)}</td></tr>
      <tr><td>FCF-Yield</td><td>${fmtPct(m.fcfYield)}</td></tr>
      <tr><td>ROE</td><td>${fmtPct(m.roe)}</td></tr>
      <tr><td>Bruttomarge / Op-Marge</td><td>${fmtPct(m.grossMargin)} / ${fmtPct(m.opMargin)}</td></tr>
      <tr><td>Net Debt/EBITDA</td><td>${fmtNum(m.netDebtEbitda)}</td></tr>
      <tr><td>Umsatz-/Gewinnwachstum</td><td>${fmtPct(m.revGrowth)} / ${fmtPct(m.earnGrowth)}</td></tr>
      <tr><td>Beta</td><td>${fmtNum(m.beta)}</td></tr>
      <tr><td>52W-Range</td><td>${fmtNum(m.week52Low)} - ${fmtNum(m.week52High)}</td></tr>
      <tr><td>Analysten-Kursziel</td><td>${fmtNum(m.targetMean)} (${m.analystCount ?? 0} Analysten)</td></tr>
      <tr><td>Dividendenrendite</td><td>${fmtRawPct(m.dividendYield)}</td></tr>
    </table>

    <h3>Sub-Scores</h3>
    ${subScoreRows}

    <div class="zone-box">
      <div class="zone-item"><span class="zl">Fairwert</span><span class="zv">${fmtPrice(s.fairValue, s.currency)}</span></div>
      <div class="zone-item"><span class="zl">Sicherheitsmarge</span><span class="zv">${s.safetyMarginPct != null ? fmtPct(s.safetyMarginPct) : "n/v"}</span></div>
      <div class="zone-item"><span class="zl">Kaufzone bis</span><span class="zv">${fmtPrice(s.buyZone, s.currency)}</span></div>
      <div class="zone-item"><span class="zl">Verkaufsschwelle</span><span class="zv">${fmtPrice(s.sellThreshold, s.currency)}</span></div>
    </div>

    ${(s.dataFlags || []).length ? `<ul class="flags-list">${s.dataFlags.map((f) => `<li>${f}</li>`).join("")}</ul>` : ""}

    <div class="ai-section">
      <h3>KI-Tiefenanalyse</h3>
      <button id="btn-ai" class="btn-primary" ${hasPat() ? "" : "disabled"} title="${hasPat() ? "" : "GitHub-Token in Einstellungen erforderlich"}">
        KI-Tiefenanalyse starten/aktualisieren
      </button>
      <p id="ai-status" class="ai-status"></p>
      <div id="ai-result"></div>
    </div>
  `;

  document.getElementById("btn-back")?.addEventListener("click", () => {
    document.body.classList.remove("showing-detail");
  });
  document.getElementById("btn-ai")?.addEventListener("click", () => startDeepAnalysis(ticker, s.profileUsed));

  loadAndShowAnalysis(ticker);
}

async function loadAndShowAnalysis(ticker) {
  const analysis = await loadAnalysis(ticker);
  if (analysis && state.selectedTicker === ticker) showAnalysisResult(analysis);
}

function showAnalysisResult(analysis) {
  const resultEl = document.getElementById("ai-result");
  if (!resultEl) return;
  resultEl.innerHTML = `
    <div class="ai-markdown">${renderMarkdown(analysis.markdown || "")}</div>
    <p class="disclaimer">Dies ist keine Anlageberatung.</p>
    <p class="ai-meta">Modell: ${analysis.model} · Erstellt: ${relTime(analysis.generatedAt)}</p>
  `;
}

function startDeepAnalysis(ticker, profile) {
  if (state.aiPoll) clearInterval(state.aiPoll.timer);
  const statusEl = document.getElementById("ai-status");
  const btn = document.getElementById("btn-ai");
  const requestedAt = new Date().toISOString();

  btn.disabled = true;
  statusEl.textContent = "Wird angestossen …";

  dispatchDeepAnalysis(ticker, profile)
    .then(() => {
      statusEl.textContent = "Läuft im Hintergrund … (kann mehrere Minuten dauern)";
      let attempts = 0;
      const timer = setInterval(async () => {
        attempts++;
        const analysis = await loadAnalysis(ticker);
        if (analysis && analysis.generatedAt > requestedAt) {
          clearInterval(timer);
          state.aiPoll = null;
          btn.disabled = !hasPat();
          statusEl.textContent = "Analyse abgeschlossen.";
          if (state.selectedTicker === ticker) showAnalysisResult(analysis);
        } else if (attempts >= POLL_MAX_ATTEMPTS) {
          clearInterval(timer);
          state.aiPoll = null;
          btn.disabled = !hasPat();
          statusEl.textContent = "Zeitüberschreitung - Status im GitHub-Actions-Tab prüfen.";
        }
      }, POLL_INTERVAL_MS);
      state.aiPoll = { timer, ticker };
    })
    .catch((err) => {
      btn.disabled = !hasPat();
      statusEl.textContent = `Fehler: ${err.message}`;
    });
}

// ---------- Einstellungen-Dialog ----------

function initSettingsDialog() {
  const dialog = document.getElementById("settings-dialog");
  document.getElementById("btn-settings").addEventListener("click", () => {
    document.getElementById("settings-owner").value = state.settings.owner;
    document.getElementById("settings-repo").value = state.settings.repo;
    document.getElementById("settings-pat").value = state.settings.pat;
    dialog.showModal();
  });
  document.getElementById("settings-cancel").addEventListener("click", () => dialog.close());
  document.getElementById("settings-form").addEventListener("submit", (e) => {
    e.preventDefault();
    state.settings.owner = document.getElementById("settings-owner").value.trim();
    state.settings.repo = document.getElementById("settings-repo").value.trim();
    state.settings.pat = document.getElementById("settings-pat").value.trim();
    saveSettings();
    dialog.close();
    if (state.selectedTicker) renderDetail(state.selectedTicker);
  });
}

// ---------- Watchlists-verwalten-Dialog ----------

let manageDraft = null;

function slugify(name) {
  return name.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || `wl-${Date.now()}`;
}

function initManageDialog() {
  const dialog = document.getElementById("manage-dialog");
  document.getElementById("btn-manage").addEventListener("click", () => {
    manageDraft = JSON.parse(JSON.stringify(state.watchlists));
    document.getElementById("manage-status").textContent = hasPat()
      ? "" : "Ohne GitHub-Token nur lesbar - Token in Einstellungen hinterlegen zum Bearbeiten.";
    renderManageLists();
    const newForm = document.getElementById("new-watchlist-form");
    newForm.querySelectorAll("input, select, button").forEach((el) => { el.disabled = !hasPat(); });
    dialog.showModal();
  });
  document.getElementById("manage-close").addEventListener("click", () => dialog.close());
  document.getElementById("manage-save").addEventListener("click", async () => {
    const statusEl = document.getElementById("manage-status");
    if (!hasPat()) {
      statusEl.textContent = "GitHub-Token in Einstellungen erforderlich.";
      return;
    }
    statusEl.textContent = "Speichere …";
    try {
      await saveWatchlists(manageDraft);
      state.watchlists = manageDraft;
      statusEl.textContent = "Gespeichert. Der Daily-Update-Workflow läuft automatisch an.";
      renderTabs();
      renderList();
    } catch (err) {
      statusEl.textContent = `Fehler: ${err.message}`;
    }
  });
  document.getElementById("new-watchlist-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const name = document.getElementById("new-wl-name").value.trim();
    const profile = document.getElementById("new-wl-profile").value;
    if (!name) return;
    manageDraft.watchlists.push({ id: slugify(name), name, profile, tickers: [] });
    e.target.reset();
    renderManageLists();
  });
}

function renderManageLists() {
  const container = document.getElementById("manage-lists");
  const readOnly = !hasPat();
  container.innerHTML = "";
  manageDraft.watchlists.forEach((wl, idx) => {
    const block = document.createElement("div");
    block.className = "wl-block";
    block.innerHTML = `
      <div class="wl-block-head">
        <input type="text" value="${wl.name}" ${readOnly ? "disabled" : ""} data-role="name">
        <select ${readOnly ? "disabled" : ""} data-role="profile">
          <option value="largecap" ${wl.profile === "largecap" ? "selected" : ""}>largecap</option>
          <option value="smallcap" ${wl.profile === "smallcap" ? "selected" : ""}>smallcap</option>
        </select>
        <button class="wl-delete" ${readOnly ? "disabled" : ""} data-role="delete" title="Watchlist löschen">🗑</button>
      </div>
      <div class="wl-tickers">
        ${wl.tickers.map((t) => `<span class="wl-ticker-chip">${t} <button data-role="remove-ticker" data-ticker="${t}" ${readOnly ? "disabled" : ""}>✕</button></span>`).join("")}
      </div>
      <div class="wl-add-row">
        <input type="text" placeholder="Ticker hinzufügen (z.B. AAPL)" data-role="add-ticker-input" ${readOnly ? "disabled" : ""}>
        <button class="btn-secondary" data-role="add-ticker-btn" ${readOnly ? "disabled" : ""}>+ Add</button>
      </div>`;

    block.querySelector('[data-role="name"]').addEventListener("input", (e) => { wl.name = e.target.value; });
    block.querySelector('[data-role="profile"]').addEventListener("change", (e) => { wl.profile = e.target.value; });
    block.querySelector('[data-role="delete"]').addEventListener("click", () => {
      manageDraft.watchlists.splice(idx, 1);
      renderManageLists();
    });
    block.querySelectorAll('[data-role="remove-ticker"]').forEach((btn) => {
      btn.addEventListener("click", () => {
        wl.tickers = wl.tickers.filter((t) => t !== btn.dataset.ticker);
        renderManageLists();
      });
    });
    const addInput = block.querySelector('[data-role="add-ticker-input"]');
    const addTicker = () => {
      const val = addInput.value.trim().toUpperCase();
      if (!val) return;
      if (!/^[A-Z0-9.\-]{1,15}$/.test(val)) {
        alert("Ungültiges Ticker-Format. Erlaubt: Grossbuchstaben, Ziffern, Punkt, Bindestrich.");
        return;
      }
      if (!wl.tickers.includes(val)) wl.tickers.push(val);
      renderManageLists();
    };
    block.querySelector('[data-role="add-ticker-btn"]').addEventListener("click", addTicker);
    addInput.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); addTicker(); } });

    container.appendChild(block);
  });
}

// ---------- Toolbar ----------

function initToolbar() {
  const sortSelect = document.getElementById("sort-select");
  sortSelect.value = state.sortBy;
  sortSelect.addEventListener("change", () => {
    state.sortBy = sortSelect.value;
    saveUiPrefs();
    renderList();
  });

  document.querySelectorAll(".chip").forEach((chip) => {
    if (chip.dataset.filter === state.filterBy) chip.classList.add("active");
    chip.addEventListener("click", () => {
      state.filterBy = chip.dataset.filter;
      saveUiPrefs();
      document.querySelectorAll(".chip").forEach((c) => c.classList.toggle("active", c === chip));
      renderList();
    });
  });
  if (!document.querySelector(".chip.active")) {
    document.querySelector('.chip[data-filter="alle"]').classList.add("active");
  }
}

// ---------- Refresh & Pull-to-refresh ----------

async function refreshAll() {
  try {
    await Promise.all([loadWatchlists(), loadData()]);
    renderTabs();
    renderList();
    if (state.selectedTicker) renderDetail(state.selectedTicker);
  } catch (err) {
    console.error("Refresh fehlgeschlagen", err);
  }
}

function initPullToRefresh() {
  // ponytail: einfacher Schwellenwert-Pull ohne visuelles Feedback,
  // Ausbau (Indikator-Animation) bei Bedarf ergänzen.
  let startY = null;
  document.addEventListener("touchstart", (e) => {
    if (window.scrollY === 0) startY = e.touches[0].clientY;
  }, { passive: true });
  document.addEventListener("touchend", (e) => {
    if (startY === null) return;
    const dy = e.changedTouches[0].clientY - startY;
    startY = null;
    if (dy > 80) refreshAll();
  }, { passive: true });
}

// ---------- Init ----------

async function init() {
  loadSettings();
  loadUiPrefs();
  initSettingsDialog();
  initManageDialog();
  initToolbar();
  initPullToRefresh();
  document.getElementById("btn-refresh").addEventListener("click", refreshAll);

  try {
    await Promise.all([loadWatchlists(), loadData()]);
  } catch (err) {
    document.getElementById("list-panel").innerHTML = `<p class="empty-hint">Daten konnten nicht geladen werden: ${err.message}</p>`;
  }
  renderTabs();
  renderList();

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
  }
}

init();
