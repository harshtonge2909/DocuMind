/* =============================================================================
   DocuMind — Evaluation Dashboard Controller (Vanilla JS)
   Renders Ragas Metrics, SVG Radar & Timeline Charts, Semantic Cache Stats
   ============================================================================= */

document.addEventListener("DOMContentLoaded", () => {
  loadEvaluationData();

  const refreshBtn = document.getElementById("refresh-eval-btn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      loadEvaluationData();
      showToast("Evaluation dashboard refreshed", "info");
    });
  }
});

async function loadEvaluationData() {
  const loadingEl = document.getElementById("eval-loading");
  const errorEl = document.getElementById("eval-error");
  const emptyEl = document.getElementById("eval-empty");
  const contentEl = document.getElementById("eval-content");

  loadingEl.style.display = "block";
  errorEl.style.display = "none";
  emptyEl.style.display = "none";
  contentEl.style.display = "none";

  try {
    const [evalData, cacheData] = await Promise.all([
      apiRequest("/api/eval/metrics?limit=50"),
      apiRequest("/api/eval/cache-stats"),
    ]);

    loadingEl.style.display = "none";

    if (!evalData || !evalData.summary || evalData.summary.total_queries === 0) {
      emptyEl.style.display = "block";
      return;
    }

    contentEl.style.display = "block";
    renderSummaryMetrics(evalData.summary);
    renderRadarChart(evalData.summary);
    renderTimelineChart(evalData.timeline || []);
    renderCacheStats(cacheData);
    renderEvaluationsTable(evalData.evaluations || []);
  } catch (err) {
    loadingEl.style.display = "none";
    errorEl.style.display = "block";
    const msgEl = document.getElementById("eval-error-message");
    if (msgEl) {
      msgEl.textContent = err.message || "Failed to load metrics from backend.";
    }
  }
}

function formatPercent(val) {
  if (val == null || isNaN(val)) return "—";
  return (val * 100).toFixed(1) + "%";
}

function renderSummaryMetrics(summary) {
  document.getElementById("val-total-queries").textContent = summary.total_queries || 0;
  document.getElementById("val-overall").textContent = formatPercent(summary.avg_overall_score);
  document.getElementById("val-faithfulness").textContent = formatPercent(summary.avg_faithfulness);
  document.getElementById("val-relevancy").textContent = formatPercent(summary.avg_answer_relevancy);
  document.getElementById("val-precision").textContent = formatPercent(summary.avg_context_precision);
  document.getElementById("val-recall").textContent = formatPercent(summary.avg_context_recall);
}

// ─── SVG Radar Chart Renderer ───────────────────────────────────────────────

function renderRadarChart(summary) {
  const svg = document.getElementById("radar-svg");
  if (!svg) return;

  const width = 360;
  const height = 280;
  const cx = width / 2;
  const cy = height / 2;
  const radius = 95;

  const dimensions = [
    { label: "Faithfulness", val: (summary.avg_faithfulness || 0) * 100 },
    { label: "Relevancy", val: (summary.avg_answer_relevancy || 0) * 100 },
    { label: "Precision", val: (summary.avg_context_precision || 0) * 100 },
    { label: "Recall", val: (summary.avg_context_recall || 0) * 100 },
  ];

  const totalAxes = dimensions.length;
  let bgRings = "";

  // Draw concentric polygon grid lines (25%, 50%, 75%, 100%)
  [0.25, 0.5, 0.75, 1.0].forEach((level) => {
    const points = [];
    for (let i = 0; i < totalAxes; i++) {
      const angle = (Math.PI * 2 / totalAxes) * i - Math.PI / 2;
      const x = cx + Math.cos(angle) * (radius * level);
      const y = cy + Math.sin(angle) * (radius * level);
      points.push(`${x},${y}`);
    }
    bgRings += `<polygon points="${points.join(" ")}" fill="none" stroke="#262626" stroke-width="1" />`;
  });

  // Axis lines and labels
  let axisLines = "";
  let dataPoints = [];

  dimensions.forEach((dim, i) => {
    const angle = (Math.PI * 2 / totalAxes) * i - Math.PI / 2;
    const ax = cx + Math.cos(angle) * radius;
    const ay = cy + Math.sin(angle) * radius;
    axisLines += `<line x1="${cx}" y1="${cy}" x2="${ax}" y2="${ay}" stroke="#262626" stroke-width="1" />`;

    // Label position slightly outside
    const lx = cx + Math.cos(angle) * (radius + 24);
    const ly = cy + Math.sin(angle) * (radius + 24);
    const anchor = Math.abs(Math.cos(angle)) < 0.1 ? "middle" : Math.cos(angle) > 0 ? "start" : "end";

    axisLines += `
      <text x="${lx}" y="${ly + 4}" text-anchor="${anchor}" fill="#a3a3a3" font-size="11" font-family="Inter, sans-serif">
        ${dim.label} (${dim.val.toFixed(0)}%)
      </text>
    `;

    // Data polygon point
    const scaledDist = (radius * Math.max(0, Math.min(100, dim.val))) / 100;
    const dx = cx + Math.cos(angle) * scaledDist;
    const dy = cy + Math.sin(angle) * scaledDist;
    dataPoints.push(`${dx},${dy}`);
  });

  const polygonPath = `<polygon points="${dataPoints.join(" ")}" fill="rgba(99, 102, 241, 0.25)" stroke="#6366f1" stroke-width="2" />`;

  svg.innerHTML = `
    ${bgRings}
    ${axisLines}
    ${polygonPath}
  `;
}

// ─── SVG Timeline Chart Renderer ───────────────────────────────────────────

function renderTimelineChart(timeline) {
  const svg = document.getElementById("timeline-svg");
  if (!svg) return;

  const width = 540;
  const height = 260;
  const padLeft = 40;
  const padRight = 20;
  const padTop = 30;
  const padBottom = 30;
  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  if (!timeline || timeline.length === 0) {
    svg.innerHTML = `
      <text x="${width / 2}" y="${height / 2}" fill="#737373" font-size="12" text-anchor="middle">
        Not enough timeline data points yet
      </text>
    `;
    return;
  }

  // Reverse timeline to chronological order (oldest to newest)
  const items = timeline.slice().reverse();

  // Grid lines (0%, 25%, 50%, 75%, 100%)
  let gridHtml = "";
  [0, 25, 50, 75, 100].forEach((pct) => {
    const y = padTop + chartH - (pct / 100) * chartH;
    gridHtml += `
      <line x1="${padLeft}" y1="${y}" x2="${width - padRight}" y2="${y}" stroke="#1f1f1f" stroke-width="1" />
      <text x="${padLeft - 8}" y="${y + 4}" fill="#525252" font-size="10" text-anchor="end">${pct}%</text>
    `;
  });

  // Calculate points for overall score line
  const stepX = items.length > 1 ? chartW / (items.length - 1) : chartW / 2;
  const points = [];

  items.forEach((item, idx) => {
    const score = (item.overall_score || item.faithfulness || 0) * 100;
    const x = padLeft + (items.length > 1 ? idx * stepX : chartW / 2);
    const y = padTop + chartH - (score / 100) * chartH;
    points.push({ x, y, score, idx: idx + 1 });
  });

  const polylineStr = points.map((p) => `${p.x},${p.y}`).join(" ");

  let circlesHtml = "";
  points.forEach((p) => {
    circlesHtml += `
      <circle cx="${p.x}" cy="${p.y}" r="3.5" fill="#4ade80" stroke="#000000" stroke-width="1.5">
        <title>Query #${p.idx}: ${p.score.toFixed(1)}%</title>
      </circle>
    `;
  });

  svg.innerHTML = `
    ${gridHtml}
    <polyline points="${polylineStr}" fill="none" stroke="#4ade80" stroke-width="2.5" />
    ${circlesHtml}
  `;
}

// ─── Cache Statistics ──────────────────────────────────────────────────────

function renderCacheStats(cache) {
  const badge = document.getElementById("cache-status-badge");
  const statusVal = document.getElementById("cache-status-val");
  const memVal = document.getElementById("cache-memory-val");
  const entriesVal = document.getElementById("cache-entries-val");
  const hitsVal = document.getElementById("cache-hits-val");

  if (!cache || cache.status === "disabled") {
    badge.className = "badge";
    badge.textContent = "Disabled";
    statusVal.textContent = "Offline";
    memVal.textContent = "—";
    entriesVal.textContent = "0";
    hitsVal.textContent = "—";
    return;
  }

  badge.className = "badge doc-status ready";
  badge.textContent = "Active";
  statusVal.textContent = "Connected";
  memVal.textContent = cache.used_memory || "N/A";
  entriesVal.textContent = cache.total_keys || cache.cached_queries || 0;
  hitsVal.textContent = cache.hit_rate != null ? `${(cache.hit_rate * 100).toFixed(1)}%` : "N/A";
}

// ─── Evaluations Table ──────────────────────────────────────────────────────

function renderEvaluationsTable(evaluations) {
  const tbody = document.getElementById("eval-table-body");
  const countEl = document.getElementById("eval-table-count");
  if (!tbody) return;

  tbody.innerHTML = "";
  countEl.textContent = `${evaluations.length} records`;

  if (evaluations.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-tertiary);">No evaluations recorded</td></tr>`;
    return;
  }

  evaluations.forEach((ev) => {
    const tr = document.createElement("tr");
    const qid = ev.query_id ? ev.query_id.substring(0, 8) + "..." : "—";
    const dateStr = ev.created_at ? new Date(ev.created_at).toLocaleDateString() : "—";

    tr.innerHTML = `
      <td>${qid}</td>
      <td>${formatPercent(ev.faithfulness)}</td>
      <td>${formatPercent(ev.answer_relevancy)}</td>
      <td>${formatPercent(ev.context_precision)}</td>
      <td>${formatPercent(ev.context_recall)}</td>
      <td><strong>${formatPercent(ev.overall_score)}</strong></td>
      <td>${dateStr}</td>
    `;
    tbody.appendChild(tr);
  });
}
