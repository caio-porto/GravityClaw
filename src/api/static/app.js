/* ═══════════════════════════════════════════════════════════════
   GravityClaw Control Panel — Application Logic
   ═══════════════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {

  // ── Constants ──
  const TABS = ['overview', 'chat', 'activity', 'memory', 'integrations', 'skills', 'config'];
  const TAB_TITLES = {
    overview: 'Overview',
    chat: 'Chat',
    activity: 'Activity',
    memory: 'Memory',
    integrations: 'Integrations',
    skills: 'Skills',
    config: 'Configuration',
  };

  // ── State ──
  let activeTab = null;
  const intervals = {};
  const startTime = Date.now();
  let activityLogs = [];
  let activityFilter = 'ALL';
  let chatProcessing = false;

  // ── DOM References ──
  const sidebar = document.getElementById('sidebar');
  const sidebarOverlay = document.getElementById('sidebar-overlay');
  const btnHamburger = document.getElementById('btn-hamburger');
  const topbarTitle = document.getElementById('topbar-title');
  const toastContainer = document.getElementById('toast-container');

  // ══════════════════════════════════════════════════
  //  NAVIGATION & ROUTING
  // ══════════════════════════════════════════════════

  function navigateTo(tab) {
    if (!TABS.includes(tab)) tab = 'overview';
    if (tab === activeTab) return;

    // Cleanup previous tab intervals
    Object.keys(intervals).forEach(key => {
      clearInterval(intervals[key]);
      delete intervals[key];
    });

    // Hide all tabs, deactivate all nav links
    TABS.forEach(t => {
      const el = document.getElementById(`tab-${t}`);
      if (el) el.classList.remove('active');
      const nav = document.getElementById(`nav-${t}`);
      if (nav) nav.classList.remove('active');
    });

    // Show selected tab
    const tabEl = document.getElementById(`tab-${tab}`);
    if (tabEl) {
      tabEl.classList.remove('active');
      // Force reflow for re-triggering animation
      void tabEl.offsetWidth;
      tabEl.classList.add('active');
    }

    const navEl = document.getElementById(`nav-${tab}`);
    if (navEl) navEl.classList.add('active');

    topbarTitle.textContent = TAB_TITLES[tab] || tab;
    activeTab = tab;

    // Close mobile sidebar
    closeSidebar();

    // Init tab
    const initMap = {
      overview: initOverview,
      chat: initChat,
      activity: initActivity,
      memory: initMemory,
      integrations: initIntegrations,
      skills: initSkills,
      config: initConfig,
    };
    if (initMap[tab]) initMap[tab]();

    // Update hash without triggering hashchange
    history.replaceState(null, '', `#${tab}`);
  }

  window.addEventListener('hashchange', () => {
    navigateTo(location.hash.slice(1) || 'overview');
  });

  // Sidebar link clicks (prevent default hash jump, use navigateTo)
  document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      navigateTo(link.dataset.tab);
    });
  });

  // ══════════════════════════════════════════════════
  //  MOBILE SIDEBAR
  // ══════════════════════════════════════════════════

  function openSidebar() {
    sidebar.classList.add('open');
    sidebarOverlay.classList.add('visible');
    sidebarOverlay.style.display = 'block';
  }

  function closeSidebar() {
    sidebar.classList.remove('open');
    sidebarOverlay.classList.remove('visible');
    setTimeout(() => {
      if (!sidebar.classList.contains('open')) {
        // Only hide on mobile
        if (window.innerWidth <= 768) {
          sidebarOverlay.style.display = '';
        }
      }
    }, 300);
  }

  btnHamburger.addEventListener('click', openSidebar);
  sidebarOverlay.addEventListener('click', closeSidebar);

  // ══════════════════════════════════════════════════
  //  TOAST NOTIFICATIONS
  // ══════════════════════════════════════════════════

  function showToast(message, isError = false) {
    const toast = document.createElement('div');
    toast.className = `toast ${isError ? 'toast--error' : 'toast--success'}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.classList.add('toast--exit');
      toast.addEventListener('animationend', () => toast.remove());
    }, 3500);
  }

  // ══════════════════════════════════════════════════
  //  API HELPERS
  // ══════════════════════════════════════════════════

  async function apiFetch(url, options = {}) {
    try {
      const res = await fetch(url, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.error(`API error [${url}]:`, err);
      throw err;
    }
  }

  function formatUptime(ms) {
    const s = Math.floor(ms / 1000);
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    const parts = [];
    if (d) parts.push(`${d}d`);
    if (h) parts.push(`${h}h`);
    if (m) parts.push(`${m}m`);
    parts.push(`${sec}s`);
    return parts.join(' ');
  }

  function formatTime(ts) {
    if (!ts) return '';
    const d = new Date(ts);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function formatLogTime(ts) {
    if (!ts) return '';
    const d = new Date(ts);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // ══════════════════════════════════════════════════
  //  TAB: OVERVIEW
  // ══════════════════════════════════════════════════

  function initOverview() {
    // Start uptime counter
    updateUptime();
    intervals.uptime = setInterval(updateUptime, 1000);

    // Fetch status
    fetchStatus();
  }

  function updateUptime() {
    const el = document.getElementById('status-uptime');
    if (el) el.textContent = formatUptime(Date.now() - startTime);
  }

  async function fetchStatus() {
    try {
      const data = await apiFetch('/api/status');

      const statusDot = document.getElementById('status-dot');
      const statusText = document.getElementById('status-text');
      if (data.status === 'running' || data.running) {
        statusDot.className = 'status-dot status-dot--running';
        statusText.textContent = 'Agent Running';
      } else {
        statusDot.className = 'status-dot status-dot--stopped';
        statusText.textContent = 'Agent Stopped';
      }

      const modelProvider = document.getElementById('model-provider');
      const modelName = document.getElementById('model-name');
      if (data.model) {
        modelProvider.textContent = data.model.provider || data.model_provider || '—';
        modelName.textContent = data.model.name || data.model_name || '—';
      } else {
        modelProvider.textContent = data.model_provider || '—';
        modelName.textContent = data.model_name || '—';
      }

      const statMessages = document.getElementById('stat-messages');
      statMessages.textContent = data.messages_today ?? data.messages ?? '0';

      const statMemory = document.getElementById('stat-memory');
      statMemory.textContent = data.memory_entries ?? data.memories ?? '0';
    } catch {
      // Silently fail — cards keep previous values
    }
  }

  // ══════════════════════════════════════════════════
  //  TAB: CHAT
  // ══════════════════════════════════════════════════

  function initChat() {
    loadChatHistory();
    setupChatComposer();
  }

  async function loadChatHistory() {
    const container = document.getElementById('chat-messages');
    try {
      const data = await apiFetch('/api/chat/history');
      container.innerHTML = '';
      const messages = data.messages || data.history || data || [];
      if (Array.isArray(messages)) {
        messages.forEach(msg => appendChatBubble(msg));
      }
      scrollChatToBottom();
    } catch {
      container.innerHTML = `
        <div class="empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          <span>Start a conversation</span>
        </div>`;
    }
  }

  function appendChatBubble(msg) {
    const container = document.getElementById('chat-messages');
    const role = msg.role || msg.sender || 'assistant';
    const isUser = role === 'user' || role === 'human';
    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${isUser ? 'chat-bubble--user' : 'chat-bubble--assistant'}`;
    bubble.innerHTML = `${escapeHtml(msg.content || msg.text || msg.message || '')}<span class="chat-bubble-time">${formatTime(msg.timestamp || msg.created_at)}</span>`;
    container.appendChild(bubble);
  }

  function scrollChatToBottom() {
    const container = document.getElementById('chat-messages');
    requestAnimationFrame(() => {
      container.scrollTop = container.scrollHeight;
    });
  }

  function setupChatComposer() {
    const input = document.getElementById('chat-input');
    const btnSend = document.getElementById('btn-send-chat');

    // Auto-grow textarea
    const autoGrow = () => {
      input.style.height = '46px';
      input.style.height = Math.min(input.scrollHeight, 140) + 'px';
    };

    // Remove old listeners by cloning
    const newInput = input.cloneNode(true);
    input.parentNode.replaceChild(newInput, input);
    const newBtn = btnSend.cloneNode(true);
    btnSend.parentNode.replaceChild(newBtn, btnSend);

    const chatInput = document.getElementById('chat-input');
    const chatBtn = document.getElementById('btn-send-chat');

    chatInput.addEventListener('input', () => {
      chatInput.style.height = '46px';
      chatInput.style.height = Math.min(chatInput.scrollHeight, 140) + 'px';
    });

    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
      }
    });

    chatBtn.addEventListener('click', sendChatMessage);
  }

  async function sendChatMessage() {
    if (chatProcessing) return;

    const input = document.getElementById('chat-input');
    const btn = document.getElementById('btn-send-chat');
    const thinking = document.getElementById('chat-thinking');
    const message = input.value.trim();
    if (!message) return;

    // Add user bubble
    appendChatBubble({ role: 'user', content: message, timestamp: new Date().toISOString() });
    scrollChatToBottom();

    // Clear input
    input.value = '';
    input.style.height = '46px';

    // Disable
    chatProcessing = true;
    input.disabled = true;
    btn.disabled = true;
    thinking.classList.remove('hidden');

    try {
      const data = await apiFetch('/api/chat', {
        method: 'POST',
        body: JSON.stringify({ message }),
      });

      const reply = data.reply || data.response || data.message || data.content || '';
      appendChatBubble({
        role: 'assistant',
        content: reply,
        timestamp: data.timestamp || new Date().toISOString(),
      });
      scrollChatToBottom();
    } catch (err) {
      showToast('Failed to send message', true);
    } finally {
      chatProcessing = false;
      input.disabled = false;
      btn.disabled = false;
      thinking.classList.add('hidden');
      input.focus();
    }
  }

  // ══════════════════════════════════════════════════
  //  TAB: ACTIVITY
  // ══════════════════════════════════════════════════

  function initActivity() {
    fetchLogs();
    intervals.logs = setInterval(fetchLogs, 3000);
    setupActivityFilters();
  }

  async function fetchLogs() {
    try {
      const data = await apiFetch('/api/logs?limit=200');
      activityLogs = data.logs || data.entries || data || [];
      renderLogs();
    } catch {
      // Silently fail
    }
  }

  function setupActivityFilters() {
    document.querySelectorAll('.filter-btn[data-level]').forEach(btn => {
      const newBtn = btn.cloneNode(true);
      btn.parentNode.replaceChild(newBtn, btn);
    });

    document.querySelectorAll('.filter-btn[data-level]').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.filter-btn[data-level]').forEach(b => b.classList.remove('filter-btn--active'));
        btn.classList.add('filter-btn--active');
        activityFilter = btn.dataset.level;
        renderLogs();
      });
    });

    const clearBtn = document.getElementById('btn-clear-logs');
    const newClear = clearBtn.cloneNode(true);
    clearBtn.parentNode.replaceChild(newClear, clearBtn);
    document.getElementById('btn-clear-logs').addEventListener('click', () => {
      activityLogs = [];
      renderLogs();
    });
  }

  function renderLogs() {
    const container = document.getElementById('activity-list');
    let filtered = activityLogs;
    if (activityFilter !== 'ALL') {
      filtered = activityLogs.filter(log => {
        const level = (log.level || log.levelname || '').toUpperCase();
        return level === activityFilter;
      });
    }

    if (!filtered.length) {
      container.innerHTML = `
        <div class="empty-state">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
          <span>No log entries</span>
        </div>`;
      return;
    }

    container.innerHTML = filtered.map(log => {
      const level = (log.level || log.levelname || 'INFO').toUpperCase();
      const levelClass = ['INFO', 'WARNING', 'ERROR', 'DEBUG'].includes(level) ? level : 'INFO';
      const ts = formatLogTime(log.timestamp || log.created || log.time);
      const logger = log.logger || log.name || '';
      const msg = escapeHtml(log.message || log.msg || '');

      return `<div class="log-entry">
        <span class="log-timestamp">${ts}</span>
        <span class="log-level log-level--${levelClass}">${level}</span>
        <span class="log-logger" title="${escapeHtml(logger)}">${escapeHtml(logger)}</span>
        <span class="log-message">${msg}</span>
      </div>`;
    }).join('');
  }

  // ══════════════════════════════════════════════════
  //  TAB: MEMORY
  // ══════════════════════════════════════════════════

  function initMemory() {
    loadCoreMemory();
    loadDailyDates();
    setupMemoryHandlers();
  }

  async function loadCoreMemory() {
    try {
      const data = await apiFetch('/api/memory/core');
      document.getElementById('memory-core-editor').value = data.content || data.text || '';
    } catch {
      document.getElementById('memory-core-editor').value = '# Failed to load core memory';
    }
  }

  async function loadDailyDates() {
    const picker = document.getElementById('memory-date-picker');
    // Default to today
    const today = new Date().toISOString().split('T')[0];
    picker.value = today;
    loadDailyLog(today);
  }

  async function loadDailyLog(date) {
    const viewer = document.getElementById('memory-daily-content');
    try {
      const data = await apiFetch(`/api/memory/daily?date=${date}`);
      viewer.textContent = data.content || data.text || data.log || '(No log for this date)';
    } catch {
      viewer.textContent = '(No log for this date)';
    }
  }

  function setupMemoryHandlers() {
    // Save core memory
    const saveBtn = document.getElementById('btn-save-core-memory');
    const newSave = saveBtn.cloneNode(true);
    saveBtn.parentNode.replaceChild(newSave, saveBtn);
    document.getElementById('btn-save-core-memory').addEventListener('click', async () => {
      const content = document.getElementById('memory-core-editor').value;
      try {
        await apiFetch('/api/memory/core', {
          method: 'PUT',
          body: JSON.stringify({ content }),
        });
        showToast('Core memory saved');
      } catch {
        showToast('Failed to save core memory', true);
      }
    });

    // Date picker
    const picker = document.getElementById('memory-date-picker');
    const newPicker = picker.cloneNode(true);
    picker.parentNode.replaceChild(newPicker, picker);
    document.getElementById('memory-date-picker').addEventListener('change', (e) => {
      loadDailyLog(e.target.value);
    });
  }

  // ══════════════════════════════════════════════════
  //  TAB: INTEGRATIONS
  // ══════════════════════════════════════════════════

  let editingServer = null;

  const MCP_TEMPLATES = {
    github: {
      name: 'github',
      command: 'npx',
      args: '-y, @modelcontextprotocol/server-github',
      env: 'GITHUB_TOKEN=your_github_token_here'
    },
    brave: {
      name: 'brave-search',
      command: 'npx',
      args: '-y, @modelcontextprotocol/server-brave-search',
      env: 'BRAVE_API_KEY=your_brave_key_here'
    },
    ddg: {
      name: 'ddg-search',
      command: 'npx',
      args: '-y, duckduckgo-mcp-server',
      env: ''
    },
    notion: {
      name: 'notion',
      command: 'npx',
      args: '-y, @modelcontextprotocol/server-notion',
      env: 'NOTION_API_KEY=your_notion_key_here'
    },
    drive: {
      name: 'google-drive',
      command: 'npx',
      args: '-y, @modelcontextprotocol/server-google-drive',
      env: ''
    }
  };

  function initIntegrations() {
    fetchIntegrations();
    setupTelegramHandlers();
    setupMCPFormHandlers();
    setupEnvKeysHandlers();
  }

  function setupMCPFormHandlers() {
    const formContainer = document.getElementById('mcp-form-container');
    const inputName = document.getElementById('mcp-input-name');
    const inputCommand = document.getElementById('mcp-input-command');
    const inputArgs = document.getElementById('mcp-input-args');
    const inputEnv = document.getElementById('mcp-input-env');

    // Add button
    const btnAdd = document.getElementById('btn-add-mcp-server');
    const newAdd = btnAdd.cloneNode(true);
    btnAdd.parentNode.replaceChild(newAdd, btnAdd);
    document.getElementById('btn-add-mcp-server').addEventListener('click', () => {
      editingServer = null;
      document.getElementById('mcp-form-title').textContent = 'Add Custom MCP Server';
      inputName.value = '';
      inputName.disabled = false;
      inputCommand.value = '';
      inputArgs.value = '';
      inputEnv.value = '';
      formContainer.classList.remove('hidden');
      formContainer.scrollIntoView({ behavior: 'smooth' });
    });

    // Cancel button
    const btnCancel = document.getElementById('btn-cancel-mcp');
    const newCancel = btnCancel.cloneNode(true);
    btnCancel.parentNode.replaceChild(newCancel, btnCancel);
    document.getElementById('btn-cancel-mcp').addEventListener('click', () => {
      formContainer.classList.add('hidden');
    });

    // Save button
    const btnSave = document.getElementById('btn-save-mcp-server');
    const newSave = btnSave.cloneNode(true);
    btnSave.parentNode.replaceChild(newSave, btnSave);
    document.getElementById('btn-save-mcp-server').addEventListener('click', async () => {
      const name = inputName.value.trim().toLowerCase();
      const command = inputCommand.value.trim();
      const rawArgs = inputArgs.value.trim();
      const rawEnv = inputEnv.value.trim();

      if (!name || !command) {
        showToast('Server name and command are required', true);
        return;
      }

      // Parse args
      const args = rawArgs ? rawArgs.split(',').map(s => s.trim()).filter(Boolean) : [];

      // Parse env variables
      const env = {};
      if (rawEnv) {
        rawEnv.split('\n').forEach(line => {
          const parts = line.split('=', 2);
          if (parts.length === 2) {
            env[parts[0].trim()] = parts[1].trim();
          }
        });
      }

      try {
        await apiFetch('/api/integrations/mcp/save', {
          method: 'POST',
          body: JSON.stringify({ name, command, args, env }),
        });
        showToast(`MCP server '${name}' saved successfully`);
        formContainer.classList.add('hidden');
        fetchIntegrations();
      } catch (err) {
        showToast('Failed to save MCP server', true);
      }
    });

    // Template buttons
    document.querySelectorAll('.mcp-template-btn').forEach(btn => {
      const newBtn = btn.cloneNode(true);
      btn.parentNode.replaceChild(newBtn, btn);
    });
    document.querySelectorAll('.mcp-template-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const tmpl = MCP_TEMPLATES[btn.dataset.template];
        if (tmpl) {
          inputName.value = tmpl.name;
          inputCommand.value = tmpl.command;
          inputArgs.value = tmpl.args;
          inputEnv.value = tmpl.env;
          showToast(`Loaded ${btn.textContent} template`);
        }
      });
    });
  }

  function setupTelegramHandlers() {
    const toggle = document.getElementById('telegram-bot-toggle');
    const btnToggleConfig = document.getElementById('btn-toggle-telegram-config');
    const configPanel = document.getElementById('telegram-config-panel');
    const btnShowToken = document.getElementById('btn-show-telegram-token');
    const inputToken = document.getElementById('telegram-input-token');
    const btnSaveConfig = document.getElementById('btn-save-telegram-config');

    // Clone to remove old listeners
    const newToggle = toggle.cloneNode(true);
    toggle.parentNode.replaceChild(newToggle, toggle);
    const newBtnToggleConfig = btnToggleConfig.cloneNode(true);
    btnToggleConfig.parentNode.replaceChild(newBtnToggleConfig, btnToggleConfig);
    const newBtnShowToken = btnShowToken.cloneNode(true);
    btnShowToken.parentNode.replaceChild(newBtnShowToken, btnShowToken);
    const newBtnSaveConfig = btnSaveConfig.cloneNode(true);
    btnSaveConfig.parentNode.replaceChild(newBtnSaveConfig, btnSaveConfig);

    const tgToggle = document.getElementById('telegram-bot-toggle');
    const tgBtnToggleConfig = document.getElementById('btn-toggle-telegram-config');
    const tgBtnShowToken = document.getElementById('btn-show-telegram-token');
    const tgBtnSaveConfig = document.getElementById('btn-save-telegram-config');

    tgToggle.addEventListener('change', async () => {
      const enabled = tgToggle.checked;
      try {
        const data = await apiFetch('/api/integrations/telegram/toggle', {
          method: 'POST',
          body: JSON.stringify({ enabled })
        });
        showToast(data.message || `Telegram bot ${enabled ? 'started' : 'stopped'}`);
        fetchIntegrations();
      } catch (err) {
        showToast(err.message || 'Failed to toggle Telegram Bot', true);
        tgToggle.checked = !enabled;
      }
    });

    tgBtnToggleConfig.addEventListener('click', () => {
      configPanel.classList.toggle('hidden');
    });

    tgBtnShowToken.addEventListener('click', () => {
      const isPassword = inputToken.type === 'password';
      inputToken.type = isPassword ? 'text' : 'password';
      tgBtnShowToken.textContent = isPassword ? 'Hide' : 'Show';
    });

    tgBtnSaveConfig.addEventListener('click', async () => {
      const token = inputToken.value.trim();
      if (!token) {
        showToast('Token cannot be empty', true);
        return;
      }
      
      tgBtnSaveConfig.disabled = true;
      tgBtnSaveConfig.textContent = 'Saving…';
      
      try {
        const data = await apiFetch('/api/integrations/telegram/configure', {
          method: 'POST',
          body: JSON.stringify({ token })
        });
        showToast(data.message || 'Telegram Bot token updated successfully');
        inputToken.value = '';
        configPanel.classList.add('hidden');
        fetchIntegrations();
      } catch (err) {
        showToast('Failed to configure Telegram Bot', true);
      } finally {
        tgBtnSaveConfig.disabled = false;
        tgBtnSaveConfig.textContent = 'Save & Apply';
      }
    });
  }

  function setupEnvKeysHandlers() {
    const formContainer = document.getElementById('env-form-container');
    const inputName = document.getElementById('env-input-name');
    const inputValue = document.getElementById('env-input-value');
    const btnShowValue = document.getElementById('btn-show-env-value');
    const btnAdd = document.getElementById('btn-add-env-key');
    const btnCancel = document.getElementById('btn-cancel-env');
    const btnSave = document.getElementById('btn-save-env-key');

    // Clone to remove old listeners
    const newBtnAdd = btnAdd.cloneNode(true);
    btnAdd.parentNode.replaceChild(newBtnAdd, btnAdd);
    const newBtnCancel = btnCancel.cloneNode(true);
    btnCancel.parentNode.replaceChild(newBtnCancel, btnCancel);
    const newBtnSave = btnSave.cloneNode(true);
    btnSave.parentNode.replaceChild(newBtnSave, btnSave);
    const newBtnShowValue = btnShowValue.cloneNode(true);
    btnShowValue.parentNode.replaceChild(newBtnShowValue, btnShowValue);

    const envBtnAdd = document.getElementById('btn-add-env-key');
    const envBtnCancel = document.getElementById('btn-cancel-env');
    const envBtnSave = document.getElementById('btn-save-env-key');
    const envBtnShowValue = document.getElementById('btn-show-env-value');

    envBtnShowValue.addEventListener('click', () => {
      const isPassword = inputValue.type === 'password';
      inputValue.type = isPassword ? 'text' : 'password';
      envBtnShowValue.textContent = isPassword ? 'Hide' : 'Show';
    });

    envBtnAdd.addEventListener('click', () => {
      document.getElementById('env-form-title').textContent = 'Add Environment Key';
      inputName.value = '';
      inputName.disabled = false;
      inputValue.value = '';
      formContainer.classList.remove('hidden');
      formContainer.scrollIntoView({ behavior: 'smooth' });
    });

    envBtnCancel.addEventListener('click', () => {
      formContainer.classList.add('hidden');
    });

    envBtnSave.addEventListener('click', async () => {
      const name = inputName.value.trim().toUpperCase();
      const value = inputValue.value.trim();

      if (!name) {
        showToast('Environment Key name is required', true);
        return;
      }

      envBtnSave.disabled = true;
      envBtnSave.textContent = 'Saving…';

      try {
        const data = await apiFetch('/api/integrations/env/save', {
          method: 'POST',
          body: JSON.stringify({ name, value }),
        });
        showToast(data.message || `Environment key '${name}' saved successfully`);
        formContainer.classList.add('hidden');
        fetchIntegrations();
      } catch (err) {
        showToast(err.message || 'Failed to save environment key', true);
      } finally {
        envBtnSave.disabled = false;
        envBtnSave.textContent = 'Save Key';
      }
    });
  }

  async function fetchIntegrations() {
    try {
      const data = await apiFetch('/api/integrations');

      // Telegram Bot Integration
      const tgDot = document.getElementById('telegram-status-dot');
      const tgText = document.getElementById('telegram-status-text');
      const tgInfo = document.getElementById('telegram-bot-info');
      const tgToggle = document.getElementById('telegram-bot-toggle');
      const tgTokenStatus = document.getElementById('telegram-token-status');

      const tg = data.telegram || {};
      const tgRunning = tg.bot_running || tg.running || tg.status === 'running';
      
      if (tgRunning) {
        tgDot.className = 'status-dot status-dot--running';
        tgText.textContent = 'Running';
      } else {
        tgDot.className = 'status-dot status-dot--stopped';
        tgText.textContent = 'Stopped';
      }
      tgInfo.textContent = tg.bot_name || tg.username || '—';
      if (tgToggle) {
        tgToggle.checked = tgRunning;
      }
      if (tgTokenStatus) {
        if (tg.token_configured) {
          tgTokenStatus.textContent = '✓ Token Configured';
          tgTokenStatus.style.color = 'var(--success)';
        } else {
          tgTokenStatus.textContent = '✕ Token Missing';
          tgTokenStatus.style.color = 'var(--danger)';
        }
      }

      // MCP Tools List rendering
      const toolsList = document.getElementById('mcp-tools-list');
      const tools = data.mcp_tools || data.tools || [];
      if (tools.length === 0) {
        toolsList.innerHTML = '<div class="empty-state" style="width:100%"><span>No MCP servers configured yet</span></div>';
      } else {
        toolsList.innerHTML = tools.map((tool, i) => {
          const name = tool.name;
          const cmd = tool.command || '';
          const args = Array.isArray(tool.args) ? tool.args.join(', ') : (tool.args || '');
          const envKeys = Object.keys(tool.env || {}).join(', ') || 'None';

          return `<div class="mcp-list-item" style="animation-delay:${i * 50}ms; display: flex; flex-direction: column; background: rgba(255,255,255,0.02); border: 1px solid var(--border); padding: 1rem 1.25rem; border-radius: var(--radius-md); margin-bottom: 0.75rem; transition: background var(--transition-fast); gap: 0.5rem; width: 100%;">
            <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
              <div style="display: flex; align-items: center; gap: 0.75rem;">
                <span class="mcp-card-name" style="font-size: 1rem; font-weight: 600; background: linear-gradient(135deg, var(--text-primary), var(--text-secondary)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-family: monospace;">${escapeHtml(name)}</span>
                <span style="font-size: 0.65rem; text-transform: uppercase; font-weight: 600; padding: 2px 8px; border-radius: 99px; background: rgba(99, 102, 241, 0.15); color: var(--accent-light); border: 1px solid rgba(99, 102, 241, 0.25);">MCP Server</span>
              </div>
              <div style="display: flex; gap: 0.5rem;">
                <button class="btn-outline btn-edit-mcp" data-name="${escapeHtml(name)}" style="padding: 4px 8px; font-size: 0.7rem; border-radius: 6px;">⚙ Edit</button>
                <button class="btn-outline btn-outline--danger btn-delete-mcp" data-name="${escapeHtml(name)}" style="padding: 4px 8px; font-size: 0.7rem; border-radius: 6px;">🗑 Delete</button>
              </div>
            </div>
            <div style="display: flex; flex-wrap: wrap; gap: 1rem; align-items: center; width: 100%; margin-top: 0.25rem;">
              <div style="flex: 1; min-width: 250px; font-family: monospace; font-size: 0.75rem; color: var(--text-secondary); background: rgba(0,0,0,0.3); padding: 0.5rem 0.75rem; border-radius: 8px; border: 1px solid var(--border); overflow-x: auto; white-space: nowrap; scrollbar-width: none;">
                <span style="color: var(--accent-light); font-weight: 600;">${escapeHtml(cmd)}</span> ${escapeHtml(args)}
              </div>
              <div style="font-size: 0.75rem; color: var(--text-muted); display: flex; align-items: center; gap: 0.4rem; min-width: 150px;">
                <span style="font-weight: 600; text-transform: uppercase; font-size: 0.65rem; color: var(--accent-light);">Env Keys:</span>
                <code style="color: #a7f3d0; background: rgba(167, 243, 208, 0.08); padding: 2px 8px; border-radius: 6px; border: 1px solid rgba(167, 243, 208, 0.15); font-family: monospace;">${escapeHtml(envKeys)}</code>
              </div>
            </div>
          </div>`;
        }).join('');

        // Attach action handlers
        toolsList.querySelectorAll('.btn-edit-mcp').forEach(btn => {
          btn.addEventListener('click', () => {
            const name = btn.dataset.name;
            const tool = tools.find(t => t.name === name);
            if (tool) {
              editingServer = name;
              document.getElementById('mcp-form-title').textContent = `Edit MCP Server: ${name}`;
              
              const inputName = document.getElementById('mcp-input-name');
              inputName.value = name;
              inputName.disabled = true;
              
              document.getElementById('mcp-input-command').value = tool.command || '';
              document.getElementById('mcp-input-args').value = Array.isArray(tool.args) ? tool.args.join(', ') : (tool.args || '');
              
              const envLines = [];
              for (const [k, v] of Object.entries(tool.env || {})) {
                envLines.push(`${k}=${v}`);
              }
              document.getElementById('mcp-input-env').value = envLines.join('\n');
              
              const formContainer = document.getElementById('mcp-form-container');
              formContainer.classList.remove('hidden');
              formContainer.scrollIntoView({ behavior: 'smooth' });
            }
          });
        });

        toolsList.querySelectorAll('.btn-delete-mcp').forEach(btn => {
          btn.addEventListener('click', async () => {
            const name = btn.dataset.name;
            if (confirm(`Are you sure you want to delete and uninstall MCP server '${name}'?`)) {
              try {
                await apiFetch(`/api/integrations/mcp/${name}`, {
                  method: 'DELETE',
                });
                showToast(`MCP server '${name}' deleted successfully`);
                fetchIntegrations();
              } catch (err) {
                showToast(`Failed to delete MCP server '${name}'`, true);
              }
            }
          });
        });
      }

      // Environment Keys List
      const envList = document.getElementById('env-keys-list');
      const envKeys = data.env_keys || data.environment || [];
      if (envKeys.length === 0) {
        envList.innerHTML = '<div class="empty-state"><span>No environment keys configured</span></div>';
      } else {
        envList.innerHTML = envKeys.map(key => {
          const name = typeof key === 'string' ? key : (key.name || key.key);
          const isSet = typeof key === 'object' ? (key.set !== false && key.is_set !== false) : true;
          const isCustom = typeof key === 'object' ? (key.is_custom === true) : false;
          
          return `<div class="env-key-card" style="display: flex; justify-content: space-between; align-items: center; background: rgba(255,255,255,0.02); border: 1px solid var(--border); padding: 0.75rem 1rem; border-radius: var(--radius-sm); margin-bottom: 0.5rem; transition: background var(--transition-fast);">
            <div style="display: flex; align-items: center; gap: 0.75rem;">
              <span class="env-key-icon" style="width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; border-radius: 50%; font-size: 0.75rem; font-weight: bold; background: ${isSet ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)'}; color: ${isSet ? 'var(--success)' : 'var(--danger)'};">${isSet ? '✓' : '✕'}</span>
              <div style="display: flex; flex-direction: column;">
                <span style="font-weight: 600; font-size: 0.85rem; font-family: monospace;">${escapeHtml(name)}</span>
                <span style="font-size: 0.68rem; color: var(--text-muted);">${isSet ? 'Configured' : 'Missing'} ${isCustom ? '• Custom' : ''}</span>
              </div>
            </div>
            <div style="display: flex; gap: 0.5rem;">
              <button class="btn-outline btn-edit-env" data-name="${escapeHtml(name)}" style="padding: 4px 8px; font-size: 0.7rem; border-radius: 6px;">⚙ Edit</button>
              <button class="btn-outline btn-outline--danger btn-delete-env" data-name="${escapeHtml(name)}" style="padding: 4px 8px; font-size: 0.7rem; border-radius: 6px;">🗑 Delete</button>
            </div>
          </div>`;
        }).join('');

        // Attach action handlers for env keys
        envList.querySelectorAll('.btn-edit-env').forEach(btn => {
          btn.addEventListener('click', () => {
            const name = btn.dataset.name;
            const formContainer = document.getElementById('env-form-container');
            const inputName = document.getElementById('env-input-name');
            const inputValue = document.getElementById('env-input-value');
            
            document.getElementById('env-form-title').textContent = `Edit Environment Key: ${name}`;
            inputName.value = name;
            inputName.disabled = true;
            inputValue.value = '';
            
            formContainer.classList.remove('hidden');
            formContainer.scrollIntoView({ behavior: 'smooth' });
          });
        });

        envList.querySelectorAll('.btn-delete-env').forEach(btn => {
          btn.addEventListener('click', async () => {
            const name = btn.dataset.name;
            if (confirm(`Are you sure you want to delete and clear Environment Key '${name}'?`)) {
              try {
                await apiFetch(`/api/integrations/env/${name}`, {
                  method: 'DELETE',
                });
                showToast(`Environment key '${name}' deleted successfully`);
                fetchIntegrations();
              } catch (err) {
                showToast(`Failed to delete environment key '${name}'`, true);
              }
            }
          });
        });
      }
    } catch {
      showToast('Failed to load integrations', true);
    }
  }

  // ══════════════════════════════════════════════════
  //  TAB: CONFIG
  // ══════════════════════════════════════════════════

  function initConfig() {
    loadConfigForm();
    loadConfigRaw();
    setupConfigHandlers();
  }

  async function loadConfigForm() {
    try {
      const data = await apiFetch('/api/config');

      document.getElementById('config-primary-provider').value =
        data.primary_provider || (data.models && data.models.primary && data.models.primary.provider) || '';
      document.getElementById('config-primary-model').value =
        data.primary_model || (data.models && data.models.primary && (data.models.primary.model_name || data.models.primary.name)) || '';

      // Fallbacks
      const fallbacks = data.fallback_models || (data.models && (data.models.fallback || data.models.fallbacks)) || [];
      renderFallbacks(fallbacks);

      // Memory
      document.getElementById('config-chroma-dir').value =
        data.chroma_db_dir || (data.memory && data.memory.chroma_db_dir) || '';
      document.getElementById('config-collection').value =
        data.collection_name || (data.memory && data.memory.collection_name) || '';

      // Voice
      document.getElementById('config-voice-speed').value =
        (data.voice && data.voice.speed) || '1.0';
    } catch {
      // Keep fields empty
    }
  }

  function renderFallbacks(fallbacks) {
    const list = document.getElementById('fallback-list');
    list.innerHTML = fallbacks.map((fb, i) => {
      const val = typeof fb === 'string' ? fb : `${fb.provider || ''}/${fb.model_name || fb.name || fb.model || ''}${fb.url ? '/' + fb.url : ''}`;
      return `<div class="fallback-row">
        <input class="input-field fallback-input" value="${escapeHtml(val)}" placeholder="provider/model" />
        <button class="btn-remove-fallback" data-index="${i}" aria-label="Remove fallback">✕</button>
      </div>`;
    }).join('');

    // Remove handlers
    list.querySelectorAll('.btn-remove-fallback').forEach(btn => {
      btn.addEventListener('click', () => {
        btn.closest('.fallback-row').remove();
      });
    });
  }

  async function loadConfigRaw() {
    try {
      const data = await apiFetch('/api/config/raw');
      document.getElementById('config-raw-editor').value = data.yaml || data.content || data.raw || '';
    } catch {
      document.getElementById('config-raw-editor').value = '# Failed to load configuration';
    }
  }

  function setupConfigHandlers() {
    // Sub-tab toggle
    const formBtn = document.getElementById('config-tab-form');
    const rawBtn = document.getElementById('config-tab-raw');
    const formView = document.getElementById('config-form-view');
    const rawView = document.getElementById('config-raw-view');

    const newFormBtn = formBtn.cloneNode(true);
    formBtn.parentNode.replaceChild(newFormBtn, formBtn);
    const newRawBtn = rawBtn.cloneNode(true);
    rawBtn.parentNode.replaceChild(newRawBtn, rawBtn);

    document.getElementById('config-tab-form').addEventListener('click', () => {
      document.getElementById('config-tab-form').classList.add('config-tab-btn--active');
      document.getElementById('config-tab-raw').classList.remove('config-tab-btn--active');
      formView.classList.remove('hidden');
      rawView.classList.add('hidden');
    });

    document.getElementById('config-tab-raw').addEventListener('click', () => {
      document.getElementById('config-tab-raw').classList.add('config-tab-btn--active');
      document.getElementById('config-tab-form').classList.remove('config-tab-btn--active');
      rawView.classList.remove('hidden');
      formView.classList.add('hidden');
    });

    // Add fallback
    const addFb = document.getElementById('btn-add-fallback');
    const newAddFb = addFb.cloneNode(true);
    addFb.parentNode.replaceChild(newAddFb, addFb);
    document.getElementById('btn-add-fallback').addEventListener('click', () => {
      const list = document.getElementById('fallback-list');
      const row = document.createElement('div');
      row.className = 'fallback-row';
      row.innerHTML = `
        <input class="input-field fallback-input" value="" placeholder="provider/model" />
        <button class="btn-remove-fallback" aria-label="Remove fallback">✕</button>`;
      row.querySelector('.btn-remove-fallback').addEventListener('click', () => row.remove());
      list.appendChild(row);
    });

    // Save form config
    const saveForm = document.getElementById('btn-save-config-form');
    const newSaveForm = saveForm.cloneNode(true);
    saveForm.parentNode.replaceChild(newSaveForm, saveForm);
    document.getElementById('btn-save-config-form').addEventListener('click', async () => {
      const fallbacks = Array.from(document.querySelectorAll('.fallback-input'))
        .map(el => el.value.trim())
        .filter(Boolean);

      const payload = {
        primary_provider: document.getElementById('config-primary-provider').value,
        primary_model: document.getElementById('config-primary-model').value,
        fallback_models: fallbacks,
        chroma_db_dir: document.getElementById('config-chroma-dir').value,
        collection_name: document.getElementById('config-collection').value,
        voice_speed: parseFloat(document.getElementById('config-voice-speed').value) || 1.0,
      };

      try {
        await apiFetch('/api/config', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        showToast('Configuration saved');
      } catch {
        showToast('Failed to save configuration', true);
      }
    });

    // Save raw YAML
    const saveRaw = document.getElementById('btn-save-config-raw');
    const newSaveRaw = saveRaw.cloneNode(true);
    saveRaw.parentNode.replaceChild(newSaveRaw, saveRaw);
    document.getElementById('btn-save-config-raw').addEventListener('click', async () => {
      const yaml = document.getElementById('config-raw-editor').value;
      try {
        await apiFetch('/api/config/raw', {
          method: 'POST',
          body: JSON.stringify({ yaml }),
        });
        showToast('Raw configuration saved');
      } catch {
        showToast('Failed to save configuration', true);
      }
    });
  }

  // ══════════════════════════════════════════════════
  //  TAB: SKILLS (Phase 7)
  // ══════════════════════════════════════════════════
  let selectedSkillId = null;
  let skillsConsoleInterval = null;
  let catalogSkills = [];
  let installedSkillIds = [];

  function initSkills() {
    fetchSkills();
    setupSkillsHandlers();
    
    // Check if installer is running, if so, resume polling
    checkInstallerStatus();
  }

  async function fetchSkills() {
    const list = document.getElementById('skills-list');
    try {
      const data = await apiFetch('/api/skills');
      const skills = data.skills || [];
      
      // Store installed IDs for catalog lookup
      installedSkillIds = skills.map(s => s.id);
      
      if (skills.length === 0) {
        list.innerHTML = '<div style="padding: 1rem; color: var(--text-muted); font-size: 0.85rem; text-align: center;">No skills installed.</div>';
        return;
      }
      
      list.innerHTML = skills.map(skill => `
        <button class="skill-list-item ${selectedSkillId === skill.id ? 'skill-list-item--active' : ''}" data-id="${escapeHtml(skill.id)}">
          <span class="skill-list-item-name">${escapeHtml(skill.name)}</span>
          <span class="skill-list-item-desc">${escapeHtml(skill.description || '(No description)')}</span>
        </button>
      `).join('');
      
      // Attach select click handlers
      list.querySelectorAll('.skill-list-item').forEach(item => {
        item.addEventListener('click', () => {
          list.querySelectorAll('.skill-list-item').forEach(el => el.classList.remove('skill-list-item--active'));
          item.classList.add('skill-list-item--active');
          loadSkill(item.dataset.id);
        });
      });
    } catch (err) {
      showToast('Failed to load skills', true);
    }
  }

  async function loadSkill(id) {
    selectedSkillId = id;
    const empty = document.getElementById('skill-editor-empty');
    const container = document.getElementById('skill-editor-container');
    const editor = document.getElementById('skill-editor');
    const nameDisplay = document.getElementById('skill-display-name');
    const pathDisplay = document.getElementById('skill-display-path');
    
    empty.classList.add('hidden');
    container.classList.remove('hidden');
    
    try {
      const data = await apiFetch(`/api/skills/${id}`);
      editor.value = data.content || '';
      nameDisplay.textContent = id;
      pathDisplay.textContent = `skills/${id}/SKILL.md`;
    } catch (err) {
      showToast('Failed to load skill instructions', true);
    }
  }

  function setupSkillsHandlers() {
    // ── SUB-TAB NAVIGATION ──
    const btnInstalled = document.getElementById('skills-tab-installed');
    const btnDiscover = document.getElementById('skills-tab-discover');
    const viewInstalled = document.getElementById('skills-installed-view');
    const viewDiscover = document.getElementById('skills-discover-view');

    // Clone to remove old listeners
    const newBtnInstalled = btnInstalled.cloneNode(true);
    btnInstalled.parentNode.replaceChild(newBtnInstalled, btnInstalled);
    const newBtnDiscover = btnDiscover.cloneNode(true);
    btnDiscover.parentNode.replaceChild(newBtnDiscover, btnDiscover);

    document.getElementById('skills-tab-installed').addEventListener('click', () => {
      document.getElementById('skills-tab-installed').classList.add('config-tab-btn--active');
      document.getElementById('skills-tab-discover').classList.remove('config-tab-btn--active');
      viewInstalled.classList.remove('hidden');
      viewDiscover.classList.add('hidden');
      fetchSkills(); // refresh list
    });

    document.getElementById('skills-tab-discover').addEventListener('click', () => {
      document.getElementById('skills-tab-discover').classList.add('config-tab-btn--active');
      document.getElementById('skills-tab-installed').classList.remove('config-tab-btn--active');
      viewDiscover.classList.remove('hidden');
      viewInstalled.classList.add('hidden');
      loadCatalog();
    });

    // ── INSTALLED PLAYBOOKS ACTIONS ──
    // Expand/Collapse installer card
    const header = document.getElementById('skills-installer-header');
    const arrow = document.getElementById('skills-installer-arrow');
    const body = document.getElementById('skills-installer-body');
    
    const newHeader = header.cloneNode(true);
    header.parentNode.replaceChild(newHeader, header);
    
    document.getElementById('skills-installer-header').addEventListener('click', () => {
      const isHidden = body.classList.contains('hidden');
      if (isHidden) {
        body.classList.remove('hidden');
        arrow.style.transform = 'rotate(180deg)';
      } else {
        body.classList.add('hidden');
        arrow.style.transform = '';
      }
    });
    
    // Save Skill content
    const saveBtn = document.getElementById('btn-save-skill');
    const newSave = saveBtn.cloneNode(true);
    saveBtn.parentNode.replaceChild(newSave, saveBtn);
    document.getElementById('btn-save-skill').addEventListener('click', async () => {
      if (!selectedSkillId) return;
      const content = document.getElementById('skill-editor').value;
      try {
         await apiFetch(`/api/skills/${selectedSkillId}`, {
           method: 'PUT',
           body: JSON.stringify({ content })
         });
         showToast(`Saved instructions for ${selectedSkillId}`);
         fetchSkills(); // refresh description in list
      } catch (err) {
         showToast('Failed to save skill instructions', true);
      }
    });
    
    // Uninstall/Delete Skill
    const deleteBtn = document.getElementById('btn-delete-skill');
    const newDelete = deleteBtn.cloneNode(true);
    deleteBtn.parentNode.replaceChild(newDelete, deleteBtn);
    document.getElementById('btn-delete-skill').addEventListener('click', async () => {
      if (!selectedSkillId) return;
      if (!confirm(`Are you sure you want to uninstall and completely delete the skill "${selectedSkillId}"?`)) return;
      try {
         await apiFetch(`/api/skills/${selectedSkillId}`, {
           method: 'DELETE'
         });
         showToast(`Uninstalled skill ${selectedSkillId}`);
         selectedSkillId = null;
         
         document.getElementById('skill-editor-empty').classList.remove('hidden');
         document.getElementById('skill-editor-container').classList.add('hidden');
         fetchSkills();
      } catch (err) {
         showToast('Failed to uninstall skill', true);
      }
    });
    
    // Create Custom Skill
    const createBtn = document.getElementById('btn-create-skill');
    const newCreate = createBtn.cloneNode(true);
    createBtn.parentNode.replaceChild(newCreate, createBtn);
    document.getElementById('btn-create-skill').addEventListener('click', () => {
       const name = prompt("Enter a folder-friendly ID for your custom skill (e.g., security-auditor):");
       if (!name) return;
       const cleanName = name.toLowerCase().replace(/[^a-z0-9-_]/g, '');
       if (!cleanName) {
         showToast('Invalid skill ID', true);
         return;
       }
       
       const defaultContent = `---\nname: ${cleanName}\ndescription: Custom skill playbook description.\n---\n\n# ${cleanName}\n\nAdd your playbook instructions here.\n`;
       
       selectedSkillId = cleanName;
       
       // Open editor immediately
       document.getElementById('skill-editor-empty').classList.add('hidden');
       document.getElementById('skill-editor-container').classList.remove('hidden');
       document.getElementById('skill-editor').value = defaultContent;
       document.getElementById('skill-display-name').textContent = cleanName;
       document.getElementById('skill-display-path').textContent = `skills/${cleanName}/SKILL.md`;
       
       // Save it immediately to disk so it appears in the list
       apiFetch(`/api/skills/${cleanName}`, {
         method: 'PUT',
         body: JSON.stringify({ content: defaultContent })
       }).then(() => {
         showToast(`Created custom skill ${cleanName}`);
         fetchSkills();
       }).catch(() => {
         showToast('Failed to initialize skill on disk', true);
       });
    });
    
    // Clear Installer Console
    const clearConsoleBtn = document.getElementById('btn-clear-skills-console');
    const newClearConsole = clearConsoleBtn.cloneNode(true);
    clearConsoleBtn.parentNode.replaceChild(newClearConsole, clearConsoleBtn);
    document.getElementById('btn-clear-skills-console').addEventListener('click', () => {
      document.getElementById('skills-console').textContent = '';
    });

    // Run Bulk Installer
    const installBtn = document.getElementById('btn-install-skills');
    const newInstallBtn = installBtn.cloneNode(true);
    installBtn.parentNode.replaceChild(newInstallBtn, installBtn);
    document.getElementById('btn-install-skills').addEventListener('click', async () => {
       const categories = Array.from(document.querySelectorAll('input[name="skill-cat"]:checked')).map(el => el.value);
       const risks = Array.from(document.querySelectorAll('input[name="skill-risk"]:checked')).map(el => el.value);
       
       if (categories.length === 0) {
         showToast('Please select at least one category to install', true);
         return;
       }
       
       document.getElementById('skills-console-wrapper').classList.remove('hidden');
       document.getElementById('skills-console').textContent = 'Starting installation, please wait...\n';
       installBtn.disabled = true;
       
       try {
         await apiFetch('/api/skills/install', {
           method: 'POST',
           body: JSON.stringify({ categories, risks })
         });
         showToast('NPM installation started');
         startConsolePolling();
       } catch (err) {
         showToast('Failed to start installation', true);
         installBtn.disabled = false;
       }
    });

    // ── DISCOVER CATALOG ACTIONS ──
    const searchInput = document.getElementById('skills-catalog-search');
    const filterCat = document.getElementById('skills-catalog-filter-cat');
    const filterRisk = document.getElementById('skills-catalog-filter-risk');

    searchInput.addEventListener('input', renderCatalog);
    filterCat.addEventListener('change', renderCatalog);
    filterRisk.addEventListener('change', renderCatalog);
  }

  async function loadCatalog() {
    const loading = document.getElementById('skills-catalog-loading');
    const grid = document.getElementById('skills-catalog-grid');
    
    loading.classList.remove('hidden');
    grid.classList.add('hidden');
    
    try {
      catalogSkills = await apiFetch('/api/skills/catalog');
      loading.classList.add('hidden');
      grid.classList.remove('hidden');
      renderCatalog();
    } catch (err) {
      loading.innerHTML = '<span style="color: var(--danger)">Failed to load available catalog from GitHub. Check internet connection.</span>';
    }
  }

  function renderCatalog() {
    const grid = document.getElementById('skills-catalog-grid');
    const search = document.getElementById('skills-catalog-search').value.toLowerCase().trim();
    const cat = document.getElementById('skills-catalog-filter-cat').value;
    const risk = document.getElementById('skills-catalog-filter-risk').value;

    const filtered = catalogSkills.filter(skill => {
      // 1. Search Query
      const id = (skill.id || '').toLowerCase();
      const name = (skill.name || '').toLowerCase();
      const desc = (skill.description || '').toLowerCase();
      const matchesSearch = !search || id.includes(search) || name.includes(search) || desc.includes(search);
      
      // 2. Category
      const matchesCat = cat === 'ALL' || (skill.category || '').toLowerCase() === cat.toLowerCase();
      
      // 3. Risk
      const matchesRisk = risk === 'ALL' || (skill.risk || '').toLowerCase() === risk.toLowerCase();

      return matchesSearch && matchesCat && matchesRisk;
    });

    if (filtered.length === 0) {
      grid.innerHTML = '<div class="empty-state" style="grid-column: 1/-1"><span>No matching skills found in catalog</span></div>';
      return;
    }

    grid.innerHTML = filtered.map(skill => {
      const isInstalled = installedSkillIds.includes(skill.id);
      const catBadge = skill.category ? `<span class="catalog-badge catalog-badge--cat">${escapeHtml(skill.category)}</span>` : '';
      const riskBadge = skill.risk ? `<span class="catalog-badge catalog-badge--risk-${escapeHtml(skill.risk)}">Risk: ${escapeHtml(skill.risk)}</span>` : '';
      
      return `
        <div class="catalog-card">
          <div>
            <div class="catalog-card-header">
              <span class="catalog-card-title" title="${escapeHtml(skill.name)}">${escapeHtml(skill.name)}</span>
            </div>
            <div class="catalog-card-meta">
              ${catBadge}
              ${riskBadge}
            </div>
            <p class="catalog-card-desc" title="${escapeHtml(skill.description)}">${escapeHtml(skill.description || '(No description available)')}</p>
          </div>
          <div class="catalog-card-footer">
            ${isInstalled 
              ? `<button class="btn-outline" disabled style="opacity: 0.6; cursor: not-allowed; border-color: var(--success); color: #4ade80;">✓ Installed</button>`
              : `<button class="btn-primary btn-install-card" data-id="${escapeHtml(skill.id)}" style="padding: 6px 14px; font-size: 0.8rem;">Install Playbook</button>`
            }
          </div>
        </div>
      `;
    }).join('');

    // Attach card installation handlers
    grid.querySelectorAll('.btn-install-card').forEach(btn => {
      btn.addEventListener('click', async () => {
        const skillId = btn.dataset.id;
        btn.disabled = true;
        btn.textContent = 'Installing…';
        
        try {
          const res = await apiFetch('/api/skills/catalog/install', {
            method: 'POST',
            body: JSON.stringify({ skill_id: skillId })
          });
          showToast(`Successfully installed skill: ${skillId}`);
          
          // Add to local installed IDs list
          installedSkillIds.push(skillId);
          
          // Re-render discovery card to show Installed
          renderCatalog();
        } catch (err) {
          showToast(`Failed to install skill: ${skillId}`, true);
          btn.disabled = false;
          btn.textContent = 'Install Playbook';
        }
      });
    });
  }

  async function checkInstallerStatus() {
    try {
      const status = await apiFetch('/api/skills/install/status');
      if (status.running) {
        document.getElementById('skills-console-wrapper').classList.remove('hidden');
        document.getElementById('btn-install-skills').disabled = true;
        document.getElementById('skills-installer-body').classList.remove('hidden');
        document.getElementById('skills-installer-arrow').style.transform = 'rotate(180deg)';
        startConsolePolling();
      }
    } catch {}
  }

  function startConsolePolling() {
    if (skillsConsoleInterval) clearInterval(skillsConsoleInterval);
    
    skillsConsoleInterval = setInterval(async () => {
      try {
        const status = await apiFetch('/api/skills/install/status');
        const consoleEl = document.getElementById('skills-console');
        const dotEl = document.getElementById('skills-console-dot');
        consoleEl.textContent = status.logs || '';
        
        // Auto-scroll to bottom of console
        consoleEl.scrollTop = consoleEl.scrollHeight;
        
        if (!status.running) {
          clearInterval(skillsConsoleInterval);
          skillsConsoleInterval = null;
          document.getElementById('btn-install-skills').disabled = false;
          dotEl.className = 'status-dot'; // Turn off running glow
          showToast('Skills installation finished');
          fetchSkills(); // refresh list
        } else {
          dotEl.className = 'status-dot status-dot--running';
        }
      } catch {
        // Silently keep polling
      }
    }, 1000);
    
    // Store the interval so navigateTo cleanups catch it
    intervals.skillsConsole = skillsConsoleInterval;
  }

  // ══════════════════════════════════════════════════
  //  SHUTDOWN BUTTON
  // ══════════════════════════════════════════════════

  document.getElementById('btn-shutdown').addEventListener('click', async () => {
    if (!confirm('Are you sure you want to shut down the agent?')) return;
    try {
      await apiFetch('/api/shutdown', { method: 'POST' });
      showToast('Agent shutdown initiated');
      document.getElementById('status-dot').className = 'status-dot status-dot--stopped';
      document.getElementById('status-text').textContent = 'Agent Stopped';
    } catch {
      showToast('Failed to shut down agent', true);
    }
  });

  // ══════════════════════════════════════════════════
  //  BOOT
  // ══════════════════════════════════════════════════

  navigateTo(location.hash.slice(1) || 'overview');

});
