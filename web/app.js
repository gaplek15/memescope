/**
 * MemeScope — app.js
 * Vanilla JavaScript frontend logic. No frameworks, no bundler, no external deps.
 */

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const params = new URLSearchParams(window.location.search);
const API_BASE = params.get("api") || "http://localhost:8000";

const EXAMPLE_ADDRESS = "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82";
const EXAMPLE_CHAIN = 56;

const EVM_ADDRESS_RE = /^0x[0-9a-fA-F]{40}$/;

const CHAIN_NAMES = {
  56:  "bsc",
  1:   "ethereum",
  137: "polygon",
};

const EXPLORER_HOST = {
  56:  "bscscan.com",
  1:   "etherscan.io",
  137: "polygonscan.com",
};

const EXPLORER_LABEL = {
  56:  "BscScan",
  1:   "Etherscan",
  137: "Polygonscan",
};

const PROGRESS_STEPS_ORDER = ["cmc", "dex", "goplus", "onchain", "quote", "narrative", "done"];
const PROGRESS_STEP_LABELS = {
  cmc:       "CMC →",
  dex:       "DexScreener →",
  goplus:    "GoPlus →",
  onchain:   "On-chain →",
  quote:     "Quote →",
  narrative: "Narrative →",
  done:      "Done",
};

const LEADERBOARD_KEY = "memescope.leaderboard";
const MAX_LEADERBOARD = 20;
const SCREEN_TIMEOUT_MS = 65_000;

// ---------------------------------------------------------------------------
// DOM references (resolved once after DOMContentLoaded)
// ---------------------------------------------------------------------------

let dom = {};

function initDom() {
  dom = {
    form:           document.getElementById("screen-form"),
    addressInput:   document.getElementById("address-input"),
    chainSelect:    document.getElementById("chain-select"),
    addressError:   document.getElementById("address-error"),
    submitBtn:      document.getElementById("submit-btn"),
    exampleBtn:     document.getElementById("example-btn"),

    progressSection: document.getElementById("progress-section"),
    progressSteps:   document.getElementById("progress-steps"),
    progressLabel:   document.getElementById("progress-label"),

    errorBanner:    document.getElementById("error-banner"),

    reportSection:  document.getElementById("report-section"),
    verdictBadge:   document.getElementById("verdict-badge"),
    reportName:     document.getElementById("report-name"),
    reportAddress:  document.getElementById("report-address"),
    scoreValue:     document.getElementById("score-value"),

    cmcNote:        document.getElementById("cmc-note"),
    statPrice:      document.getElementById("stat-price"),
    statLiquidity:  document.getElementById("stat-liquidity"),
    statVolume:     document.getElementById("stat-volume"),
    statMcap:       document.getElementById("stat-mcap"),
    statDex:        document.getElementById("stat-dex"),
    statPair:       document.getElementById("stat-pair"),

    gatesTbody:     document.getElementById("gates-tbody"),
    narrativeText:  document.getElementById("narrative-text"),
    screenedAt:     document.getElementById("screened-at-value"),
    evidenceLinks:  document.getElementById("evidence-links"),

    leaderboardEmpty:    document.getElementById("leaderboard-empty"),
    leaderboardTableWrap: document.getElementById("leaderboard-table-wrap"),
    leaderboardTbody:    document.getElementById("leaderboard-tbody"),
  };
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

/**
 * Format a USD value.
 * Values ≥ $1 are shown with commas and no decimal.
 * Values < $1 are shown with 6 significant decimals (prices like $0.000001).
 */
function fmtUsd(value) {
  if (value == null) return "—";
  const n = Number(value);
  if (isNaN(n)) return "—";
  if (n >= 1) {
    return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  // Small price — show up to 6 sig figs
  return "$" + n.toPrecision(4);
}

/** Format a large USD number (liquidity, volume, mcap) with commas, no decimals. */
function fmtLargeUsd(value) {
  if (value == null) return "—";
  const n = Number(value);
  if (isNaN(n)) return "—";
  return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

/** Format an EVM address as 0x1234...abcd (first 6 + last 4 chars). */
function fmtAddress(addr) {
  if (!addr || addr.length < 10) return addr || "—";
  return addr.slice(0, 6) + "…" + addr.slice(-4);
}

/** Format an ISO timestamp to local time, e.g. "Nov 6, 2026 10:00 AM". */
function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

// ---------------------------------------------------------------------------
// Leaderboard (localStorage)
// ---------------------------------------------------------------------------

function loadLeaderboard() {
  try {
    const raw = localStorage.getItem(LEADERBOARD_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (_) {
    return [];
  }
}

function saveLeaderboard(entries) {
  try {
    localStorage.setItem(LEADERBOARD_KEY, JSON.stringify(entries));
  } catch (_) {
    // Storage full or unavailable — degrade silently.
  }
}

/**
 * Add or update an entry. Only called for LOLOS tokens.
 * Deduplicates by address (case-insensitive); keeps highest score.
 * Trims to MAX_LEADERBOARD entries sorted by score descending.
 */
function upsertLeaderboard(report) {
  const entries = loadLeaderboard();
  const addrKey = report.address.toLowerCase();
  const existing = entries.findIndex(e => e.address.toLowerCase() === addrKey);

  const entry = {
    address:      report.address,
    name:         report.name || report.symbol || fmtAddress(report.address),
    symbol:       report.symbol || "",
    score:        report.score,
    liquidity_usd: report.liquidity_usd,
    screened_at:  report.screened_at,
  };

  if (existing >= 0) {
    // Keep the highest score version
    if (entry.score >= entries[existing].score) {
      entries[existing] = entry;
    }
  } else {
    entries.push(entry);
  }

  entries.sort((a, b) => b.score - a.score);
  const trimmed = entries.slice(0, MAX_LEADERBOARD);
  saveLeaderboard(trimmed);
  return trimmed;
}

function renderLeaderboard() {
  const entries = loadLeaderboard();
  if (entries.length === 0) {
    dom.leaderboardEmpty.hidden = false;
    dom.leaderboardTableWrap.hidden = true;
    return;
  }
  dom.leaderboardEmpty.hidden = true;
  dom.leaderboardTableWrap.hidden = false;

  dom.leaderboardTbody.innerHTML = "";
  entries.forEach((entry, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="rank-cell">${i + 1}</td>
      <td class="token-cell">
        <span class="token-symbol">${escHtml(entry.symbol)}</span>
        <span class="token-name secondary">${escHtml(entry.name)}</span>
        <span class="token-addr secondary">${fmtAddress(entry.address)}</span>
      </td>
      <td class="score-cell">${entry.score}</td>
      <td>${fmtLargeUsd(entry.liquidity_usd)}</td>
      <td class="date-cell">${fmtDate(entry.screened_at)}</td>
    `;
    dom.leaderboardTbody.appendChild(tr);
  });
}

// ---------------------------------------------------------------------------
// Progress indicator
// ---------------------------------------------------------------------------

let progressInterval = null;
let currentStepIndex = 0;

function startProgress() {
  currentStepIndex = 0;
  updateProgressStep(0);
  dom.progressSection.hidden = false;

  progressInterval = setInterval(() => {
    currentStepIndex++;
    if (currentStepIndex < PROGRESS_STEPS_ORDER.length) {
      updateProgressStep(currentStepIndex);
    } else {
      clearInterval(progressInterval);
      progressInterval = null;
    }
  }, 2000);
}

function stopProgress() {
  if (progressInterval) {
    clearInterval(progressInterval);
    progressInterval = null;
  }
  dom.progressSection.hidden = true;
  // Reset all step states
  const steps = dom.progressSteps.querySelectorAll(".step");
  steps.forEach(s => {
    s.classList.remove("active", "done");
  });
}

function updateProgressStep(index) {
  const stepKey = PROGRESS_STEPS_ORDER[index];
  const label = PROGRESS_STEP_LABELS[stepKey] || stepKey;
  dom.progressLabel.textContent = label;

  const steps = dom.progressSteps.querySelectorAll(".step");
  steps.forEach((s, i) => {
    s.classList.remove("active", "done");
    if (i < index) s.classList.add("done");
    if (i === index) s.classList.add("active");
  });
}

// ---------------------------------------------------------------------------
// Error / clear helpers
// ---------------------------------------------------------------------------

function showError(msg) {
  dom.errorBanner.textContent = msg;
  dom.errorBanner.hidden = false;
}

function clearError() {
  dom.errorBanner.textContent = "";
  dom.errorBanner.hidden = true;
}

function showFieldError(msg) {
  dom.addressError.textContent = msg;
}

function clearFieldError() {
  dom.addressError.textContent = "";
}

// ---------------------------------------------------------------------------
// Report rendering
// ---------------------------------------------------------------------------

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function resultClass(result) {
  switch (result) {
    case "PASS": return "badge-pass";
    case "FAIL": return "badge-fail";
    case "WARN": return "badge-warn";
    default:     return "badge-unknown";
  }
}

function renderReport(report) {
  // --- Verdict ---
  const isLolos = report.verdict === "LOLOS";
  dom.verdictBadge.textContent = report.verdict;
  dom.verdictBadge.className = "verdict-badge " + (isLolos ? "verdict-lolos" : "verdict-gagal");

  dom.reportName.textContent = report.symbol
    ? `${report.name} (${report.symbol})`
    : report.name || "";
  dom.reportAddress.textContent = fmtAddress(report.address);
  dom.scoreValue.textContent = report.score;
  dom.scoreValue.className = "score-value " + (isLolos ? "score-lolos" : "score-gagal");

  // --- Market snapshot ---
  dom.cmcNote.hidden = (report.cmc_listed !== false);

  dom.statPrice.textContent = fmtUsd(report.price_usd);
  dom.statLiquidity.textContent = fmtLargeUsd(report.liquidity_usd);
  dom.statVolume.textContent = fmtLargeUsd(report.volume_24h);
  dom.statMcap.textContent = fmtLargeUsd(report.market_cap);
  dom.statDex.textContent = report.dex || "—";

  if (report.pair_address) {
    dom.statPair.textContent = fmtAddress(report.pair_address);
    dom.statPair.title = report.pair_address;
  } else {
    dom.statPair.textContent = "—";
  }

  // --- Gates table ---
  dom.gatesTbody.innerHTML = "";
  const gates = report.gates || [];
  gates.forEach(gate => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="gate-num">${gate.gate}</td>
      <td class="gate-name">${escHtml(gate.name)}</td>
      <td><span class="badge ${resultClass(gate.result)}">${escHtml(gate.result)}</span></td>
      <td class="gate-detail">${escHtml(gate.detail || "")}</td>
    `;
    dom.gatesTbody.appendChild(tr);
  });

  // --- Narrative ---
  dom.narrativeText.textContent = report.narrative || "";
  dom.screenedAt.textContent = fmtDate(report.screened_at);

  // --- Evidence links ---
  renderEvidenceLinks(report);

  // --- Show section ---
  dom.reportSection.hidden = false;

  // Scroll report into view on small screens
  dom.reportSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderEvidenceLinks(report) {
  const chain = Number(report.chain_id) || 56;
  const addr = report.address;
  const chainName = CHAIN_NAMES[chain] || "bsc";
  const explorerHost = EXPLORER_HOST[chain] || "bscscan.com";
  const explorerLabel = EXPLORER_LABEL[chain] || "BscScan";

  const links = [];

  if (report.pair_address) {
    links.push({
      label: "DexScreener",
      url: `https://dexscreener.com/${chainName}/${report.pair_address}`,
    });
  }

  links.push({
    label: "GoPlus",
    url: `https://gopluslabs.io/token-security/${chain}/${addr}`,
  });

  links.push({
    label: explorerLabel,
    url: `https://${explorerHost}/token/${addr}`,
  });

  dom.evidenceLinks.innerHTML = links
    .map(l => `<a href="${escHtml(l.url)}" class="evidence-pill" target="_blank" rel="noopener noreferrer">${escHtml(l.label)} ↗</a>`)
    .join("");
}

// ---------------------------------------------------------------------------
// Screening — the main flow
// ---------------------------------------------------------------------------

async function runScreening(address, chainId) {
  clearError();
  dom.reportSection.hidden = true;
  dom.submitBtn.disabled = true;

  startProgress();

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), SCREEN_TIMEOUT_MS);

  try {
    const res = await fetch(`${API_BASE}/api/screen`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ address, chain_id: chainId }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    stopProgress();

    if (!res.ok) {
      let errMsg = `Server error (HTTP ${res.status})`;
      try {
        const body = await res.json();
        if (body.error) errMsg = body.error;
      } catch (_) { /* ignore */ }
      showError(errMsg);
      return;
    }

    const report = await res.json();
    renderReport(report);

    if (report.verdict === "LOLOS") {
      upsertLeaderboard(report);
      renderLeaderboard();
    }

  } catch (err) {
    clearTimeout(timeoutId);
    stopProgress();

    if (err.name === "AbortError") {
      showError("Screening timed out — the backend may be down. Try again.");
    } else {
      showError("Network error — could not reach the backend. Make sure the server is running.");
    }
  } finally {
    dom.submitBtn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Event wiring
// ---------------------------------------------------------------------------

function handleSubmit(e) {
  e.preventDefault();
  clearFieldError();
  clearError();

  const address = dom.addressInput.value.trim();
  const chainId = parseInt(dom.chainSelect.value, 10);

  if (!EVM_ADDRESS_RE.test(address)) {
    showFieldError("Invalid address — expected 0x followed by 40 hex characters.");
    dom.addressInput.focus();
    return;
  }

  runScreening(address, chainId);
}

function handleExample() {
  dom.addressInput.value = EXAMPLE_ADDRESS;
  dom.chainSelect.value = String(EXAMPLE_CHAIN);
  clearFieldError();
  clearError();
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  initDom();
  renderLeaderboard();

  dom.form.addEventListener("submit", handleSubmit);
  dom.exampleBtn.addEventListener("click", handleExample);
});
