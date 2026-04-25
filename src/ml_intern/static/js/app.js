/**
 * ml-intern — Dashboard Client
 *
 * Job-based execution flow:
 * 1. User clicks command card
 * 2. POST /api/jobs → creates job, gets job_id
 * 3. GET /api/jobs/{job_id}/stream → SSE stream
 * 4. Lines rendered incrementally in output panel
 * 5. On completion, job appears in recent jobs
 *
 * Supports clean/raw output views and SSE reconnection.
 */

// ── State ───────────────────────────────────────────────────────
const state = {
    commands: {},
    configs: [],
    currentJobId: null,
    currentCommand: null,
    eventSource: null,
    viewMode: 'clean', // 'clean' or 'raw'
    outputLines: [],    // { stream, text, text_clean, timestamp }
    connected: false,
};

// ── Command icons ───────────────────────────────────────────────
const CMD_ICONS = {
    'doctor': '⚕',
    'info': 'ℹ',
    'paths': '📂',
    'validate-config': '✓',
};

// ── DOM References ──────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

const dom = {
    statusDot: $('status-dot'),
    statusText: $('status-text'),
    researchBadge: $('research-badge'),
    commandList: $('command-list'),
    configList: $('config-list'),
    configSelectArea: $('config-select-area'),
    configSelect: $('config-select'),
    outputHeader: $('output-header'),
    outputCmdLabel: $('output-cmd-label'),
    outputJobStatus: $('output-job-status'),
    outputMeta: $('output-meta'),
    outputBody: $('output-body'),
    outputWelcome: $('output-welcome'),
    btnViewClean: $('btn-view-clean'),
    btnViewRaw: $('btn-view-raw'),
    btnCancel: $('btn-cancel'),
    recentList: $('recent-list'),
    recentEmpty: $('recent-empty'),
    configModalOverlay: $('config-modal-overlay'),
    configModalTitle: $('config-modal-title'),
    configModalContent: $('config-modal-content'),
    configModalClose: $('config-modal-close'),
};

// ── API Layer ───────────────────────────────────────────────────

async function api(path, options = {}) {
    try {
        const res = await fetch(`/api${path}`, {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }
        return await res.json();
    } catch (err) {
        console.error(`API ${path}:`, err);
        throw err;
    }
}

// ── Status Check ────────────────────────────────────────────────

async function checkStatus() {
    setStatus('checking', 'Checking...');
    try {
        const status = await api('/status');
        if (status.health === 'healthy') {
            const version = status.cli_version ? ` v${status.cli_version}` : '';
            setStatus('connected', `Connected${version}`);
            state.connected = true;
        } else if (status.health === 'degraded') {
            setStatus('degraded', 'Degraded — CLI not callable');
            state.connected = false;
        } else {
            let reason = 'Unavailable';
            if (!status.python_exe_exists) reason = 'Python exe not found';
            else if (!status.project_root_exists) reason = 'Project root not found';
            setStatus('error', reason);
            state.connected = false;
        }
        // Update research badge
        updateResearchBadge(status.research_status);
    } catch {
        setStatus('error', 'Server unreachable');
        state.connected = false;
    }
}

function setStatus(type, text) {
    dom.statusDot.className = `status-dot ${type}`;
    dom.statusText.textContent = text;
}

function updateResearchBadge(status) {
    if (!dom.researchBadge) return;
    dom.researchBadge.className = `research-badge ${status || 'disabled'}`;
    const labels = {
        disabled: 'Research: disabled',
        unconfigured: 'Research: unconfigured',
        available: 'Research: available',
    };
    dom.researchBadge.textContent = labels[status] || 'Research: disabled';
}

// ── Load Commands ───────────────────────────────────────────────

async function loadCommands() {
    try {
        state.commands = await api('/commands');
        renderCommands();
    } catch {
        dom.commandList.innerHTML = '<div class="empty-state">Failed to load commands</div>';
    }
}

function renderCommands() {
    dom.commandList.innerHTML = '';
    for (const [name, cmd] of Object.entries(state.commands)) {
        const card = document.createElement('button');
        card.className = 'command-card';
        card.dataset.command = name;
        card.innerHTML = `
            <span class="cmd-icon">${CMD_ICONS[name] || '▸'}</span>
            <div class="cmd-info">
                <div class="cmd-name">${name}</div>
                <div class="cmd-desc">${cmd.description}</div>
            </div>
            <span class="cmd-phase">P${cmd.phase}</span>
        `;
        card.addEventListener('click', () => onCommandClick(name, cmd));
        dom.commandList.appendChild(card);
    }
}

// ── Load Configs ────────────────────────────────────────────────

async function loadConfigs() {
    try {
        state.configs = await api('/configs');
        renderConfigs();
        populateConfigSelect();
    } catch {
        dom.configList.innerHTML = '<div class="empty-state">No configs found</div>';
    }
}

function renderConfigs() {
    dom.configList.innerHTML = '';
    if (state.configs.length === 0) {
        dom.configList.innerHTML = '<div class="empty-state">No config files</div>';
        return;
    }
    for (const cfg of state.configs) {
        const item = document.createElement('button');
        item.className = 'config-item';
        item.innerHTML = `
            <span class="config-icon">⚙</span>
            <span>${cfg.name}</span>
            <span class="config-category">${cfg.category}</span>
        `;
        item.addEventListener('click', () => openConfigModal(cfg));
        dom.configList.appendChild(item);
    }
}

function populateConfigSelect() {
    dom.configSelect.innerHTML = '<option value="">— select a config file —</option>';
    for (const cfg of state.configs) {
        const opt = document.createElement('option');
        opt.value = cfg.path;
        opt.textContent = `${cfg.name} (${cfg.category})`;
        dom.configSelect.appendChild(opt);
    }
}

// ── Config Modal ────────────────────────────────────────────────

async function openConfigModal(cfg) {
    dom.configModalTitle.textContent = `${cfg.category}/${cfg.name}`;
    dom.configModalContent.textContent = 'Loading...';
    dom.configModalOverlay.classList.add('visible');

    try {
        const data = await api(`/configs/${cfg.category}/${cfg.name}`);
        dom.configModalContent.textContent = data.content;
    } catch (err) {
        dom.configModalContent.textContent = `Error: ${err.message}`;
    }
}

function closeConfigModal() {
    dom.configModalOverlay.classList.remove('visible');
}

// ── Command Execution ───────────────────────────────────────────

async function onCommandClick(name, cmd) {
    // Highlight active card
    document.querySelectorAll('.command-card').forEach(c => c.classList.remove('active'));
    document.querySelector(`[data-command="${name}"]`)?.classList.add('active');

    state.currentCommand = name;

    // Show/hide config select for validate-config
    if (cmd.needs_config) {
        dom.configSelectArea.classList.add('visible');
        return; // Wait for config selection + enter/click
    }

    dom.configSelectArea.classList.remove('visible');
    await executeCommand(name);
}

async function executeCommand(name, configFile = null, flags = {}) {
    if (!state.connected) {
        showError('Not connected to lex_study_foundation');
        return;
    }

    // Close any existing SSE stream
    closeStream();

    // Clear output
    clearOutput();
    showOutputHeader(name, 'queued');

    try {
        const body = { command: name };
        if (configFile) body.config_file = configFile;
        if (Object.keys(flags).length) body.flags = flags;

        const job = await api('/jobs', {
            method: 'POST',
            body: JSON.stringify(body),
        });

        state.currentJobId = job.job_id;
        updateJobStatus(job.status);
        dom.btnCancel.style.display = job.status === 'running' ? 'inline-block' : 'none';

        // Connect SSE stream
        openStream(job.job_id);
    } catch (err) {
        showError(err.message);
    }
}

// ── SSE Stream ──────────────────────────────────────────────────

function openStream(jobId) {
    closeStream();

    const es = new EventSource(`/api/jobs/${jobId}/stream`);
    state.eventSource = es;

    es.addEventListener('output', (event) => {
        const line = JSON.parse(event.data);
        state.outputLines.push(line);
        appendOutputLine(line);
    });

    es.addEventListener('status', (event) => {
        const job = JSON.parse(event.data);
        updateJobStatus(job.status);
        updateMeta(job);
        dom.btnCancel.style.display = 'none';
        closeStream();
        loadRecentJobs();
    });

    es.onerror = () => {
        // SSE connection lost — check job status
        closeStream();
        if (state.currentJobId) {
            pollJobStatus(state.currentJobId);
        }
    };
}

function closeStream() {
    if (state.eventSource) {
        state.eventSource.close();
        state.eventSource = null;
    }
}

async function pollJobStatus(jobId) {
    try {
        const job = await api(`/jobs/${jobId}`);
        updateJobStatus(job.status);
        updateMeta(job);
        if (job.status === 'running') {
            // Reconnect stream
            openStream(jobId);
        } else {
            dom.btnCancel.style.display = 'none';
            loadRecentJobs();
        }
    } catch {
        // Job not found, stop polling
    }
}

// ── Output Rendering ────────────────────────────────────────────

function clearOutput() {
    state.outputLines = [];
    dom.outputBody.innerHTML = '';
    dom.outputWelcome.style.display = 'none';
    dom.outputMeta.textContent = '';
}

function showOutputHeader(cmdName, status) {
    dom.outputHeader.style.display = 'flex';
    dom.outputCmdLabel.textContent = `$ lex-study-foundation ${cmdName}`;
    updateJobStatus(status);
}

function updateJobStatus(status) {
    dom.outputJobStatus.textContent = status;
    dom.outputJobStatus.className = `job-status ${status}`;
    dom.btnCancel.style.display = status === 'running' ? 'inline-block' : 'none';
}

function updateMeta(job) {
    const parts = [];
    if (job.exit_code !== null && job.exit_code !== undefined) {
        parts.push(`exit: ${job.exit_code}`);
    }
    if (job.duration_ms !== null && job.duration_ms !== undefined) {
        parts.push(formatDuration(job.duration_ms));
    }
    if (job.finished_at) {
        const d = new Date(job.finished_at);
        parts.push(d.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
    }
    dom.outputMeta.textContent = parts.join(' │ ');
}

function appendOutputLine(line) {
    const div = document.createElement('div');
    div.className = `output-line ${line.stream === 'stderr' ? 'stderr' : ''}`;
    div.textContent = state.viewMode === 'clean' ? line.text_clean : line.text;
    dom.outputBody.appendChild(div);

    // Auto-scroll to bottom
    dom.outputBody.scrollTop = dom.outputBody.scrollHeight;
}

function rerenderOutput() {
    dom.outputBody.innerHTML = '';
    for (const line of state.outputLines) {
        const div = document.createElement('div');
        div.className = `output-line ${line.stream === 'stderr' ? 'stderr' : ''}`;
        div.textContent = state.viewMode === 'clean' ? line.text_clean : line.text;
        dom.outputBody.appendChild(div);
    }
    dom.outputBody.scrollTop = dom.outputBody.scrollHeight;
}

function showError(message) {
    const div = document.createElement('div');
    div.className = 'output-line error-line';
    div.textContent = `Error: ${message}`;
    dom.outputBody.appendChild(div);
}

// ── Recent Jobs ─────────────────────────────────────────────────

async function loadRecentJobs() {
    try {
        const jobs = await api('/jobs/recent?limit=15');
        renderRecentJobs(jobs);
    } catch {
        // Silently fail — recent jobs is non-critical
    }
}

function renderRecentJobs(jobs) {
    if (!jobs.length) {
        dom.recentEmpty.style.display = 'block';
        return;
    }
    dom.recentEmpty.style.display = 'none';

    // Keep the empty-state element, clear the rest
    const existing = dom.recentList.querySelectorAll('.recent-item');
    existing.forEach(el => el.remove());

    for (const job of jobs) {
        const item = document.createElement('div');
        item.className = 'recent-item';
        item.dataset.jobId = job.job_id;
        item.innerHTML = `
            <span class="ri-status ${job.status}"></span>
            <span class="ri-cmd">${job.command}</span>
            <span class="ri-exit">${job.exit_code !== null ? `exit ${job.exit_code}` : '—'}</span>
            <span class="ri-duration">${job.duration_ms !== null ? formatDuration(job.duration_ms) : '—'}</span>
            <span class="ri-time">${formatTime(job.created_at)}</span>
        `;
        item.addEventListener('click', () => viewJobOutput(job.job_id));
        dom.recentList.appendChild(item);
    }
}

async function viewJobOutput(jobId) {
    try {
        const job = await api(`/jobs/${jobId}`);
        state.currentJobId = jobId;

        clearOutput();
        showOutputHeader(job.command, job.status);
        updateMeta(job);

        // Open stream to get buffered output
        openStream(jobId);
    } catch (err) {
        showError(err.message);
    }
}

// ── View Mode Toggle ────────────────────────────────────────────

function setViewMode(mode) {
    state.viewMode = mode;
    dom.btnViewClean.classList.toggle('active', mode === 'clean');
    dom.btnViewRaw.classList.toggle('active', mode === 'raw');
    rerenderOutput();
}

// ── Cancel Job ──────────────────────────────────────────────────

async function cancelCurrentJob() {
    if (!state.currentJobId) return;
    try {
        const job = await api(`/jobs/${state.currentJobId}/cancel`, { method: 'POST' });
        updateJobStatus(job.status);
        dom.btnCancel.style.display = 'none';
        closeStream();
        loadRecentJobs();
    } catch (err) {
        showError(err.message);
    }
}

// ── Config Select Handler ───────────────────────────────────────

function onConfigSelectChange() {
    const configPath = dom.configSelect.value;
    if (!configPath || !state.currentCommand) return;
    executeCommand(state.currentCommand, configPath);
}

// ── Utilities ───────────────────────────────────────────────────

function formatDuration(ms) {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
}

function formatTime(isoStr) {
    try {
        const d = new Date(isoStr);
        return d.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
        return '—';
    }
}

// ── Event Listeners ─────────────────────────────────────────────

dom.btnViewClean.addEventListener('click', () => setViewMode('clean'));
dom.btnViewRaw.addEventListener('click', () => setViewMode('raw'));
dom.btnCancel.addEventListener('click', cancelCurrentJob);
dom.configSelect.addEventListener('change', onConfigSelectChange);
dom.configModalClose.addEventListener('click', closeConfigModal);
dom.configModalOverlay.addEventListener('click', (e) => {
    if (e.target === dom.configModalOverlay) closeConfigModal();
});

// Keyboard: Escape closes modal
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeConfigModal();
});

// ── Initialize ──────────────────────────────────────────────────

async function init() {
    await checkStatus();
    await Promise.all([loadCommands(), loadConfigs(), loadRecentJobs()]);

    // Re-check status periodically
    setInterval(checkStatus, 30000);
}

init();
