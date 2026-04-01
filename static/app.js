/* ── DOM refs ─────────────────────────────────── */
const chatEl = document.getElementById('chat');
const emptyEl = document.getElementById('empty-state');
const inputAreaEl = document.getElementById('input-area');
const toastEl = document.getElementById('toast');
const headerTitle = document.getElementById('header-title');
const headerTitleInput = document.getElementById('header-title-input');
const sessionListEl = document.getElementById('session-list');
const newChatBtn = document.getElementById('new-chat-btn');
const toggleSidebarBtn = document.getElementById('toggle-sidebar-btn');
const sidebar = document.getElementById('sidebar');

const settingsOverlay = document.getElementById('settings-overlay');
const openSettingsBtn = document.getElementById('open-settings-btn');
const closeSettingsBtn = document.getElementById('close-settings-btn');
const toggleStreaming = document.getElementById('toggle-streaming');

const confirmOverlay = document.getElementById('confirm-overlay');
const cancelConfirm = document.getElementById('cancel-confirm');
const doConfirm = document.getElementById('do-confirm');

// Two input surfaces: landing (empty-state) and chat-mode bottom bar
const inputElLanding = document.getElementById('message-input');
const sendBtnLanding = document.getElementById('send-btn');
const inputElChat = document.getElementById('message-input-chat');
const sendBtnChat = document.getElementById('send-btn-chat');

// Unified accessors — always point at whichever is active
function inputEl() { return emptyEl.classList.contains('hidden') ? inputElChat : inputElLanding; }
function sendBtn() { return emptyEl.classList.contains('hidden') ? sendBtnChat : sendBtnLanding; }

/* ── Mode switching ───────────────────────────── */
function enterChatMode() {
  emptyEl.classList.add('hidden');
  chatEl.classList.add('active');
  inputAreaEl.classList.add('active');
  inputElChat.value = '';
  inputElChat.style.height = 'auto';
  inputElChat.focus();
}

function enterLandingMode() {
  emptyEl.classList.remove('hidden');
  chatEl.classList.remove('active');
  inputAreaEl.classList.remove('active');
  inputElLanding.value = '';
  inputElLanding.style.height = 'auto';
  inputElLanding.focus();
}

/* ── State ────────────────────────────────────── */
let currentSessionId = null;
let isWaiting = false;
let confirmCallback = null;

/* ── Prefs (localStorage) ─────────────────────── */
const PREFS_KEY = 'unai_prefs';
function loadPrefs() { try { return JSON.parse(localStorage.getItem(PREFS_KEY)) || {}; } catch { return {}; } }
function savePrefs(p) { localStorage.setItem(PREFS_KEY, JSON.stringify(p)); }

function applyPrefs() {
  const p = loadPrefs();
  setTheme(p.theme || 'dark', false);
  toggleStreaming.checked = p.streaming !== false;
}

/* ── Theme ────────────────────────────────────── */
function setTheme(t, persist = true) {
  document.documentElement.setAttribute('data-theme', t);
  document.getElementById('theme-dark').classList.toggle('selected', t === 'dark');
  document.getElementById('theme-light').classList.toggle('selected', t === 'light');
  if (persist) { const p = loadPrefs(); p.theme = t; savePrefs(p); }
}

/* ── Toast ────────────────────────────────────── */
let toastTimer;
function showToast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove('show'), 2200);
}

/* ── Confirm dialog ───────────────────────────── */
function showConfirm(title, body, cb) {
  document.getElementById('confirm-title').textContent = title;
  document.getElementById('confirm-body').textContent = body;
  confirmCallback = cb;
  confirmOverlay.classList.add('open');
}
cancelConfirm.addEventListener('click', () => confirmOverlay.classList.remove('open'));
confirmOverlay.addEventListener('click', e => { if (e.target === confirmOverlay) confirmOverlay.classList.remove('open'); });
doConfirm.addEventListener('click', () => {
  confirmOverlay.classList.remove('open');
  if (confirmCallback) { confirmCallback(); confirmCallback = null; }
});

/* ── Settings panel ───────────────────────────── */
openSettingsBtn.addEventListener('click', () => settingsOverlay.classList.add('open'));
closeSettingsBtn.addEventListener('click', () => settingsOverlay.classList.remove('open'));
settingsOverlay.addEventListener('click', e => { if (e.target === settingsOverlay) settingsOverlay.classList.remove('open'); });
toggleStreaming.addEventListener('change', () => { const p = loadPrefs(); p.streaming = toggleStreaming.checked; savePrefs(p); });

/* ── Sidebar toggle ───────────────────────────── */
toggleSidebarBtn.addEventListener('click', () => sidebar.classList.toggle('collapsed'));

/* ── Header title rename ──────────────────────── */
function startRenameHeader() {
  if (!currentSessionId) return;
  headerTitle.classList.add('hidden');
  headerTitleInput.value = headerTitle.textContent;
  headerTitleInput.classList.add('active');
  headerTitleInput.focus();
  headerTitleInput.select();
}

async function commitRenameHeader() {
  const newTitle = headerTitleInput.value.trim();
  headerTitleInput.classList.remove('active');
  headerTitle.classList.remove('hidden');
  if (!newTitle || !currentSessionId) return;
  if (newTitle === headerTitle.textContent) return;
  try {
    const res = await fetch(`/api/sessions/${currentSessionId}/rename`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newTitle }),
    });
    const data = await res.json();
    if (data.ok) {
      headerTitle.textContent = data.title;
      loadSessionList();
      showToast('Renamed');
    }
  } catch { showToast('Rename failed'); }
}

headerTitle.addEventListener('dblclick', startRenameHeader);
headerTitleInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); commitRenameHeader(); }
  if (e.key === 'Escape') { headerTitleInput.classList.remove('active'); headerTitle.classList.remove('hidden'); }
});
headerTitleInput.addEventListener('blur', commitRenameHeader);

/* ── Session list ─────────────────────────────── */
async function loadSessionList() {
  try {
    const res = await fetch('/api/sessions');
    const list = await res.json();
    renderSessionList(list);
  } catch { /* silent */ }
}

function renderSessionList(list) {
  sessionListEl.innerHTML = '';
  if (list.length === 0) {
    sessionListEl.innerHTML = '<div style="padding:16px 12px;font-size:11px;color:var(--muted)">No history</div>';
    return;
  }
  const today = new Date().toDateString();
  const yesterday = new Date(Date.now() - 86400000).toDateString();
  const groups = {};
  list.forEach(s => {
    const d = s.updated_at ? new Date(s.updated_at).toDateString() : '';
    const label = d === today ? 'Today' : d === yesterday ? 'Yesterday' : (d || 'Earlier');
    (groups[label] = groups[label] || []).push(s);
  });
  Object.entries(groups).forEach(([label, items]) => {
    const gl = document.createElement('div');
    gl.className = 'session-group-label';
    gl.textContent = label;
    sessionListEl.appendChild(gl);
    items.forEach(s => {
      const el = document.createElement('div');
      el.className = 'session-item' + (s.id === currentSessionId ? ' active' : '');
      el.dataset.id = s.id;
      el.innerHTML = `
        <span class="session-title">${escHtml(s.title)}</span>
        <div class="session-actions">
          <button class="session-rename" title="Rename" data-id="${s.id}">
            <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
              <path d="M7.5 1.5l2 2L2 11H0V9L7.5 1.5z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>
            </svg>
          </button>
          <button class="session-delete" title="Delete" data-id="${s.id}">
            <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
              <path d="M1 1l9 9M10 1L1 10" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
            </svg>
          </button>
        </div>
      `;
      el.addEventListener('click', () => loadSession(s.id));
      el.querySelector('.session-rename').addEventListener('click', e => {
        e.stopPropagation();
        startRenameInline(s.id, el, s.title);
      });
      el.querySelector('.session-delete').addEventListener('click', e => {
        e.stopPropagation();
        showConfirm('Delete chat', `Chat "${s.title}" will be permanently deleted.`, () => deleteSession(s.id));
      });
      sessionListEl.appendChild(el);
    });
  });
}

/* インライン rename（セッションリスト内） */
function startRenameInline(sessionId, itemEl, currentTitle) {
  const titleEl = itemEl.querySelector('.session-title');
  const inp = document.createElement('input');
  inp.className = 'session-rename-input';
  inp.value = currentTitle;
  inp.maxLength = 80;
  titleEl.replaceWith(inp);
  inp.focus();
  inp.select();

  async function commit() {
    const newTitle = inp.value.trim();
    inp.replaceWith(titleEl);
    if (!newTitle || newTitle === currentTitle) return;
    try {
      const res = await fetch(`/api/sessions/${sessionId}/rename`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle }),
      });
      const data = await res.json();
      if (data.ok) {
        titleEl.textContent = data.title;
        if (sessionId === currentSessionId) headerTitle.textContent = data.title;
        showToast('Renamed');
      }
    } catch { showToast('Rename failed'); }
  }

  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); commit(); }
    if (e.key === 'Escape') { inp.replaceWith(titleEl); }
  });
  inp.addEventListener('blur', commit);
}

async function deleteSession(id) {
  if (id === currentSessionId) {
    const picker = chatEl.querySelector('.candidate-picker');
    if (picker && picker._autoResolve) picker._autoResolve();
  }
  await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
  if (id === currentSessionId) {
    currentSessionId = null;
    clearChat();
    headerTitle.textContent = 'New Chat';  // ← タイトルをリセット
  }
  loadSessionList();
  showToast('Chat deleted');
}

/* ── Load session ─────────────────────────────── */
async function loadSession(id) {
  const picker = chatEl.querySelector('.candidate-picker');
  if (picker && picker._autoResolve) picker._autoResolve();
  try {
    const res = await fetch(`/api/sessions/${id}`);
    const sess = await res.json();

    while (chatEl.firstChild) chatEl.removeChild(chatEl.firstChild);
    currentSessionId = id;
    headerTitle.textContent = sess.title || 'New Chat';

    if (sess.turns && sess.turns.length > 0) {
      enterChatMode();
      sess.turns.forEach(t => renderTurn(t, false));
      scrollBottom();
    } else {
      enterLandingMode();
    }

    document.querySelectorAll('.session-item').forEach(el => {
      el.classList.toggle('active', el.dataset.id === id);
    });
  } catch { showToast('Failed to load session'); }
}

/* ── New chat ─────────────────────────────────── */
newChatBtn.addEventListener('click', () => {
  if (!currentSessionId) return;
  const picker = chatEl.querySelector('.candidate-picker');
  if (picker && picker._autoResolve) picker._autoResolve();
  currentSessionId = null;
  clearChat();
  headerTitle.textContent = 'New Chat';  // ← タイトルをリセット
  document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
});

/* ── Clear chat view ──────────────────────────── */
function clearChat(showLanding = true) {
  while (chatEl.firstChild) chatEl.removeChild(chatEl.firstChild);
  if (showLanding) enterLandingMode();
}

/* ══════════════════════════════════════════════════
   TURN RENDERING
   Each "turn" = { turn_id, branch, branch_index, branch_count }
   branch = { id, user:{content,ts}, bot:{content,skill,...} }
══════════════════════════════════════════════════ */

function renderTurn(turnData, stream = false, skipUser = false) {
  const { turn_id, branch, branch_index, branch_count } = turnData;

  // ── user message ──
  let userBubble;
  let userMsg;
  if (!skipUser) {
    userMsg = document.createElement('div');
    userMsg.className = 'msg user';
    userMsg.dataset.turnId = turn_id;
    userBubble = document.createElement('div');
    userBubble.className = 'bubble';
    userBubble.textContent = branch.user.content;
    userMsg.appendChild(userBubble);
    chatEl.appendChild(userMsg);
  } else {
    // Find the most recent user message (should be the one we just created)
    const userMessages = chatEl.querySelectorAll('.msg.user');
    userMsg = userMessages.length > 0 ? userMessages[userMessages.length - 1] : null;
    userBubble = userMsg ? userMsg.querySelector('.bubble') : null;
  }

  // ── user action bar (edit button only) ──
  if (userMsg && userBubble) {
    const userActionBar = buildUserActionBar(turn_id, userBubble, userMsg);
    chatEl.insertBefore(userActionBar, userMsg.nextSibling);
  }

  // ── bot message ──
  const botMsg = document.createElement('div');
  botMsg.className = 'msg bot';
  botMsg.dataset.turnId = turn_id;
  const botBubble = document.createElement('div');
  botBubble.className = 'bubble';
  botMsg.appendChild(botBubble);
  const metaEl = buildMetaEl(branch.bot);
  botMsg.appendChild(metaEl);

  chatEl.appendChild(botMsg);

  // ── bot action bar (copy, regenerate, branch nav) ──
  const botActionBar = buildBotActionBar(turn_id, branch_index, branch_count, userBubble, botBubble, metaEl, botMsg);
  chatEl.insertBefore(botActionBar, botMsg.nextSibling);

  // Fill bot content (stream or instant)
  if (stream) {
    typeText(botBubble, branch.bot.content);
  } else {
    botBubble.textContent = branch.bot.content;
  }
}

/* ── Build user action bar (edit button only) ──────────────────────────── */
function buildUserActionBar(turn_id, userBubble, userMsg) {
  const actionBar = document.createElement('div');
  actionBar.className = 'turn-actions user-actions';
  actionBar.dataset.turnId = turn_id;

  const editBtn = makeActionBtn(
    `<svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <path d="M8.5 1.5l2 2L3 11H1v-2L8.5 1.5z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
    </svg>Edit`,
    () => startEdit(turn_id, userBubble, null, null, actionBar)
  );
  actionBar.appendChild(editBtn);

  // Hover wiring for user message
  let hoverCount = 0;
  const showActions = () => { hoverCount++; actionBar.classList.add('visible'); };
  const hideActions = () => { hoverCount = Math.max(0, hoverCount - 1); if (hoverCount === 0) actionBar.classList.remove('visible'); };
  [userMsg, actionBar].forEach(el => {
    el.addEventListener('mouseenter', showActions);
    el.addEventListener('mouseleave', hideActions);
  });

  return actionBar;
}

/* ── Build bot action bar (copy, regenerate, branch nav) ─────────────────── */
function buildBotActionBar(turn_id, branchIndex, branchCount, userBubble, botBubble, metaEl, botMsg) {
  const actionBar = document.createElement('div');
  actionBar.className = 'turn-actions';
  actionBar.dataset.turnId = turn_id;

  const nav = document.createElement('div');
  nav.className = 'branch-nav';
  nav.dataset.turnId = turn_id;
  updateBranchNav(nav, branchIndex, branchCount, turn_id, userBubble, botBubble, metaEl);
  actionBar.appendChild(nav);

  const copyBtn = makeActionBtn(
    `<svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <rect x="4" y="4" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.2"/>
      <path d="M1 8V2a1 1 0 0 1 1-1h6" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
    </svg>Copy`,
    async () => { await navigator.clipboard.writeText(botBubble.textContent); showToast('Copied'); }
  );
  actionBar.appendChild(copyBtn);

  const regenBtn = makeActionBtn(
    `<svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <path d="M1.5 6A4.5 4.5 0 1 0 3 2.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
      <polyline points="1,1 1,3.5 3.5,3.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>Regenerate`,
    () => regenerateTurn(turn_id, actionBar, userBubble, botBubble, metaEl)
  );
  actionBar.appendChild(regenBtn);

  // Hover wiring for bot message
  let hoverCount = 0;
  const showActions = () => { hoverCount++; actionBar.classList.add('visible'); };
  const hideActions = () => { hoverCount = Math.max(0, hoverCount - 1); if (hoverCount === 0) actionBar.classList.remove('visible'); };
  [botMsg, actionBar].forEach(el => {
    el.addEventListener('mouseenter', showActions);
    el.addEventListener('mouseleave', hideActions);
  });

  return actionBar;
}

function makeActionBtn(innerHTML, onClick) {
  const btn = document.createElement('button');
  btn.className = 'action-btn';
  btn.innerHTML = innerHTML;
  btn.addEventListener('click', onClick);
  return btn;
}

/* ── Branch navigator ─────────────────────────── */
function updateBranchNav(nav, branchIndex, branchCount, turn_id, userBubble, botBubble, metaEl) {
  nav.innerHTML = '';
  if (branchCount <= 1) return;

  const prev = document.createElement('button');
  prev.className = 'branch-nav-btn';
  prev.innerHTML = `<svg width="8" height="8" viewBox="0 0 8 8" fill="none"><path d="M5 1L2 4l3 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  prev.disabled = branchIndex === 0;
  prev.addEventListener('click', () => switchBranch(turn_id, branchIndex - 1, nav, userBubble, botBubble, metaEl));

  const label = document.createElement('span');
  label.className = 'branch-label';
  label.textContent = `${branchIndex + 1}/${branchCount}`;

  const next = document.createElement('button');
  next.className = 'branch-nav-btn';
  next.innerHTML = `<svg width="8" height="8" viewBox="0 0 8 8" fill="none"><path d="M3 1l3 3-3 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  next.disabled = branchIndex === branchCount - 1;
  next.addEventListener('click', () => switchBranch(turn_id, branchIndex + 1, nav, userBubble, botBubble, metaEl));

  nav.appendChild(prev);
  nav.appendChild(label);
  nav.appendChild(next);
}

/* ── Switch branch ────────────────────────────── */
async function switchBranch(turn_id, newIndex, nav, userBubble, botBubble, metaEl) {
  if (!currentSessionId || isWaiting) return;
  try {
    const res = await fetch('/api/chat/switch_branch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentSessionId, turn_id, branch_index: newIndex }),
    });
    const data = await res.json();
    userBubble.textContent = data.user_content;
    botBubble.textContent = data.bot.content;
    updateMetaEl(metaEl, data.bot);
    updateBranchNav(nav, data.branch_index, data.branch_count, turn_id, userBubble, botBubble, metaEl);
  } catch { showToast('Failed to switch branch'); }
}

/* ── Regenerate ───────────────────────────────── */
async function regenerateTurn(turn_id, bar, userBubble, botBubble, metaEl) {
  if (!currentSessionId || isWaiting) return;
  isWaiting = true;

  botBubble.innerHTML = '';
  const ind = document.createElement('div');
  ind.className = 'typing-indicator';
  ind.innerHTML = '<span></span><span></span><span></span>';
  botBubble.appendChild(ind);

  const regenStart = performance.now();
  try {
    const res = await fetch('/api/chat/regenerate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentSessionId, turn_id }),
    });
    const data = await res.json();
    data.wallMs = Math.round(performance.now() - regenStart);
    botBubble.innerHTML = '';
    const nav = bar.querySelector('.branch-nav');
    updateBranchNav(nav, data.branch_index, data.branch_count, turn_id, userBubble, botBubble, metaEl);
    updateMetaEl(metaEl, data);
    if (toggleStreaming.checked) await typeText(botBubble, data.response);
    else botBubble.textContent = data.response;
  } catch { botBubble.textContent = 'Regeneration failed.'; }

  isWaiting = false;
}

/* ── Edit user message ────────────────────────── */
function startEdit(turn_id, userBubble, botBubble, metaEl, actionBar) {
  if (isWaiting) return;

  // Find bot message elements if not provided
  if (!botBubble || !metaEl) {
    const botMsg = document.querySelector(`.msg.bot[data-turn-id="${turn_id}"]`);
    if (botMsg) {
      botBubble = botBubble || botMsg.querySelector('.bubble');
      metaEl = metaEl || botMsg.querySelector('.turn-meta');
    }
  }

  const original = userBubble.textContent;
  const textarea = document.createElement('textarea');
  textarea.className = 'user-edit-area';
  textarea.value = original;
  userBubble.replaceWith(textarea);
  textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
  textarea.focus();
  textarea.addEventListener('input', () => {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
  });

  const row = document.createElement('div');
  row.className = 'edit-confirm-row';
  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'btn-edit-cancel';
  cancelBtn.textContent = 'Cancel';
  cancelBtn.addEventListener('click', () => { textarea.replaceWith(userBubble); row.remove(); });
  const sendEditBtn = document.createElement('button');
  sendEditBtn.className = 'btn-edit-send';
  sendEditBtn.textContent = 'Send';
  sendEditBtn.addEventListener('click', () => submitEdit(turn_id, textarea, userBubble, botBubble, metaEl, actionBar, row));

  textarea.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitEdit(turn_id, textarea, userBubble, botBubble, metaEl, actionBar, row); }
    if (e.key === 'Escape') { textarea.replaceWith(userBubble); row.remove(); }
  });

  row.appendChild(cancelBtn);
  row.appendChild(sendEditBtn);
  textarea.parentElement.appendChild(row);
}

async function submitEdit(turn_id, textarea, userBubble, botBubble, metaEl, actionBar, row) {
  const newText = textarea.value.trim();
  if (!newText || isWaiting) return;
  isWaiting = true;

  userBubble.textContent = newText;
  textarea.replaceWith(userBubble);
  row.remove();

  // Find bot message elements if not provided
  if (!botBubble || !metaEl) {
    const botMsg = document.querySelector(`.msg.bot[data-turn-id="${turn_id}"]`);
    if (botMsg) {
      botBubble = botBubble || botMsg.querySelector('.bubble');
      metaEl = metaEl || botMsg.querySelector('.turn-meta');
    }
  }

  // Find the bot action bar for branch navigation updates
  const botActionBar = document.querySelector(`.turn-actions:not(.user-actions)[data-turn-id="${turn_id}"]`);

  botBubble.innerHTML = '';
  const ind = document.createElement('div');
  ind.className = 'typing-indicator';
  ind.innerHTML = '<span></span><span></span><span></span>';
  botBubble.appendChild(ind);

  const editStart = performance.now();
  try {
    const res = await fetch('/api/chat/edit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentSessionId, turn_id, message: newText }),
    });
    const data = await res.json();
    data.wallMs = Math.round(performance.now() - editStart);

    if (data.truncated_after) removeTurnsAfter(turn_id);

    const editRow = document.querySelector('.edit-confirm-row');
    if (editRow) editRow.remove();

    botBubble.innerHTML = '';
    const nav = botActionBar ? botActionBar.querySelector('.branch-nav') : null;

    console.log('Debug - botBubble:', botBubble);
    console.log('Debug - metaEl:', metaEl);
    console.log('Debug - nav:', nav);
    console.log('Debug - data:', data);

    if (nav) {
      updateBranchNav(nav, data.branch_index, data.branch_count, turn_id, userBubble, botBubble, metaEl);
    }
    if (metaEl) {
      updateMetaEl(metaEl, data);
    }
    if (toggleStreaming.checked) await typeText(botBubble, data.response || data.bot_response || data.answer || data.text);
    else botBubble.textContent = data.response || data.bot_response || data.answer || data.text || 'No response received';

    loadSessionList();
  } catch (error) {
    console.error('Edit failed:', error);
    botBubble.textContent = 'Edit failed: ' + (error.message || 'Unknown error');
  }

  isWaiting = false;
}

/* Remove all DOM turn elements after a given turn_id */
function removeTurnsAfter(turn_id) {
  const remaining = Array.from(chatEl.children);
  let removing = false;
  for (const el of remaining) {
    if (removing) {
      chatEl.removeChild(el);
    }
    else if (el.classList.contains('turn-actions') &&
      el.dataset.turnId === turn_id &&
      !el.classList.contains('user-actions')) {
      removing = true;
    }
  }
}

/* ══════════════════════════════════════════════════
   SKILL PROGRESS INDICATOR
   Shows which skill is being tested / called during generation.
══════════════════════════════════════════════════ */

function createProgressEl() {
  const wrap = document.createElement('div');
  wrap.className = 'msg bot skill-progress-wrap';
  const inner = document.createElement('div');
  inner.className = 'skill-progress';
  wrap.appendChild(inner);
  chatEl.appendChild(wrap);
  scrollBottom();
  return { wrap, inner };
}

function setProgress(inner, phase, skill) {
  if (phase === 'matching') {
    inner.textContent = `checking ${skill}…`;
  } else if (phase === 'responding') {
    inner.textContent = `${skill} ›`;
  }
}

/* ── Send message (SSE) ───────────────────────── */
async function send() {
  const text = inputEl().value.trim();
  if (!text || isWaiting) return;

  let isNewSession = false;
  if (!currentSessionId) {
    try {
      const res = await fetch('/api/sessions', { method: 'POST' });
      const data = await res.json();
      currentSessionId = data.id;
      isNewSession = true;
    } catch { /* ignore */ }
  }

  isWaiting = true;

  if (!emptyEl.classList.contains('hidden')) enterChatMode();

  inputEl().value = '';
  inputEl().style.height = 'auto';
  sendBtn().classList.remove('active');

  // Show user bubble immediately (kept permanently)
  const userMsgEl = document.createElement('div');
  userMsgEl.className = 'msg user';
  const userBubbleEl = document.createElement('div');
  userBubbleEl.className = 'bubble';
  userBubbleEl.textContent = text;
  userMsgEl.appendChild(userBubbleEl);
  chatEl.appendChild(userMsgEl);

  // Progress spinner (removed once matched_skills arrives)
  const { wrap: progressWrap, inner: progressInner } = createProgressEl();
  progressInner.textContent = 'matching skills\u2026';
  scrollBottom();

  let pickerEl = null;
  let candidates = [];
  let sseOutcome = null;
  let committedData = null;
  const sendTime = performance.now();

  try {
    const res = await fetch('/api/chat/sse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, session_id: currentSessionId || '' }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';

    outer: while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const event = JSON.parse(line.slice(6));

        if (event.phase === 'matched_skills') {
          progressWrap.remove();
          if (event.skills.length > 1) {
            pickerEl = buildCandidatePickerSkeleton(event.skills);
            chatEl.appendChild(pickerEl);
            scrollBottom();
          }

        } else if (event.phase === 'candidate') {
          const cand = { ...event };
          delete cand.phase;
          cand.wallMs = Math.round(performance.now() - sendTime);
          candidates.push(cand);
          if (pickerEl) {
            // Setup early selection if this is the first candidate
            if (candidates.length === 1) {
              setupEarlySelection(pickerEl, candidates, async (result) => {
                pickerEl.remove();
                try {
                  await fetch('/api/chat/commit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: currentSessionId, message: text, result }),
                  });
                } catch { /* non-fatal */ }
                try {
                  const sr = await fetch(`/api/sessions/${currentSessionId}`);
                  const sess = await sr.json();
                  const lastTurn = sess.turns[sess.turns.length - 1];
                  if (lastTurn && lastTurn.branch.user.content === text) {
                    renderTurn(lastTurn, toggleStreaming.checked, true);
                  } else {
                    appendMsgFallback('bot', result.response, result);
                  }
                  if (isNewSession && sess.title) headerTitle.textContent = sess.title;
                  loadSessionList();
                } catch {
                  appendMsgFallback('bot', result.response, result);
                }
                isWaiting = false;
                inputElChat.focus();
              });
            }
            fillCandidateCard(pickerEl, cand, candidates, pickerEl._onResolve);
          }

        } else if (event.phase === 'committed') {
          committedData = { ...event };
          delete committedData.phase;
          committedData.wallMs = Math.round(performance.now() - sendTime);
          sseOutcome = 'committed';
          break outer;

        } else if (event.phase === 'pick') {
          sseOutcome = 'pick';
          break outer;

        } else if (event.phase === 'no_match') {
          sseOutcome = 'no_match';
          break outer;
        }
      }
    }

  } catch (err) {
    progressWrap.remove();
    if (pickerEl) pickerEl.remove();
    userMsgEl.remove();
    console.error('SSE error:', err);
    appendMsgFallback('bot', `Error: ${err.message || 'Unknown error occurred'}`);
    isWaiting = false;
    inputElChat.focus();
    return;
  }

  progressWrap.remove(); // idempotent

  if (sseOutcome === 'pick') {
    // Check if early selection was disabled
    if (pickerEl && pickerEl._earlySelectionDisabled) {
      // Fall back to normal activation
      activateCandidatePicker(pickerEl, candidates, async (result) => {
        pickerEl.remove();
        try {
          await fetch('/api/chat/commit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId, message: text, result }),
          });
        } catch { /* non-fatal */ }
        try {
          const sr = await fetch(`/api/sessions/${currentSessionId}`);
          const sess = await sr.json();
          const lastTurn = sess.turns[sess.turns.length - 1];
          if (lastTurn && lastTurn.branch.user.content === text) {
            renderTurn(lastTurn, toggleStreaming.checked, true);
          } else {
            appendMsgFallback('bot', result.response, result);
          }
          if (isNewSession && sess.title) headerTitle.textContent = sess.title;
          loadSessionList();
        } catch {
          appendMsgFallback('bot', result.response, result);
        }
        isWaiting = false;
        inputElChat.focus();
      });
    } else if (pickerEl && !pickerEl._earlySelectionDisabled) {
      // Early selection is still active, update the UI to show all responses are ready
      const label = pickerEl.querySelector('.candidate-picker-label');
      if (label) label.textContent = `${candidates.length} skills matched \u2014 pick the best response:`;

      const dismissBtn = pickerEl.querySelector('.btn-candidate-dismiss');
      if (dismissBtn) {
        dismissBtn.textContent = 'Use default';
        dismissBtn.title = "Use the highest-priority skill's response";
        dismissBtn.onclick = () => {
          if (pickerEl._onResolve) pickerEl._onResolve(null);
        };
      }

      const hint = pickerEl.querySelector('.candidate-hint');
      if (hint) hint.textContent = 'All responses ready';
    }
    return; // isWaiting cleared by callback above
  }

  if (sseOutcome === 'no_match') {
    if (pickerEl) pickerEl.remove();
    try {
      const sr = await fetch(`/api/sessions/${currentSessionId}`);
      const sess = await sr.json();
      const lastTurn = sess.turns[sess.turns.length - 1];
      if (lastTurn && lastTurn.branch.user.content === text) {
        renderTurn(lastTurn, toggleStreaming.checked, true);
      } else {
        appendMsgFallback('bot', 'Sorry, there is no corresponding Skill for that question.');
      }
      if (isNewSession && sess.title) headerTitle.textContent = sess.title;
      loadSessionList();
    } catch {
      appendMsgFallback('bot', 'Sorry, there is no corresponding Skill for that question.');
    }
    isWaiting = false;
    inputElChat.focus();
    return;
  }

  // sseOutcome === 'committed'
  try {
    const sr = await fetch(`/api/sessions/${currentSessionId}`);
    const sess = await sr.json();
    const lastTurn = sess.turns[sess.turns.length - 1];
    if (lastTurn && lastTurn.branch.user.content === text) {
      renderTurn(lastTurn, toggleStreaming.checked, true);
    } else {
      appendMsgFallback('bot', committedData?.response ?? 'No response.', committedData);
    }
    if (isNewSession && sess.title) headerTitle.textContent = sess.title;
    loadSessionList();
  } catch (err) {
    console.error('Session fetch error:', err);
    appendMsgFallback('bot', committedData?.response ?? 'Error', committedData);
  }

  isWaiting = false;
  inputElChat.focus();
}

/* ══════════════════════════════════════════════════
   CANDIDATE PICKER  (multi-match UI)
   Phase 1 – buildCandidatePickerSkeleton(skillNames)
     Creates the wrapper + a "loading" card per skill immediately
     after all match() calls complete.
   Phase 2 – fillCandidateCard(pickerEl, candidate)
     Replaces the loading skeleton for a skill as each respond() finishes.
   Phase 3 – activateCandidatePicker(pickerEl, candidates, onResolve)
     Wires up confirm/dismiss buttons once all candidates have arrived.
   onResolve(chosen) receives the selected candidate object.
══════════════════════════════════════════════════ */

function buildCandidatePickerSkeleton(skillNames) {
  const wrap = document.createElement('div');
  wrap.className = 'candidate-picker';
  wrap._skillNames = skillNames;

  const label = document.createElement('div');
  label.className = 'candidate-picker-label';
  label.textContent = `${skillNames.length} skills matched \u2014 generating responses\u2026`;
  wrap.appendChild(label);

  const cardsRow = document.createElement('div');
  cardsRow.className = 'candidate-cards';
  wrap._cardsRow = cardsRow;

  skillNames.forEach((name) => {
    const card = document.createElement('div');
    card.className = 'candidate-card loading';
    card.dataset.skill = name;

    const header = document.createElement('div');
    header.className = 'candidate-card-header';
    const badge = document.createElement('span');
    badge.className = 'candidate-skill-badge';
    badge.textContent = name;
    header.appendChild(badge);
    card.appendChild(header);

    const body = document.createElement('div');
    body.className = 'candidate-card-body';
    const ind = document.createElement('div');
    ind.className = 'typing-indicator';
    ind.innerHTML = '<span></span><span></span><span></span>';
    body.appendChild(ind);
    card.appendChild(body);

    const meta = document.createElement('div');
    meta.className = 'candidate-card-meta';
    meta.textContent = '\u2014';
    card.appendChild(meta);

    cardsRow.appendChild(card);
  });

  wrap.appendChild(cardsRow);

  const actionsRow = document.createElement('div');
  actionsRow.className = 'candidate-actions';
  actionsRow.innerHTML =
    '<button class="btn-candidate-select" disabled>Use selected</button>' +
    '<button class="btn-candidate-dismiss" disabled>Use default</button>' +
    '<span class="candidate-hint">Generating responses\u2026</span>';
  wrap._actionsRow = actionsRow;
  wrap.appendChild(actionsRow);

  wrap._autoResolve = null;

  return wrap;
}

function setupEarlySelection(pickerEl, candidates, onResolve) {
  let resolved = false;
  pickerEl._onResolve = onResolve;
  pickerEl._selectedIndex = 0;

  function resolve(chosen) {
    if (resolved) return;
    resolved = true;
    onResolve(chosen ?? candidates[0]);
  }

  const actionsRow = pickerEl._actionsRow;
  actionsRow.innerHTML = '';

  const selectBtn = document.createElement('button');
  selectBtn.className = 'btn-candidate-select';
  selectBtn.textContent = 'Use selected response';
  selectBtn.disabled = true; // Enable only when a card is selected
  selectBtn.addEventListener('click', () => {
    const selectedCandidate = candidates[pickerEl._selectedIndex] || candidates[0];
    resolve(selectedCandidate);
  });
  actionsRow.appendChild(selectBtn);

  const dismissBtn = document.createElement('button');
  dismissBtn.className = 'btn-candidate-dismiss';
  dismissBtn.textContent = 'Wait for all responses';
  dismissBtn.title = "Wait for all skills to finish generating";
  dismissBtn.addEventListener('click', () => {
    // Don't resolve yet, let the normal flow continue
    pickerEl._earlySelectionDisabled = true;
  });
  actionsRow.appendChild(dismissBtn);

  const hint = document.createElement('span');
  hint.className = 'candidate-hint';
  hint.textContent = 'Select a response as soon as it\'s ready';
  actionsRow.appendChild(hint);

  pickerEl._autoResolve = () => resolve(null);
}

function fillCandidateCard(pickerEl, candidate, allCandidates, onResolve) {
  const card = pickerEl._cardsRow.querySelector(`[data-skill="${candidate.skill}"]`);
  if (!card) return;
  card.classList.remove('loading');
  card.classList.add('selectable');

  const body = card.querySelector('.candidate-card-body');
  body.innerHTML = '';
  body.textContent = candidate.response;

  const meta = card.querySelector('.candidate-card-meta');
  meta.textContent = `${candidate.tokens} tok \u00b7 ${candidate.wallMs ?? candidate.elapsed_ms}ms \u00b7 ${candidate.tps} t/s`;

  // Make this card immediately selectable
  card.addEventListener('click', () => {
    // Remove selected from all cards and add to this one
    pickerEl._cardsRow.querySelectorAll('.candidate-card').forEach(c => c.classList.remove('selected'));
    card.classList.add('selected');

    // Enable the select button if not already enabled
    const selectBtn = pickerEl._actionsRow.querySelector('.btn-candidate-select');
    if (selectBtn && selectBtn.disabled) {
      selectBtn.disabled = false;
      selectBtn.textContent = 'Use selected response';
    }

    // Store the selected candidate index
    const candidateIndex = allCandidates.findIndex(c => c.skill === candidate.skill);
    pickerEl._selectedIndex = candidateIndex;
  });

  scrollBottom();
}

function activateCandidatePicker(pickerEl, candidates, onResolve) {
  let selectedIndex = 0;
  let resolved = false;

  function resolve(chosen) {
    if (resolved) return;
    resolved = true;
    onResolve(chosen ?? candidates[0]);
  }

  const label = pickerEl.querySelector('.candidate-picker-label');
  if (label) label.textContent = `${candidates.length} skills matched \u2014 pick the best response:`;

  const cards = Array.from(pickerEl._cardsRow.querySelectorAll('.candidate-card'));
  if (cards[0]) cards[0].classList.add('selected');

  cards.forEach((card, i) => {
    card.addEventListener('click', () => {
      cards.forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      selectedIndex = i;
    });
  });

  const actionsRow = pickerEl._actionsRow;
  actionsRow.innerHTML = '';

  const selectBtn = document.createElement('button');
  selectBtn.className = 'btn-candidate-select';
  selectBtn.textContent = 'Use selected';
  selectBtn.addEventListener('click', () => resolve(candidates[selectedIndex]));
  actionsRow.appendChild(selectBtn);

  const dismissBtn = document.createElement('button');
  dismissBtn.className = 'btn-candidate-dismiss';
  dismissBtn.textContent = 'Use default';
  dismissBtn.title = "Use the highest-priority skill's response";
  dismissBtn.addEventListener('click', () => resolve(null));
  actionsRow.appendChild(dismissBtn);

  const hint = document.createElement('span');
  hint.className = 'candidate-hint';
  hint.textContent = 'Closing this session uses the default';
  actionsRow.appendChild(hint);

  pickerEl._autoResolve = () => resolve(null);
}


/* ── Fallback plain message (no turn controls) ── */
function appendMsgFallback(role, text, meta = null) {
  const msgEl = document.createElement('div');
  msgEl.className = `msg ${role}`;
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;
  msgEl.appendChild(bubble);
  if (meta) msgEl.appendChild(buildMetaEl(meta));
  chatEl.appendChild(msgEl);
  scrollBottom();
}

/* ── Streaming text ───────────────────────────── */
async function typeText(el, text) {
  el.classList.add('streaming-cursor');
  el.textContent = '';
  const tokenRe = /\S+\s*/g;
  const tokens = [];
  let m;
  while ((m = tokenRe.exec(text)) !== null) tokens.push(m[0]);
  if (tokens.length === 0) { el.textContent = text; el.classList.remove('streaming-cursor'); return; }
  const targetMs = Math.min(1500, 600 + tokens.length * 4);
  const baseDelay = Math.max(12, Math.min(60, targetMs / tokens.length));
  for (let i = 0; i < tokens.length; i++) {
    el.textContent += tokens[i];
    if (i % 5 === 0) scrollBottom();
    await sleep(baseDelay + (Math.random() - 0.5) * baseDelay * 0.5);
  }
  el.classList.remove('streaming-cursor');
}
function sleep(ms) { return new Promise(r => setTimeout(r, Math.max(1, ms))); }

/* ── Meta element ─────────────────────────────── */
function buildMetaEl(bot) {
  const metaEl = document.createElement('div');
  metaEl.className = 'meta';
  if (bot && bot.skill) {
    const badge = document.createElement('span');
    badge.className = 'skill-badge';
    badge.textContent = `[${bot.skill}]`;
    metaEl.appendChild(badge);
    const sep = document.createElement('span');
    sep.className = 'sep';
    metaEl.appendChild(sep);
  }
  if (bot && bot.tokens !== undefined) {
    const stat = document.createElement('span');
    stat.className = 'stat';
    stat.textContent = `${bot.tokens} tok · ${bot.wallMs ?? bot.elapsed_ms}ms · ${bot.tps} t/s`;
    metaEl.appendChild(stat);
  }
  return metaEl;
}

function updateMetaEl(metaEl, bot) {
  metaEl.innerHTML = '';
  if (bot.skill) {
    const badge = document.createElement('span');
    badge.className = 'skill-badge';
    badge.textContent = `[${bot.skill}]`;
    metaEl.appendChild(badge);
    const sep = document.createElement('span');
    sep.className = 'sep';
    metaEl.appendChild(sep);
  }
  if (bot.tokens !== undefined) {
    const stat = document.createElement('span');
    stat.className = 'stat';
    stat.textContent = `${bot.tokens} tok · ${bot.wallMs ?? bot.elapsed_ms}ms · ${bot.tps} t/s`;
    metaEl.appendChild(stat);
  }
}

/* ── Scroll ───────────────────────────────────── */
function scrollBottom() { chatEl.scrollTop = chatEl.scrollHeight; }

/* ── Input helpers ────────────────────────────── */
function wireInput(inp, btn) {
  inp.addEventListener('input', () => {
    inp.style.height = 'auto';
    inp.style.height = Math.min(inp.scrollHeight, 120) + 'px';
    btn.classList.toggle('active', inp.value.trim().length > 0);


  });
  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });
  btn.addEventListener('click', send);
}
wireInput(inputElLanding, sendBtnLanding);
wireInput(inputElChat, sendBtnChat);

/* ── Utility ──────────────────────────────────── */
function escHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/* ── Init ─────────────────────────────────────── */
applyPrefs();
loadSessionList();
inputElLanding.focus();