/* =============================================================================
   DocuMind — Chat Controller & SSE Stream Engine (Vanilla JS)
   Handles Document Ingestion, Threading, SSE Streams, Citations, Quotas
   ============================================================================= */

// Application State
const state = {
  documents: [],
  selectedDocument: null,
  conversations: [],
  activeConversationId: null,
  messages: [],
  isUploading: false,
  isStreaming: false,
  streamAbortController: null,
  pollTimer: null,
};

// DOM Elements
const elements = {
  // Sidebar & Documents
  sidebar: document.getElementById("app-sidebar"),
  mobileToggle: document.getElementById("mobile-sidebar-toggle"),
  dropzone: document.getElementById("pdf-dropzone"),
  fileInput: document.getElementById("pdf-file-input"),
  dropzoneDefault: document.getElementById("dropzone-default"),
  dropzoneLoading: document.getElementById("dropzone-loading"),
  uploadStatusText: document.getElementById("upload-status-text"),
  documentsList: document.getElementById("documents-list"),
  documentsEmpty: document.getElementById("documents-empty"),
  docCountBadge: document.getElementById("doc-count-badge"),

  // Conversations
  conversationSection: document.getElementById("conversation-section"),
  conversationsList: document.getElementById("conversations-list"),
  newChatBtn: document.getElementById("new-chat-btn"),

  // Usage Banner
  tierBadge: document.getElementById("tier-badge"),
  tierName: document.getElementById("tier-name"),
  usageText: document.getElementById("usage-text"),
  usageProgressBar: document.getElementById("usage-progress-bar"),
  refreshUsageBtn: document.getElementById("refresh-usage-btn"),
  tierToggleBtn: document.getElementById("tier-toggle-btn"),

  // Chat Panel
  activeDocBanner: document.getElementById("active-doc-banner"),
  activeDocName: document.getElementById("active-doc-name"),
  deselectDocBtn: document.getElementById("deselect-doc-btn"),
  chatMessages: document.getElementById("chat-messages"),
  chatNoDoc: document.getElementById("chat-no-doc"),
  chatEmptyPrompt: document.getElementById("chat-empty-prompt"),
  emptyDocTitle: document.getElementById("empty-doc-title"),
  emptyDocSubtitle: document.getElementById("empty-doc-subtitle"),
  messagesList: document.getElementById("messages-list"),
  messagesBottom: document.getElementById("messages-bottom"),

  // Streaming Bubble
  streamingBubble: document.getElementById("streaming-bubble"),
  streamingPhaseText: document.getElementById("streaming-phase-text"),
  streamingPartialAnswer: document.getElementById("streaming-partial-answer"),

  // Chat Input
  chatInput: document.getElementById("chat-input"),
  chatSendBtn: document.getElementById("chat-send-btn"),
  chatStopBtn: document.getElementById("chat-stop-btn"),
};

// ─── Initialization ─────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  loadDocuments();
  loadUsage();
});

function setupEventListeners() {
  // Mobile Sidebar Toggle
  if (elements.mobileToggle) {
    elements.mobileToggle.addEventListener("click", () => {
      elements.sidebar.classList.toggle("open");
    });
  }

  // Dropzone Events
  if (elements.dropzone) {
    elements.dropzone.addEventListener("click", () => elements.fileInput.click());

    elements.dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      elements.dropzone.classList.add("active");
    });

    elements.dropzone.addEventListener("dragleave", () => {
      elements.dropzone.classList.remove("active");
    });

    elements.dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      elements.dropzone.classList.remove("active");
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFileUpload(e.dataTransfer.files[0]);
      }
    });

    elements.fileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files.length > 0) {
        handleFileUpload(e.target.files[0]);
      }
    });
  }

  // Deselect Document
  if (elements.deselectDocBtn) {
    elements.deselectDocBtn.addEventListener("click", () => selectDocument(null));
  }

  // Start New Chat Thread
  if (elements.newChatBtn) {
    elements.newChatBtn.addEventListener("click", () => startNewChat());
  }

  // Refresh Usage
  if (elements.refreshUsageBtn) {
    elements.refreshUsageBtn.addEventListener("click", () => loadUsage(true));
  }

  // Tier Toggle (Upgrade / Downgrade)
  if (elements.tierToggleBtn) {
    elements.tierToggleBtn.addEventListener("click", handleTierToggle);
  }

  // Suggested Queries
  document.querySelectorAll(".suggested-query-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const q = btn.getAttribute("data-query");
      if (q && elements.chatInput) {
        elements.chatInput.value = q;
        submitQuery();
      }
    });
  });

  // Chat Input Events
  if (elements.chatInput) {
    elements.chatInput.addEventListener("input", autoResizeInput);
    elements.chatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        submitQuery();
      }
    });
  }

  if (elements.chatSendBtn) {
    elements.chatSendBtn.addEventListener("click", submitQuery);
  }

  if (elements.chatStopBtn) {
    elements.chatStopBtn.addEventListener("click", abortCurrentStream);
  }
}

function autoResizeInput() {
  const input = elements.chatInput;
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 140) + "px";
  elements.chatSendBtn.disabled = !input.value.trim() || !state.selectedDocument || state.isStreaming;
}

function scrollToBottom() {
  if (elements.messagesBottom) {
    elements.messagesBottom.scrollIntoView({ behavior: "smooth" });
  }
}

// ─── Document Management ───────────────────────────────────────────────────

async function handleFileUpload(file) {
  if (!file) return;

  if (!file.name.toLowerCase().endsWith(".pdf")) {
    showToast("Invalid file: Only PDF documents are supported.", "error");
    return;
  }

  if (file.size > 50 * 1024 * 1024) {
    showToast("File exceeds 50MB maximum size limit.", "error");
    return;
  }

  setUploading(true, `Uploading "${file.name}"...`);

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await apiRequest("/api/documents/upload", {
      method: "POST",
      body: formData,
    });

    showToast(`"${file.name}" uploaded successfully. Ingestion started!`, "success");
    elements.fileInput.value = "";
    await loadDocuments();

    // Select the newly uploaded document
    if (res.id) {
      selectDocument(res.id);
    }
  } catch (err) {
    showToast(err.message || "Failed to upload document", "error");
  } finally {
    setUploading(false);
  }
}

function setUploading(loading, text = "Uploading & Ingesting...") {
  state.isUploading = loading;
  if (loading) {
    elements.dropzoneDefault.style.display = "none";
    elements.dropzoneLoading.style.display = "flex";
    elements.uploadStatusText.textContent = text;
  } else {
    elements.dropzoneDefault.style.display = "flex";
    elements.dropzoneLoading.style.display = "none";
  }
}

async function loadDocuments() {
  try {
    const data = await apiRequest("/api/documents?limit=50");
    state.documents = data.documents || [];
    renderDocumentsList();

    // If active document was deleted externally, deselect
    if (state.selectedDocument && !state.documents.some((d) => d.id === state.selectedDocument.id)) {
      selectDocument(null);
    }

    // Check if any documents are still processing; if so, poll
    const hasPending = state.documents.some(
      (d) => d.status === "uploading" || d.status === "processing" || d.status === "chunking" || d.status === "embedding"
    );

    if (hasPending) {
      if (!state.pollTimer) {
        state.pollTimer = setInterval(loadDocuments, 2500);
      }
    } else {
      if (state.pollTimer) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
      }
    }
  } catch (e) {
    console.warn("Failed to load documents", e);
  }
}

function renderDocumentsList() {
  elements.docCountBadge.textContent = state.documents.length;

  if (state.documents.length === 0) {
    elements.documentsEmpty.style.display = "flex";
    elements.documentsList.innerHTML = "";
    elements.documentsList.appendChild(elements.documentsEmpty);
    return;
  }

  elements.documentsEmpty.style.display = "none";
  elements.documentsList.innerHTML = "";

  state.documents.forEach((doc) => {
    const card = document.createElement("div");
    const isSelected = state.selectedDocument && state.selectedDocument.id === doc.id;
    card.className = `doc-card ${isSelected ? "selected" : ""}`;

    let statusIcon = "";
    if (doc.status === "ready") {
      statusIcon = `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
    } else if (doc.status === "error") {
      statusIcon = `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;
    } else {
      statusIcon = `<svg class="spinner-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="12" y1="2" x2="12" y2="6"></line><line x1="12" y1="18" x2="12" y2="22"></line><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line><line x1="2" y1="12" x2="6" y2="12"></line><line x1="18" y1="12" x2="22" y2="12"></line></svg>`;
    }

    card.innerHTML = `
      <div class="doc-card-top">
        <span class="doc-card-name" title="${escapeHtml(doc.original_name)}">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
          ${escapeHtml(doc.original_name)}
        </span>
        <button class="doc-delete" title="Delete document" data-doc-id="${doc.id}">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
        </button>
      </div>
      <div class="doc-card-meta">
        <span class="doc-status ${doc.status}">${statusIcon} ${doc.status}</span>
        <span>${formatFileSize(doc.file_size)}</span>
        ${doc.page_count > 0 ? `<span>${doc.page_count} p</span>` : ""}
        ${doc.total_chunks > 0 ? `<span>${doc.total_chunks} chunks</span>` : ""}
      </div>
    `;

    card.addEventListener("click", () => selectDocument(doc.id));

    const deleteBtn = card.querySelector(".doc-delete");
    deleteBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteDocument(doc.id, doc.original_name);
    });

    elements.documentsList.appendChild(card);
  });
}

function selectDocument(docId) {
  if (!docId) {
    state.selectedDocument = null;
    state.activeConversationId = null;
    state.messages = [];
    updateWorkspaceViews();
    renderDocumentsList();
    return;
  }

  const doc = state.documents.find((d) => d.id === docId);
  if (!doc) return;

  state.selectedDocument = doc;
  state.activeConversationId = null;
  state.messages = [];

  updateWorkspaceViews();
  renderDocumentsList();
  loadConversations(doc.id);
}

async function deleteDocument(docId, docName) {
  if (!confirm(`Are you sure you want to delete "${docName}"? This will remove all chunks and citations.`)) {
    return;
  }

  try {
    await apiRequest(`/api/documents/${docId}`, { method: "DELETE" });
    showToast(`"${docName}" deleted`, "info");
    if (state.selectedDocument && state.selectedDocument.id === docId) {
      selectDocument(null);
    }
    await loadDocuments();
  } catch (err) {
    showToast(err.message || "Failed to delete document", "error");
  }
}

// ─── Conversation Threads ───────────────────────────────────────────────────

async function loadConversations(documentId) {
  if (!documentId) return;

  try {
    const data = await apiRequest(`/api/conversations?document_id=${documentId}`);
    state.conversations = data.conversations || [];
    renderConversationsList();
  } catch (e) {
    console.warn("Failed to load conversations", e);
  }
}

function renderConversationsList() {
  if (!state.selectedDocument) {
    elements.conversationSection.style.display = "none";
    return;
  }

  elements.conversationSection.style.display = "flex";
  elements.conversationsList.innerHTML = "";

  if (state.conversations.length === 0) {
    elements.conversationsList.innerHTML = `
      <div class="empty-state" style="padding: 16px 8px;">
        <p style="font-size: 11px; color: var(--text-tertiary);">No chat history yet</p>
      </div>
    `;
    return;
  }

  state.conversations.forEach((conv) => {
    const card = document.createElement("div");
    const isSelected = state.activeConversationId === conv.id;
    card.className = `conv-card ${isSelected ? "selected" : ""}`;

    card.innerHTML = `
      <div class="conv-card-top" id="conv-top-${conv.id}">
        <span class="conv-card-title" title="${escapeHtml(conv.title)}">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
          <span class="conv-title-text">${escapeHtml(conv.title)}</span>
        </span>
        <div class="conv-card-actions">
          <button class="conv-action-btn edit" title="Rename thread" data-id="${conv.id}">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>
          </button>
          <button class="conv-action-btn danger delete" title="Delete thread" data-id="${conv.id}">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
          </button>
        </div>
      </div>
      <div class="conv-card-meta">
        <span>${conv.message_count} messages</span>
        <span>${formatTimeAgo(conv.updated_at)}</span>
      </div>
    `;

    card.addEventListener("click", () => loadConversationMessages(conv.id));

    // Rename Button
    const editBtn = card.querySelector(".conv-action-btn.edit");
    editBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      startInlineRename(conv.id, conv.title);
    });

    // Delete Button
    const delBtn = card.querySelector(".conv-action-btn.delete");
    delBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteConversation(conv.id, conv.title);
    });

    elements.conversationsList.appendChild(card);
  });
}

function startInlineRename(convId, currentTitle) {
  const topElem = document.getElementById(`conv-top-${convId}`);
  if (!topElem) return;

  topElem.innerHTML = `
    <div class="conv-edit-row" onclick="event.stopPropagation()">
      <input type="text" class="conv-edit-input" value="${escapeHtml(currentTitle)}" id="rename-input-${convId}">
      <button class="conv-edit-btn" id="save-rename-${convId}" title="Save">✓</button>
      <button class="conv-edit-btn" id="cancel-rename-${convId}" title="Cancel">✕</button>
    </div>
  `;

  const input = document.getElementById(`rename-input-${convId}`);
  input.focus();
  input.select();

  const saveRename = async () => {
    const newTitle = input.value.trim();
    if (newTitle && newTitle !== currentTitle) {
      try {
        await apiRequest(`/api/conversations/${convId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: newTitle }),
        });
        showToast("Conversation renamed", "info");
      } catch (err) {
        showToast("Failed to rename conversation", "error");
      }
    }
    loadConversations(state.selectedDocument.id);
  };

  document.getElementById(`save-rename-${convId}`).addEventListener("click", saveRename);
  document.getElementById(`cancel-rename-${convId}`).addEventListener("click", () => {
    renderConversationsList();
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") saveRename();
    if (e.key === "Escape") renderConversationsList();
  });
}

async function loadConversationMessages(conversationId) {
  try {
    const detail = await apiRequest(`/api/conversations/${conversationId}`);
    state.activeConversationId = conversationId;
    state.messages = detail.messages.map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      citations: m.citations || [],
      confidence: m.confidence_score,
      latencyMs: m.latency_ms,
      subQueries: m.sub_queries || [],
      cached: m.cached,
    }));

    updateWorkspaceViews();
    renderConversationsList();
    renderMessages();
    scrollToBottom();
  } catch (err) {
    showToast("Failed to load conversation history", "error");
  }
}

function startNewChat() {
  state.activeConversationId = null;
  state.messages = [];
  updateWorkspaceViews();
  renderConversationsList();
  renderMessages();
}

async function deleteConversation(convId, title) {
  if (!confirm(`Delete conversation "${title}"?`)) return;

  try {
    await apiRequest(`/api/conversations/${convId}`, { method: "DELETE" });
    showToast("Conversation deleted", "info");
    if (state.activeConversationId === convId) {
      startNewChat();
    }
    if (state.selectedDocument) {
      loadConversations(state.selectedDocument.id);
    }
  } catch (err) {
    showToast("Failed to delete conversation", "error");
  }
}

// ─── Workspace View Updates ────────────────────────────────────────────────

function updateWorkspaceViews() {
  if (!state.selectedDocument) {
    // No document selected
    elements.activeDocBanner.style.display = "none";
    elements.chatNoDoc.style.display = "flex";
    elements.chatEmptyPrompt.style.display = "none";
    elements.chatInput.disabled = true;
    elements.chatInput.placeholder = "Select a document first...";
    elements.chatSendBtn.disabled = true;
    elements.messagesList.innerHTML = "";
    return;
  }

  // Document is selected
  elements.activeDocBanner.style.display = "flex";
  elements.activeDocName.textContent = state.selectedDocument.original_name;
  elements.chatNoDoc.style.display = "none";

  const isDocReady = state.selectedDocument.status === "ready";
  elements.chatInput.disabled = !isDocReady || state.isStreaming;
  elements.chatInput.placeholder = isDocReady
    ? `Ask a question about "${state.selectedDocument.original_name}"...`
    : `Document is ${state.selectedDocument.status}. Please wait...`;

  if (state.messages.length === 0 && !state.isStreaming) {
    elements.chatEmptyPrompt.style.display = "flex";
    elements.emptyDocTitle.textContent = state.selectedDocument.original_name;
    elements.emptyDocSubtitle.textContent = isDocReady
      ? "Ask questions, explore arguments, or request summaries."
      : `Document status: ${state.selectedDocument.status.toUpperCase()}. Waiting for processing to finish...`;
  } else {
    elements.chatEmptyPrompt.style.display = "none";
  }

  autoResizeInput();
}

// ─── Message Rendering ─────────────────────────────────────────────────────

function renderMessages() {
  elements.messagesList.innerHTML = "";

  state.messages.forEach((msg) => {
    const msgElem = createMessageElement(msg);
    elements.messagesList.appendChild(msgElem);
  });
}

function createMessageElement(msg) {
  const elem = document.createElement("div");
  elem.className = `message ${msg.role}`;
  elem.id = `msg-${msg.id}`;

  const isUser = msg.role === "user";
  const avatarSvg = isUser
    ? `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>`
    : `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="10" rx="2"></rect><circle cx="12" cy="5" r="2"></circle><path d="M12 7v4"></path><line x1="8" y1="16" x2="8" y2="16"></line><line x1="16" y1="16" x2="16" y2="16"></line></svg>`;

  let citationsHtml = "";
  if (!isUser && msg.citations && msg.citations.length > 0) {
    const items = msg.citations
      .map(
        (c, idx) => `
        <div class="citation-item">
          <span class="citation-badge">${idx + 1}</span>
          <div>
            <div class="citation-text">${escapeHtml(c.text_snippet ? c.text_snippet.substring(0, 200) : "")}...</div>
            <div class="citation-page">
              Page ${c.page_number || (c.page_numbers && c.page_numbers[0]) || "?"} · Relevance: ${Math.round((c.relevance_score || 0) * 100)}%
            </div>
          </div>
        </div>
      `
      )
      .join("");

    citationsHtml = `
      <div class="citations-panel">
        <div class="citations-title">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
          Sources & Citations (${msg.citations.length})
        </div>
        ${items}
      </div>
    `;
  }

  let metaHtml = "";
  if (!isUser) {
    const metaTags = [];

    if (msg.confidence != null) {
      let confClass = "confidence-low";
      if (msg.confidence >= 0.8) confClass = "confidence-high";
      else if (msg.confidence >= 0.6) confClass = "confidence-medium";

      metaTags.push(`
        <span class="meta-tag ${confClass}">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="6"></circle><circle cx="12" cy="12" r="2"></circle></svg>
          ${Math.round(msg.confidence * 100)}% confidence
        </span>
      `);
    }

    if (msg.latencyMs != null) {
      metaTags.push(`
        <span class="meta-tag">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
          ${msg.latencyMs}ms
        </span>
      `);
    }

    if (msg.cached) {
      metaTags.push(`
        <span class="meta-tag confidence-high">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="21 8 21 21 3 21 3 8"></polyline><rect x="1" y="3" width="22" height="5"></rect><line x1="10" y1="12" x2="14" y2="12"></line></svg>
          Cached
        </span>
      `);
    }

    if (metaTags.length > 0) {
      metaHtml = `<div class="message-meta">${metaTags.join("")}</div>`;
    }
  }

  let subQueriesHtml = "";
  if (!isUser && msg.subQueries && msg.subQueries.length > 1) {
    const pills = msg.subQueries
      .map((sq) => `<span class="sub-query-pill">${escapeHtml(sq)}</span>`)
      .join("");
    subQueriesHtml = `<div class="sub-queries-row">${pills}</div>`;
  }

  const contentHtml = isUser ? escapeHtml(msg.content) : renderMarkdown(msg.content);

  elem.innerHTML = `
    <div class="message-avatar">${avatarSvg}</div>
    <div class="message-body">
      <div class="message-content">${contentHtml}</div>
      ${citationsHtml}
      ${metaHtml}
      ${subQueriesHtml}
    </div>
  `;

  return elem;
}

// ─── Query Submission & SSE Stream Engine ──────────────────────────────────

async function submitQuery() {
  const query = elements.chatInput.value.trim();
  if (!query || !state.selectedDocument || state.isStreaming) return;

  if (state.selectedDocument.status !== "ready") {
    showToast(`Document is not ready yet (${state.selectedDocument.status}). Please wait.`, "error");
    return;
  }

  // Clear input & prompt
  elements.chatInput.value = "";
  autoResizeInput();
  elements.chatEmptyPrompt.style.display = "none";

  // Append user message
  const userMsgId = "user_" + Date.now();
  const userMsg = {
    id: userMsgId,
    role: "user",
    content: query,
  };
  state.messages.push(userMsg);
  elements.messagesList.appendChild(createMessageElement(userMsg));
  scrollToBottom();

  // Set streaming UI state
  state.isStreaming = true;
  elements.chatSendBtn.style.display = "none";
  elements.chatStopBtn.style.display = "flex";
  elements.chatInput.disabled = true;

  elements.streamingBubble.style.display = "flex";
  elements.streamingPhaseText.textContent = "🔍 Analyzing query...";
  elements.streamingPartialAnswer.style.display = "none";
  elements.streamingPartialAnswer.innerHTML = "";
  scrollToBottom();

  const controller = new AbortController();
  state.streamAbortController = controller;

  let streamAnswer = "";
  let streamCitations = [];
  let streamConfidence = null;
  let streamLatency = null;
  let streamCached = false;
  let streamSubQueries = [];
  let streamConvId = state.activeConversationId;

  try {
    const response = await fetch("/api/query", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": GLOBAL_USER_ID,
      },
      body: JSON.stringify({
        query: query,
        document_id: state.selectedDocument.id,
        conversation_id: state.activeConversationId || null,
        stream: true,
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      let errDetail = `Server error ${response.status}`;
      try {
        const errJson = await response.json();
        errDetail = errJson.detail || errDetail;
      } catch {}
      throw new Error(errDetail);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      let currentEvent = "";
      for (const line of lines) {
        if (line.startsWith("event: ")) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          const rawData = line.slice(6).trim();
          try {
            const data = JSON.parse(rawData);
            handleStreamEvent(currentEvent, data);
          } catch (e) {
            // Malformed JSON chunk
          }
        }
      }
    }

    function handleStreamEvent(event, data) {
      switch (event) {
        case "planning":
          elements.streamingPhaseText.textContent = "🔍 Analyzing query intent...";
          break;
        case "planned":
          elements.streamingPhaseText.textContent = "📋 Query plan decomposed";
          streamSubQueries = data.sub_queries || [];
          break;
        case "retrieving":
          elements.streamingPhaseText.textContent = "Searching Pgvector & BM25 index...";
          break;
        case "retrieved":
          elements.streamingPhaseText.textContent = `Retrieved ${data.chunk_count || 0} context passages`;
          break;
        case "generating":
          elements.streamingPhaseText.textContent = "Synthesizing answer & citations...";
          break;
        case "token":
          if (data.token) {
            streamAnswer += data.token;
            elements.streamingPartialAnswer.style.display = "block";
            elements.streamingPartialAnswer.innerHTML = renderMarkdown(streamAnswer);
            scrollToBottom();
          }
          break;
        case "critiquing":
          elements.streamingPhaseText.textContent = "Evaluating answer faithfulness & precision...";
          break;
        case "critiqued":
          elements.streamingPhaseText.textContent = `Self-critique confidence: ${Math.round((data.confidence || 0) * 100)}%`;
          break;
        case "re_retrieving":
          elements.streamingPhaseText.textContent = "Confidence low — re-retrieving with refined query...";
          break;
        case "complete":
          if (data.answer) streamAnswer = data.answer;
          streamCitations = data.citations || [];
          streamConfidence = data.confidence_score;
          streamLatency = data.latency_ms;
          streamCached = Boolean(data.cached);
          streamSubQueries = data.sub_queries || streamSubQueries;
          if (data.conversation_id) {
            streamConvId = data.conversation_id;
          }
          break;
        case "error":
          throw new Error(data.detail || data.error || "Streaming pipeline error");
      }
    }

    // Finalize assistant message
    const assistantMsg = {
      id: "assistant_" + Date.now(),
      role: "assistant",
      content: streamAnswer || "No answer generated.",
      citations: streamCitations,
      confidence: streamConfidence,
      latencyMs: streamLatency,
      cached: streamCached,
      subQueries: streamSubQueries,
    };

    state.messages.push(assistantMsg);
    elements.messagesList.appendChild(createMessageElement(assistantMsg));

    if (streamConvId && !state.activeConversationId) {
      state.activeConversationId = streamConvId;
    }

    // Refresh conversations list to update titles/counts
    if (state.selectedDocument) {
      loadConversations(state.selectedDocument.id);
    }

    // Refresh query usage stats
    loadUsage();
  } catch (err) {
    if (err.name === "AbortError") {
      showToast("Response generation stopped", "info");
      if (streamAnswer) {
        const partialMsg = {
          id: "assistant_" + Date.now(),
          role: "assistant",
          content: streamAnswer + " *(generation stopped)*",
          citations: streamCitations,
          confidence: null,
          latencyMs: null,
          cached: false,
          subQueries: streamSubQueries,
        };
        state.messages.push(partialMsg);
        elements.messagesList.appendChild(createMessageElement(partialMsg));
      }
    } else {
      showToast(err.message || "Failed to generate answer", "error");
      const errElem = document.createElement("div");
      errElem.className = "message assistant";
      errElem.innerHTML = `
        <div class="message-avatar">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--color-error)" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
        </div>
        <div class="message-body">
          <div class="message-content" style="color: var(--color-error);">
            Error: ${escapeHtml(err.message)}
          </div>
        </div>
      `;
      elements.messagesList.appendChild(errElem);
    }
  } finally {
    state.isStreaming = false;
    state.streamAbortController = null;
    elements.streamingBubble.style.display = "none";
    elements.chatSendBtn.style.display = "flex";
    elements.chatStopBtn.style.display = "none";
    elements.chatInput.disabled = false;
    elements.chatInput.focus();
    autoResizeInput();
    scrollToBottom();
  }
}

function abortCurrentStream() {
  if (state.streamAbortController) {
    state.streamAbortController.abort();
  }
}

// ─── Usage Quotas & Tier Management ─────────────────────────────────────────

async function loadUsage(showToastOnRefresh = false) {
  try {
    const usage = await apiRequest("/api/usage");
    const isPro = usage.tier === "pro";

    elements.tierName.textContent = isPro ? "Pro Plan" : "Free Plan";
    elements.tierBadge.className = `tier-badge ${isPro ? "pro" : ""}`;

    if (isPro) {
      elements.usageText.textContent = "Unlimited queries";
      elements.usageProgressBar.style.width = "100%";
      elements.usageProgressBar.className = "progress-bar-fill";
      elements.tierToggleBtn.textContent = "Downgrade to Free (Demo)";
      elements.tierToggleBtn.className = "upgrade-btn downgrade";
    } else {
      const used = usage.daily_used || 0;
      const limit = usage.daily_limit || 10;
      const pct = Math.min(100, Math.round((used / limit) * 100));

      elements.usageText.textContent = `${used} / ${limit} queries today`;
      elements.usageProgressBar.style.width = `${pct}%`;

      if (pct >= 90) {
        elements.usageProgressBar.className = "progress-bar-fill danger";
      } else if (pct >= 70) {
        elements.usageProgressBar.className = "progress-bar-fill warning";
      } else {
        elements.usageProgressBar.className = "progress-bar-fill";
      }

      elements.tierToggleBtn.textContent = "Upgrade to Pro";
      elements.tierToggleBtn.className = "upgrade-btn";
    }

    if (showToastOnRefresh) {
      showToast("Usage quota refreshed", "info");
    }
  } catch (e) {
    console.warn("Failed to load usage", e);
  }
}

async function handleTierToggle() {
  const currentIsPro = elements.tierName.textContent.includes("Pro");
  const targetTier = currentIsPro ? "free" : "pro";

  elements.tierToggleBtn.disabled = true;
  elements.tierToggleBtn.textContent = "Updating...";

  try {
    await apiRequest("/api/usage/upgrade", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tier: targetTier }),
    });

    showToast(
      targetTier === "pro"
        ? "Upgraded to Pro Plan (Unlimited queries enabled)"
        : "Reverted to Free Plan",
      "success"
    );
    await loadUsage();
  } catch (err) {
    showToast(err.message || "Failed to update subscription plan", "error");
  } finally {
    elements.tierToggleBtn.disabled = false;
  }
}
