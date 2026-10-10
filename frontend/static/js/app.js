/* =============================================================================
   DocuMind — Core JavaScript Utilities
   Vanilla JS helpers, Markdown parser, Toast notifications, API client
   ============================================================================= */

// Global User ID Management (persists across sessions)
function getGlobalUserId() {
  let uid = localStorage.getItem("documind_user_id");
  if (!uid) {
    uid = "user_" + Math.random().toString(36).substring(2, 10) + Date.now().toString(36);
    localStorage.setItem("documind_user_id", uid);
  }
  return uid;
}

const GLOBAL_USER_ID = getGlobalUserId();

// ─── Toast Notifications ───────────────────────────────────────────────────

function showToast(message, type = "info", duration = 4000) {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast ${type}`;

  let iconSvg = "";
  if (type === "success") {
    iconSvg = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
  } else if (type === "error") {
    iconSvg = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`;
  } else {
    iconSvg = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`;
  }

  toast.innerHTML = `${iconSvg}<span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = "toastOut 200ms ease forwards";
    setTimeout(() => toast.remove(), 200);
  }, duration);
}

// ─── Formatters & Sanitizers ────────────────────────────────────────────────

function escapeHtml(text) {
  if (text == null) return "";
  const div = document.createElement("div");
  div.textContent = String(text);
  return div.innerHTML;
}

function formatFileSize(bytes) {
  if (bytes == null || isNaN(bytes)) return "0 B";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function formatTimeAgo(dateStr) {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  const now = new Date();
  const diffSec = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (diffSec < 60) return "just now";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  return `${diffDays}d ago`;
}

// ─── Client-side Markdown Formatter ─────────────────────────────────────────

function renderMarkdown(md) {
  if (!md) return "";

  let html = escapeHtml(md);

  // Fenced Code Blocks (```lang ... ```)
  html = html.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
    return `<pre><code class="language-${lang}">${code.trim()}</code></pre>`;
  });

  // Inline Code (`...`)
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Headings
  html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

  // Bold & Italic
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

  // Blockquotes
  html = html.replace(/^\> (.*$)/gim, '<blockquote>$1</blockquote>');

  // Citation references like [1], [2], [1, 2]
  html = html.replace(/\[(\d+(?:,\s*\d+)*)\]/g, '<span class="citation-ref">[$1]</span>');

  // Unordered lists (- or *)
  html = html.replace(/^\s*[-*]\s+(.*$)/gim, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/gim, '<ul>$1</ul>');
  // Clean up adjacent duplicate <ul> tags
  html = html.replace(/<\/ul>\s*<ul>/gim, '');

  // Line breaks to paragraphs
  const paragraphs = html.split(/\n{2,}/);
  html = paragraphs
    .map(p => {
      p = p.trim();
      if (!p) return "";
      if (p.startsWith("<h") || p.startsWith("<pre") || p.startsWith("<ul") || p.startsWith("<block")) {
        return p;
      }
      return `<p>${p.replace(/\n/g, "<br>")}</p>`;
    })
    .join("\n");

  return html;
}

// ─── API Client Wrapper ─────────────────────────────────────────────────────

async function apiRequest(endpoint, options = {}) {
  const headers = {
    "X-User-Id": GLOBAL_USER_ID,
    ...(options.headers || {}),
  };

  const response = await fetch(endpoint, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errDetail = `HTTP ${response.status}`;
    try {
      const errJson = await response.json();
      errDetail = errJson.detail || errJson.message || errDetail;
    } catch {
      // response wasn't JSON
    }
    const err = new Error(errDetail);
    err.status = response.status;
    throw err;
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

// ─── Backend Health Heartbeat ───────────────────────────────────────────────

async function checkBackendHealth() {
  const indicator = document.getElementById("backend-status");
  if (!indicator) return;

  try {
    const data = await apiRequest("/api/health");
    if (data.backend_status === 200 || (data.backend && data.backend.status === "healthy")) {
      indicator.className = "backend-status-indicator connected";
      indicator.title = "Connected to FastAPI Backend (Healthy)";
    } else {
      indicator.className = "backend-status-indicator error";
      indicator.title = "Backend is responding with issues";
    }
  } catch (e) {
    indicator.className = "backend-status-indicator error";
    indicator.title = "FastAPI Backend is unreachable";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  checkBackendHealth();
  // Poll backend health every 30 seconds
  setInterval(checkBackendHealth, 30000);
});
