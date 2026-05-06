import re

with open('dev_shell.html', 'r') as f:
    content = f.read()

# Split content at <script>
parts = content.split('<script>')
if len(parts) != 2:
    print("Error splitting script")
    exit(1)

html_part = parts[0]
script_part = parts[1]

new_script = """
const API_BASE = "";
let sessionState = null;
let currentInstData = null;
let currentResponses = {};
let selectedIntakeCats = [];

// Component 1: View Routing State
let currentView = 'welcome';
let currentPlanetId = null;
let lastResultData = null;
let autoNarrate = localStorage.getItem('helix_auto_narrate') === 'true';

// Component 8: Initialize toggle
document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.getElementById('auto-narrate-toggle');
    if (toggle) toggle.checked = autoNarrate;
});

function toggleAutoNarrate(el) {
    autoNarrate = el.checked;
    localStorage.setItem('helix_auto_narrate', autoNarrate);
}

const INTAKE_CATS = [
    {id: 'mood_anxiety', label: 'Mood and anxiety'},
    {id: 'sleep_energy', label: 'Sleep and energy'},
    {id: 'relationships', label: 'Relationships and connection'},
    {id: 'attention_focus', label: 'Attention and focus'},
    {id: 'identity_personality', label: 'Identity and personality'},
    {id: 'values_meaning', label: 'Values and meaning'},
    {id: 'childhood_history', label: 'Childhood and history'},
    {id: 'neurodivergence', label: 'Neurodivergence'},
    {id: 'trauma_experiences', label: 'Trauma and past experiences'},
    {id: 'general', label: 'General self-understanding'}
];

const PLANET_COLORS = {
    mercury: 'var(--mercury)', venus: 'var(--venus)', earth: 'var(--earth)', 
    mars: 'var(--mars)', jupiter: 'var(--jupiter)', saturn: 'var(--saturn)', 
    neptune: 'var(--neptune)', uranus: 'var(--uranus)'
};

const PLANET_IDS = ['mercury','venus','earth','mars','jupiter','saturn','uranus','neptune'];

async function api(path, options = {}) {
    const res = await fetch(API_BASE + path, {
        ...options,
        headers: { 'Content-Type': 'application/json', ...options.headers }
    });
    const data = await res.json();
    if (!res.ok) {
        let msg = data.detail;
        if (typeof msg === 'object') msg = JSON.stringify(msg, null, 2);
        throw new Error(msg || JSON.stringify(data));
    }
    return data;
}

function copySessionId() {
    const el = document.getElementById('session-id-input');
    if (!el.value) return;
    navigator.clipboard.writeText(el.value);
    const btn = document.getElementById('copy-btn');
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = 'Copy', 2000);
}

async function createSession() {
    try {
        sessionState = await api('/sessions', { method: 'POST' });
        document.getElementById('session-id-input').value = sessionState.session_id;
        currentView = 'welcome';
        renderState();
    } catch (e) { alert(e.message); }
}

async function createQuickStartSession() {
    try {
        sessionState = await api('/sessions/quick-start', { method: 'POST' });
        document.getElementById('session-id-input').value = sessionState.session_id;
        currentView = 'welcome';
        renderState();
    } catch (e) { alert(e.message); }
}

async function loadSession() {
    const id = document.getElementById('session-id-input').value.trim();
    if (!id) return;
    try {
        sessionState = await api(`/sessions/${id}`);
        currentView = 'welcome';
        renderState();
    } catch (e) { alert(e.message); }
}

async function acknowledgeSafety() {
    try {
        sessionState = await api(`/sessions/${sessionState.session_id}/acknowledge-safety`, { method: 'POST' });
        document.getElementById('safety-overlay').style.display = 'none';
        renderState();
    } catch (e) { alert(e.message); }
}

async function dismissFatigue() {
    try {
        sessionState = await api(`/sessions/${sessionState.session_id}/dismiss-fatigue`, { method: 'POST' });
        document.getElementById('fatigue-overlay').style.display = 'none';
        renderState();
    } catch (e) { alert(e.message); }
}

function renderState(preserveView = false) {
    if (!sessionState) return;
    
    // Safety check
    if (sessionState.state === 'SAFETY_PAUSED') {
        document.getElementById('safety-overlay').style.display = 'flex';
    } else {
        document.getElementById('safety-overlay').style.display = 'none';
    }
    
    // Fatigue check
    if (sessionState.fatigue_nudge) {
        document.getElementById('fatigue-overlay').style.display = 'flex';
    } else {
        document.getElementById('fatigue-overlay').style.display = 'none';
    }
    
    renderPlanetNav();
    updateAIInvestigationPanel(); // Legacy Dev Tools update
    updateReadinessDots(); // Pre-update readiness dots
    
    // Decide view if not preserving
    if (!preserveView) {
        if (sessionState.state === 'CORE_FLOW_IN_PROGRESS') {
            currentView = 'core-flow';
        } else if (sessionState.state === 'EXPLORING' && currentView === 'welcome') {
            currentView = 'dashboard';
        }
    }
    
    navigateTo(currentView, { renderOnly: true });
}

// Component 1: Central Navigation Router
function navigateTo(view, params = {}) {
    if (!sessionState) return;
    if (!params.renderOnly) currentView = view;
    
    const breadcrumb = document.getElementById('breadcrumb-area');
    const cfProgress = document.getElementById('core-flow-progress-area');
    const content = document.getElementById('content-area');
    
    breadcrumb.style.display = 'none';
    cfProgress.style.display = 'none';
    
    if (view === 'welcome') {
        renderWelcome();
    } else if (view === 'core-flow') {
        renderCoreFlow();
    } else if (view === 'dashboard') {
        renderBreadcrumb([{label: 'Dashboard'}]);
        renderDashboard();
    } else if (view === 'planet-detail') {
        if (params.planetId) currentPlanetId = params.planetId;
        renderBreadcrumb([
            {label: 'Dashboard', view: 'dashboard'},
            {label: getPlanetName(currentPlanetId)}
        ]);
        renderPlanetDetail(currentPlanetId);
    } else if (view === 'instrument') {
        renderBreadcrumb([
            {label: 'Dashboard', view: 'dashboard'},
            {label: getPlanetName(currentPlanetId), view: 'planet-detail', params: {planetId: currentPlanetId}},
            {label: params.instrumentName || 'Assessment'}
        ]);
        renderInstrumentForm(currentInstData);
    } else if (view === 'result') {
        renderBreadcrumb([
            {label: 'Dashboard', view: 'dashboard'},
            {label: getPlanetName(currentPlanetId), view: 'planet-detail', params: {planetId: currentPlanetId}},
            {label: 'Result'}
        ]);
        renderResultCard(lastResultData);
    }
}

function renderBreadcrumb(pathItems) {
    const area = document.getElementById('breadcrumb-area');
    area.style.display = 'block';
    
    let html = '<div class="breadcrumb-bar">';
    html += '<span style="font-weight: 600; color: var(--text);">HELIX</span>';
    
    pathItems.forEach(item => {
        html += ` <span style="color: var(--border);">/</span> `;
        if (item.view) {
            const paramStr = item.params ? JSON.stringify(item.params).replace(/"/g, "'") : '{}';
            html += `<span class="breadcrumb-link" onclick="navigateTo('${item.view}', ${paramStr})">${item.label}</span>`;
        } else {
            html += `<span style="color: var(--text);">${item.label}</span>`;
        }
    });
    
    html += '</div>';
    area.innerHTML = html;
}

function getPlanetName(pid) {
    if (!sessionState || !sessionState.planet_states) return pid;
    const p = sessionState.planet_states.find(x => x.planet_id === pid);
    return p ? p.display_name.split('—')[0].trim() : pid;
}

function renderPlanetNav() {
    const nav = document.getElementById('planet-nav');
    if (!sessionState.planet_states || sessionState.planet_states.length === 0) {
        nav.innerHTML = '<div style="color:var(--text-light); font-size:0.9rem;">Complete core flow to unlock map.</div>';
        return;
    }
    
    let html = '';
    sessionState.planet_states.forEach(planet => {
        const color = PLANET_COLORS[planet.planet_id] || '#fff';
        const isLocked = planet.status === 'LOCKED';
        const lockIcon = isLocked ? '🔒 ' : '';
        
        let instHtml = '';
        const allInsts = [...new Set([...planet.available_instruments, ...planet.completed_instruments])];
        allInsts.forEach(inst => {
            const isComp = planet.completed_instruments.includes(inst);
            const isAvail = planet.available_instruments.includes(inst);
            let icon = '○';
            if (isComp) icon = '● <span style="color:var(--success);">✓</span>';
            else if (isAvail && planet.status.includes('SCANNED')) icon = '→';
            
            if (isAvail || isComp) {
                instHtml += `
                    <div class="instrument-item" onclick="${isAvail ? `currentPlanetId='${planet.planet_id}'; loadInstrument('${inst}')` : ''}">
                        <span class="status-icon">${icon}</span>
                        ${inst.toUpperCase()}
                    </div>
                `;
            }
        });
        
        html += `
            <div class="planet-group" onclick="this.classList.toggle('expanded')">
                <div class="planet-header" style="${isLocked ? 'opacity: 0.5;' : ''}" onclick="event.stopPropagation(); if(!${isLocked}) navigateTo('planet-detail', {planetId: '${planet.planet_id}'})">
                    <div class="planet-title">
                        <div class="planet-icon" style="background: ${color};"></div>
                        ${lockIcon}${planet.display_name.split('—')[0].trim()}
                    </div>
                    <div style="font-size: 0.8rem; color: var(--text-light);">${Math.round(planet.completion_pct * 100)}%</div>
                </div>
                ${!isLocked ? `<div class="instrument-list">${instHtml}</div>` : ''}
            </div>
        `;
    });
    nav.innerHTML = html;
}

// Component 7: Core Flow Progress
function renderCoreFlowProgress(currentStepKey) {
    const area = document.getElementById('core-flow-progress-area');
    area.style.display = 'block';
    
    const steps = [
        {key: 'intake', label: 'Welcome'},
        {key: 'pbat', label: 'How you\\'ve been'},
        {key: 'anchors', label: 'Right now'},
        {key: 'wsas', label: 'Daily life'},
        {key: 'pcptsd5', label: 'Recent experiences'}
    ];
    
    let currentIndex = steps.findIndex(s => s.key === currentStepKey);
    if (currentIndex === -1) currentIndex = 0;
    
    let html = '<div class="core-flow-progress">';
    steps.forEach((step, idx) => {
        let stateClass = '';
        if (idx < currentIndex) stateClass = 'completed';
        else if (idx === currentIndex) stateClass = 'active';
        
        const icon = idx < currentIndex ? '✓' : (idx + 1);
        
        html += `
            <div class="cf-step ${stateClass}">
                <div style="width: 20px; height: 20px; border-radius: 50%; background: ${idx <= currentIndex ? 'var(--primary)' : 'var(--border)'}; color: ${idx <= currentIndex ? 'white' : 'var(--text-light)'}; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: bold;">
                    ${icon}
                </div>
                ${step.label}
            </div>
        `;
        
        if (idx < steps.length - 1) {
            html += '<div class="cf-divider"></div>';
        }
    });
    html += '</div>';
    area.innerHTML = html;
}

function renderCoreFlow() {
    const step = sessionState.available[0];
    renderCoreFlowProgress(step);
    
    if (step === 'intake') renderIntake();
    else if (step === 'pbat') { currentPlanetId = 'mercury'; loadInstrument('pbat', true); }
    else if (step === 'anchors') renderAnchors();
    else if (step === 'wsas') { currentPlanetId = 'earth'; loadInstrument('wsas', true); }
    else if (step === 'pcptsd5') { currentPlanetId = 'mars'; loadInstrument('pcptsd5', true); }
    else if (sessionState.state === 'EXPLORING') navigateTo('dashboard');
}

function renderWelcome() {
    if (sessionState && sessionState.state === 'EXPLORING') {
        navigateTo('dashboard');
        return;
    }
    document.getElementById('content-area').innerHTML = `
        <div style="text-align: center; margin-top: 20vh; color: var(--text-light);">
            <h2>Welcome to Helix</h2>
            <p>Load a session or click Quick Start.</p>
        </div>
    `;
}

// Component 2: Dashboard
function renderDashboard() {
    const area = document.getElementById('content-area');
    let html = '<div style="max-width: 900px; margin: 0 auto; padding-bottom: 3rem;">';
    
    // Red Thread
    if (sessionState.intake && sessionState.intake.red_thread_question) {
        html += `
            <div style="margin-bottom: 2rem; border-left: 4px solid var(--uranus); padding-left: 1rem;">
                <p style="font-style: italic; font-size: 1.1rem; margin: 0; color: var(--text);">"${sessionState.intake.red_thread_question}"</p>
            </div>
        `;
    }
    
    // Anchor Scores
    if (sessionState.anchors) {
        html += '<div style="display: flex; gap: 1rem; margin-bottom: 2rem;">';
        ['mood', 'energy', 'focus'].forEach(a => {
            const val = sessionState.anchors[a];
            html += `
                <div style="flex: 1; background: rgba(255,255,255,0.02); padding: 1rem; border-radius: var(--radius); border: 1px solid var(--border); text-align: center;">
                    <div style="font-size: 0.8rem; color: var(--text-light); text-transform: uppercase;">${a}</div>
                    <div style="font-size: 1.5rem; font-weight: bold; color: var(--primary);">${val !== undefined ? val : '-'}</div>
                </div>
            `;
        });
        html += '</div>';
    }
    
    // Planet Grid
    if (sessionState.planet_states && sessionState.planet_states.length > 0) {
        html += '<h3 style="margin-top: 0;">Planetary Map</h3>';
        html += '<div class="dashboard-grid">';
        sessionState.planet_states.forEach(planet => {
            const color = PLANET_COLORS[planet.planet_id] || '#fff';
            const isLocked = planet.status === 'LOCKED';
            const compCount = planet.completed_instruments.length;
            const totalCount = compCount + planet.available_instruments.length;
            
            html += `
                <div class="planet-card ${isLocked ? 'locked' : ''}" onclick="if(!${isLocked}) navigateTo('planet-detail', {planetId: '${planet.planet_id}'})">
                    <div class="planet-card-header">
                        <div class="planet-card-title">
                            <div class="planet-icon" style="background: ${color};"></div>
                            ${planet.display_name.split('—')[0].trim()}
                        </div>
                        <div class="planet-card-status">${isLocked ? 'Locked' : planet.status.includes('SCANNED') ? 'Scanned' : 'Exploring'}</div>
                    </div>
                    <div style="font-size: 0.8rem; color: var(--text-light); margin-top: 0.5rem;">
                        ${compCount} of ${totalCount} instruments
                    </div>
                    <div class="comp-bar-bg" style="margin-top: auto; height: 4px;">
                        <div class="comp-bar-fill" style="width: ${planet.completion_pct * 100}%; background: ${color};"></div>
                    </div>
                </div>
            `;
        });
        html += '</div>';
    }

    // Composites
    if (sessionState.composites && sessionState.composites.length > 0) {
        html += '<h3 style="margin-top: 3rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem;">Composites</h3>';
        html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">';
        sessionState.composites.forEach(comp => {
            if (!comp.score && !comp.components_present.length) return;
            const scoreVal = comp.score;
            const pct = scoreVal != null ? Math.max(0, Math.min(100, (scoreVal + 3) / 6 * 100)) : 0;
            html += `
                <div class="composite-item">
                    <div style="display: flex; justify-content: space-between; font-size: 0.9rem;">
                        <strong style="color: var(--text);">${comp.index_id.replace(/_/g, ' ').toUpperCase()}</strong>
                        <span style="color: var(--primary);">${scoreVal != null ? scoreVal.toFixed(1) : 'N/A'}</span>
                    </div>
                    <div style="font-size: 0.8rem; color: var(--text-light); margin-top: 0.2rem;">${comp.label || 'Insufficient data'}</div>
                    <div class="comp-bar-bg">
                        <div class="comp-bar-fill" style="width: ${pct}%;"></div>
                    </div>
                </div>
            `;
        });
        html += '</div>';
    }

    // Narratives
    html += '<h3 style="margin-top: 3rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem;">Insights</h3>';
    
    // Mission Control & Red Thread
    html += '<div style="display: flex; gap: 1rem;">';
    html += '<div style="flex: 1;"><div style="display:flex; justify-content:space-between; align-items:center;"><h4>Mission Control</h4>';
    if (!autoNarrate) html += '<button class="btn-outline" style="padding:0.2rem 0.5rem; font-size:0.75rem;" onclick="narrateTask(\\'mission_control\\')">Generate</button>';
    html += '</div><div id="out-mission-control" class="narrate-output"></div></div>';
    
    html += '<div style="flex: 1;"><div style="display:flex; justify-content:space-between; align-items:center;"><h4>Red Thread</h4>';
    if (!autoNarrate) html += '<button class="btn-outline" style="padding:0.2rem 0.5rem; font-size:0.75rem;" onclick="narrateTask(\\'red_thread\\')">Generate</button>';
    html += '</div><div id="out-red-thread" class="narrate-output"></div></div>';
    html += '</div>';
    
    html += '<div style="margin-top: 2rem;"><div style="display:flex; justify-content:space-between; align-items:center;"><h4>Full Formulation</h4>';
    if (!autoNarrate) html += '<button class="btn-outline" style="padding:0.2rem 0.5rem; font-size:0.75rem;" onclick="narrateTask(\\'full_formulation\\')">Generate</button>';
    html += '</div><div id="out-full-formulation" class="narrate-output"></div></div>';
    
    html += '</div>';
    area.innerHTML = html;
    
    // Trigger auto narrate if enabled
    if (autoNarrate && aiReadiness) {
        ['mission_control', 'full_formulation', 'red_thread'].forEach(task => {
            if (aiReadiness[task] && aiReadiness[task].ready) {
                document.getElementById('out-' + task.replace('_', '-')).classList.add('open');
                narrateTask(task, {}, true);
            }
        });
    }
}

// Component 3: Planet Detail View
function renderPlanetDetail(planetId) {
    if (!sessionState || !sessionState.planet_states) return;
    const planet = sessionState.planet_states.find(p => p.planet_id === planetId);
    if (!planet) return;
    
    const color = PLANET_COLORS[planetId] || '#fff';
    const area = document.getElementById('content-area');
    
    let html = '<div style="max-width: 800px; margin: 0 auto; padding-bottom: 3rem;">';
    
    html += `
        <div style="border-left: 4px solid ${color}; padding-left: 1.5rem; margin-bottom: 2rem;">
            <h1 style="margin: 0; font-size: 2rem;">${planet.display_name}</h1>
            <div style="font-size: 0.9rem; color: var(--text-light); margin-top: 0.5rem; display: flex; gap: 1rem;">
                <span>Status: ${planet.status}</span>
                <span>Completion: ${Math.round(planet.completion_pct * 100)}%</span>
            </div>
        </div>
    `;
    
    // Planet Summary Narrative
    html += `
        <div style="margin-bottom: 2.5rem;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 0.5rem;">
                <h3 style="margin:0;">Planet Summary</h3>
                ${!autoNarrate ? `<button class="btn-outline" style="padding:0.2rem 0.5rem; font-size:0.75rem;" onclick="narratePlanet('${planetId}')">Generate Summary</button>` : ''}
            </div>
            <div id="out-planet-summary-${planetId}" class="narrate-output"></div>
        </div>
    `;
    
    html += '<div style="display: flex; gap: 2rem;">';
    
    // Left col: Available
    html += '<div style="flex: 1;">';
    html += '<h3 style="border-bottom: 1px solid var(--border); padding-bottom: 0.5rem;">Available to Explore</h3>';
    if (planet.available_instruments.length === 0) {
        html += '<p style="color: var(--text-light); font-size: 0.85rem;">Nothing available right now.</p>';
    } else {
        planet.available_instruments.forEach(inst => {
            html += `
                <div class="planet-card" style="margin-bottom: 1rem; border-left: 2px solid ${color};">
                    <div style="font-weight: 600; font-size: 1.1rem; margin-bottom: 0.5rem;">${inst.toUpperCase()}</div>
                    <button onclick="loadInstrument('${inst}')" style="width: 100%;">Begin Assessment</button>
                </div>
            `;
        });
    }
    html += '</div>';
    
    // Right col: Completed
    html += '<div style="flex: 1;">';
    html += '<h3 style="border-bottom: 1px solid var(--border); padding-bottom: 0.5rem;">Completed</h3>';
    if (planet.completed_instruments.length === 0) {
        html += '<p style="color: var(--text-light); font-size: 0.85rem;">No instruments completed yet.</p>';
    } else {
        planet.completed_instruments.forEach(inst => {
            // Find past result if we stored it
            const pastRes = window.storedResults && window.storedResults[inst];
            html += `
                <div class="planet-card" style="margin-bottom: 1rem; background: rgba(255,255,255,0.02); opacity: 0.8;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="font-weight: 600;">${inst.toUpperCase()}</div>
                        ${pastRes && pastRes.score ? `<div style="color: var(--primary); font-weight: bold;">Score: ${pastRes.score.total_score}</div>` : '<div style="color: var(--success);">✓</div>'}
                    </div>
                </div>
            `;
        });
    }
    html += '</div>';
    
    html += '</div></div>';
    area.innerHTML = html;
    
    if (autoNarrate && aiReadiness && aiReadiness.planet_summary && aiReadiness.planet_summary[planetId]) {
        if (aiReadiness.planet_summary[planetId].ready) {
            document.getElementById(`out-planet-summary-${planetId}`).classList.add('open');
            // Mock out-planet-summary ID for narrateTask
            const oldId = document.getElementById('out-planet-summary');
            if (oldId) oldId.id = 'out-planet-summary-old';
            document.getElementById(`out-planet-summary-${planetId}`).id = 'out-planet-summary';
            narratePlanet(planetId);
        }
    }
}

// Intake functions
function renderIntake() {
    selectedIntakeCats = [];
    document.getElementById('content-area').innerHTML = `
        <div class="framing-block">
            <h2>Welcome to Helix</h2>
            <p style="color: var(--text-light);">We'll start with a few questions to understand what brings you here and set up your exploration.</p>
        </div>
        <form onsubmit="submitIntake(event)">
            <div class="form-group">
                <label>In one or two sentences, what would you most like to understand about yourself right now?</label>
                <textarea id="intake-red" rows="3" required placeholder="I want to understand..."></textarea>
            </div>
            <div class="form-group">
                <label>Choose and rank up to 5 areas you'd like to focus on (click in order of priority):</label>
                <div id="intake-cats-container" style="margin-top: 0.5rem;"></div>
            </div>
            <button type="submit" style="width: 100%; padding: 1rem; font-size: 1.1rem;">Continue</button>
        </form>
    `;
    renderIntakeCats();
}

function renderIntakeCats() {
    const container = document.getElementById('intake-cats-container');
    if (!container) return;
    
    container.innerHTML = INTAKE_CATS.map(cat => {
        const idx = selectedIntakeCats.indexOf(cat.id);
        const isSelected = idx > -1;
        const badge = isSelected ? `<span class="rank-badge">${idx + 1}</span>` : '';
        return `<div class="rank-chip ${isSelected ? 'selected' : ''}" onclick="toggleIntakeCat('${cat.id}')">${badge}${cat.label}</div>`;
    }).join('');
}

function toggleIntakeCat(id) {
    const idx = selectedIntakeCats.indexOf(id);
    if (idx > -1) {
        selectedIntakeCats.splice(idx, 1);
    } else {
        if (selectedIntakeCats.length >= 5) {
            alert('You can only select up to 5 areas.');
            return;
        }
        selectedIntakeCats.push(id);
    }
    renderIntakeCats();
}

async function submitIntake(e) {
    e.preventDefault();
    const red = document.getElementById('intake-red').value;
    if (selectedIntakeCats.length === 0) { alert('Select 1-5 categories'); return; }
    
    try {
        sessionState = await api(`/sessions/${sessionState.session_id}/intake`, {
            method: 'POST', body: JSON.stringify({ red_thread_question: red, categories: selectedIntakeCats })
        });
        renderState();
    } catch (e) { alert(e.message); }
}

function renderAnchors() {
    document.getElementById('content-area').innerHTML = `
        <div class="framing-block">
            <h2>Current State</h2>
            <p style="color: var(--text-light);">Right now, how would you rate your...</p>
        </div>
        <form onsubmit="submitAnchors(event)">
            ${['mood', 'energy', 'focus'].map(a => `
                <div class="form-group">
                    <label style="text-transform: capitalize;">${a}</label>
                    <input type="range" id="anchor-${a}" min="0" max="10" value="5" oninput="document.getElementById('val-${a}').textContent=this.value">
                    <div class="slider-labels"><span>0 (Very Low)</span><span>10 (Very High)</span></div>
                    <div class="slider-value-display" id="val-${a}">5</div>
                </div>
            `).join('')}
            <button type="submit" style="width: 100%; padding: 1rem; font-size: 1.1rem;">Continue</button>
        </form>
    `;
}

async function submitAnchors(e) {
    e.preventDefault();
    try {
        sessionState = await api(`/sessions/${sessionState.session_id}/anchors`, {
            method: 'POST', 
            body: JSON.stringify({
                mood: parseInt(document.getElementById('anchor-mood').value),
                energy: parseInt(document.getElementById('anchor-energy').value),
                focus: parseInt(document.getElementById('anchor-focus').value)
            })
        });
        renderState();
    } catch (e) { alert(e.message); }
}

async function loadInstrument(instId, isCoreFlow = false) {
    try {
        const data = await api(`/sessions/${sessionState.session_id}/instruments/${instId}`);
        currentInstData = data;
        
        if (instId === 'aces') {
            document.getElementById('aces-overlay').style.display = 'flex';
        } else {
            if (!isCoreFlow) navigateTo('instrument', { instrumentName: data.instrument_name });
            else renderInstrumentForm(data);
        }
    } catch (e) { alert(e.message); }
}

// Component 5: Instrument Form Enhancements
function renderInstrumentForm(data) {
    currentResponses = {};
    const area = document.getElementById('content-area');
    
    let html = '';
    
    // Back button if in EXPLORING mode
    if (sessionState.state === 'EXPLORING' && currentPlanetId) {
        html += `<button class="btn-outline" style="margin-bottom: 1.5rem; padding: 0.3rem 0.8rem; font-size: 0.85rem;" onclick="navigateTo('planet-detail', {planetId: currentPlanetId})">← Back to ${getPlanetName(currentPlanetId)}</button>`;
    }
    
    // Bridge card injected here if we just arrived
    if (window.pendingBridgeHtml) {
        html += window.pendingBridgeHtml;
        window.pendingBridgeHtml = null;
    }
    
    html += `
        <div class="framing-block">
            <h2>${data.instrument_name}</h2>
            ${data.time_window_text ? `<p style="color: var(--text-light); font-style: italic;">${data.time_window_text}</p>` : ''}
            ${data.parent_instance_id ? `<p style="font-size: 0.85rem; color: var(--primary); margin-top: 1rem; background: rgba(59,130,246,0.1); padding: 0.5rem; border-radius: 4px;">This is an expanded version of a previous assessment. Your previous answers have been carried forward.</p>` : `<p style="font-size: 0.85rem; color: #64748b; margin-top: 1rem;">${data.items_to_render.length} questions</p>`}
        </div>
        <form id="inst-form" onsubmit="submitInstrument(event)">
    `;
    
    data.items_to_render.forEach(item => {
        const opts = data.response_option_sets[item.response_options_key];
        
        html += `<div class="form-group"><label>${item.text}</label>`;
        
        if (item.response_options_key.includes('time') || item.response_options_key.includes('number')) {
            html += `<input type="${item.response_options_key.includes('time') ? 'time' : 'number'}" id="${item.item_id}" required style="width:100%; padding: 0.75rem;">`;
        } else if (opts.length === 2 && (opts[0].value === 0 && opts[1].value === 1)) {
            // Binary toggle
            html += `
                <div class="toggle-container" id="toggle-group-${item.item_id}">
                    ${opts.map(o => `
                        <div class="toggle-btn" onclick="selectToggle('${item.item_id}', ${o.value}, this)">
                            ${o.label || o.text}
                        </div>
                    `).join('')}
                </div>
            `;
        } else if (opts.length <= 11) {
            // Stacked radio buttons for discrete Likert scales (forced to row)
            html += `
                <div id="toggle-group-${item.item_id}" class="stacked-options">
                    ${opts.map(o => `
                        <div class="stacked-btn" onclick="selectToggle('${item.item_id}', ${o.value}, this)">
                            ${o.label || o.text}
                        </div>
                    `).join('')}
                </div>
            `;
        } else {
            // Slider with persistent tick labels
            const min = opts[0].value;
            const max = opts[opts.length-1].value;
            const step = opts.length > 20 ? 1 : (max - min) / (opts.length - 1);
            
            html += `
                <input type="range" id="${item.item_id}" min="${min}" max="${max}" step="${step}" value="${min}" 
                       list="ticks-${item.item_id}" oninput="currentResponses['${item.item_id}'] = parseFloat(this.value)">
                <datalist id="ticks-${item.item_id}">
                    ${opts.map(o => `<option value="${o.value}"></option>`).join('')}
                </datalist>
                <div class="slider-labels-persistent">
                    ${opts.map(o => `<span>${o.label || o.text || o.value}</span>`).join('')}
                </div>
            `;
            // Default select min
            currentResponses[item.item_id] = min;
        }
        
        html += `</div>`;
    });
    
    html += `<button type="submit" style="width: 100%; padding: 1rem; font-size: 1.1rem;" ${!data.is_submittable ? 'disabled' : ''}>Submit Responses</button></form>`;
    
    window.currentOptionsData = data.response_option_sets;
    area.innerHTML = html;
}

function updateSliderLabel(itemId, valStr, optionsKey) {
    const val = parseFloat(valStr);
    currentResponses[itemId] = val;
    const opts = window.currentOptionsData[optionsKey];
    
    // Find closest option label if discrete
    let label = val;
    if (opts.length < 20) {
        const closest = opts.reduce((prev, curr) => Math.abs(curr.value - val) < Math.abs(prev.value - val) ? curr : prev);
        label = closest.label || closest.text;
    }
    document.getElementById(`val-${itemId}`).textContent = label;
}

function selectToggle(itemId, val, el) {
    currentResponses[itemId] = val;
    const container = document.getElementById(`toggle-group-${itemId}`);
    container.querySelectorAll('.toggle-btn, .stacked-btn').forEach(b => b.classList.remove('selected'));
    el.classList.add('selected');
}

async function submitInstrument(e) {
    e.preventDefault();
    if (!currentInstData) return;
    
    // Gather inputs for text/number/time
    currentInstData.items_to_render.forEach(item => {
        const el = document.getElementById(item.item_id);
        if (el && (el.type === 'number' || el.type === 'time')) {
            currentResponses[item.item_id] = el.type === 'number' ? parseFloat(el.value) : el.value; // simplistic
        }
    });
    
    // Validate binary toggles
    for (let item of currentInstData.items_to_render) {
        if (!(item.item_id in currentResponses) && !document.getElementById(item.item_id)) {
            alert(`Please answer all questions.`);
            return;
        }
    }
    
    try {
        const res = await api(`/sessions/${sessionState.session_id}/assessments/${currentInstData.instrument_id}/submit`, {
            method: 'POST',
            body: JSON.stringify({
                responses: currentResponses,
                parent_instance_id: currentInstData.parent_instance_id
            })
        });
        
        // Component 6: Store result
        if (!window.storedResults) window.storedResults = {};
        window.storedResults[currentInstData.instrument_id] = res;
        lastResultData = res;
        
        sessionState = await api(`/sessions/${sessionState.session_id}`);
        
        // Save bridge html for next instrument if exists
        if (res.ai_bridge) {
            const nextId = res.routing && res.routing.next_instrument_id;
            window.pendingBridgeHtml = `
                <div class="bridge-card">
                    <div class="bridge-label">AI Transition · ${currentInstData.instrument_id} → ${nextId || 'next'}</div>
                    ${res.ai_bridge.convergent_narrative ? `<p>${res.ai_bridge.convergent_narrative}</p>` : ''}
                    ${res.ai_bridge.divergent_narrative ? `<p style="color:var(--text-light);">${res.ai_bridge.divergent_narrative}</p>` : ''}
                    ${res.ai_bridge.composite_reflection ? `<p style="font-size:0.82rem;color:var(--text-light);">${res.ai_bridge.composite_reflection}</p>` : ''}
                </div>
            `;
        }
        
        renderState(true);
        if (sessionState.state === 'CORE_FLOW_IN_PROGRESS') {
            // Keep in core-flow but render result card directly
            const area = document.getElementById('content-area');
            const oldHtml = area.innerHTML;
            renderResultCard(res);
        } else {
            navigateTo('result');
        }
    } catch (e) { alert(e.message); }
}

// Component 6: Result Card Enhancements
function renderResultCard(submitRes) {
    if (!submitRes || !submitRes.score) return;
    
    let routingTxt = '';
    if (submitRes.routing.action === 'next_instrument') {
        routingTxt = "This has unlocked a more detailed assessment.";
    } else if (submitRes.routing.action === 'safety_pause') {
        routingTxt = "Safety protocol triggered.";
    } else if (submitRes.routing.unlock_planets && submitRes.routing.unlock_planets.length > 0) {
        routingTxt = `Based on this, we recommend exploring ${submitRes.routing.unlock_planets.join(', ')}.`;
    }
    
    let subscalesHtml = '';
    if (submitRes.score.subscales && Object.keys(submitRes.score.subscales).length > 0) {
        subscalesHtml = '<div class="subscales-list">';
        for (const [key, sub] of Object.entries(submitRes.score.subscales)) {
            const bandTxt = sub.band ? sub.band.replace(/_/g, ' ').toUpperCase() : '';
            subscalesHtml += `
                <div class="subscale-item">
                    <span class="subscale-name">${key.replace(/_/g, ' ').toUpperCase()}</span>
                    <div class="subscale-meta">
                        <span>${sub.score}</span>
                        ${bandTxt ? `<span style="background: rgba(59,130,246,0.1); padding: 0.2rem 0.5rem; border-radius: 4px;">${bandTxt}</span>` : ''}
                    </div>
                </div>
            `;
        }
        subscalesHtml += '</div>';
    }
    
    let buttonsHtml = '';
    if (sessionState.state === 'CORE_FLOW_IN_PROGRESS') {
        buttonsHtml = `<button onclick="renderState()" style="margin-top: 2rem; width: 100%;">Continue to next step</button>`;
    } else if (submitRes.routing.action === 'next_instrument') {
        buttonsHtml = `<button onclick="loadInstrument('${submitRes.routing.next_instrument_id}')" style="margin-top: 2rem; width: 100%;">Continue to ${submitRes.routing.next_instrument_id.toUpperCase()}</button>`;
    } else {
        buttonsHtml = `
            <div style="display: flex; gap: 1rem; margin-top: 2rem;">
                <button onclick="navigateTo('planet-detail', {planetId: currentPlanetId})" style="flex: 1;">Back to Planet</button>
                <button onclick="navigateTo('dashboard')" class="btn-outline" style="flex: 1;">Back to Dashboard</button>
            </div>
        `;
    }
    
    document.getElementById('content-area').innerHTML = `
        <div class="result-card" style="max-width: 600px; margin: 0 auto;">
            <h2>${currentInstData ? currentInstData.instrument_name : 'Result'}</h2>
            <div class="result-score">${submitRes.score.total_score}</div>
            <div class="result-band">${submitRes.score.band ? submitRes.score.band.replace(/_/g, ' ').toUpperCase() : ''}</div>
            ${routingTxt ? `<div class="result-routing" style="margin-bottom: 1.5rem;">${routingTxt}</div>` : ''}
            ${subscalesHtml}
            ${buttonsHtml}
        </div>
    `;
}

// Dev Tools & Debug AI Functions
function updateAIInvestigationPanel() {
    if (!sessionState) return;
    
    const sid = sessionState.session_id || sessionState.id;
    const el = id => document.getElementById(id);
    if (el('ai-inv-session')) el('ai-inv-session').textContent = sid ? sid.slice(0,8)+'...' : 'None';
    if (el('ai-inv-completed')) el('ai-inv-completed').textContent = (sessionState.completed || []).length;
    if (el('ai-inv-composites')) el('ai-inv-composites').textContent = (sessionState.composites || []).length;
    if (el('ai-inv-safety')) el('ai-inv-safety').textContent = (sessionState.safety_flags || []).length > 0 ? '⚠️' : 'None';

    const isReady = sessionState.completed && sessionState.completed.length >= 3;
    if (el('ai-inv-ready')) {
        el('ai-inv-ready').textContent = isReady ? 'Ready' : 'Insufficient Data';
        el('ai-inv-ready').style.color = isReady ? 'var(--success)' : 'var(--text-light)';
    }

    aiReadiness = sessionState.ai_readiness || null;
    
    // Auto-fill debug inputs
    const planetInput = document.getElementById('ai-debug-planet-id');
    if (planetInput && !planetInput.value && sessionState.planet_states && sessionState.planet_states.length > 0) {
        const activePlanet = sessionState.planet_states.find(p => p.completion_pct > 0) || sessionState.planet_states[0];
        if (activePlanet) planetInput.value = activePlanet.planet_id;
    }
    const prevInput = document.getElementById('ai-debug-prev-inst');
    const nextInput = document.getElementById('ai-debug-next-inst');
    if (prevInput && nextInput && sessionState.completed && sessionState.completed.length >= 2) {
        if (!prevInput.value) prevInput.value = sessionState.completed[sessionState.completed.length - 2].instrument_id;
        if (!nextInput.value) nextInput.value = sessionState.completed[sessionState.completed.length - 1].instrument_id;
    }
}

function updateReadinessDots() {
    if (!aiReadiness) return;

    const taskDotMap = {
        'mission_control': 'dot-mission-control',
        'full_formulation': 'dot-full-formulation',
        'red_thread': 'dot-red-thread',
    };

    for (const [task, dotId] of Object.entries(taskDotMap)) {
        const r = aiReadiness[task];
        if (!r) continue;
        const dot = document.getElementById(dotId);
        if (!dot) continue;
        dot.className = 'rdot';
        if (!r.ready) {
            dot.classList.add('rdot-not-ready');
            dot.title = r.reason || 'Not ready';
        } else {
            dot.classList.add('rdot-ready');
            dot.title = 'Ready';
        }
    }
}

function closeAIDebugOverlay() {
    document.getElementById('ai-debug-overlay').style.display = 'none';
}

function renderAIDebugOverlay(title, data) {
    document.getElementById('ai-debug-title').textContent = title;
    const outputEl = document.getElementById('ai-debug-output');
    
    if (typeof data === 'string') {
        outputEl.textContent = data;
    } else {
        outputEl.textContent = JSON.stringify(data, null, 2);
    }
    
    document.getElementById('ai-debug-overlay').style.display = 'flex';
}

async function fetchAIDebug(action) {
    if (!sessionState || !sessionState.session_id) {
        alert("Please create or load a session first.");
        return;
    }
    
    const sessionId = sessionState.session_id;
    let url = `/debug/sessions/${sessionId}/ai/${action}`;
    let options = { method: 'POST', body: JSON.stringify({}) };
    let title = "AI Debug Output";
    
    if (action === 'context') {
        options = { method: 'GET' };
        title = "Context Payload";
    } else if (action === 'prompt-preview') {
        const taskType = document.getElementById('ai-debug-task-type').value;
        const body = { task_type: taskType };
        
        if (taskType === 'planet_summary') {
            body.planet_id = document.getElementById('ai-debug-planet-id').value || 'venus';
        } else if (taskType === 'inter_instrument_narration') {
            body.prev_instrument_id = document.getElementById('ai-debug-prev-inst').value;
            body.next_instrument_id = document.getElementById('ai-debug-next-inst').value;
        }
        
        options.body = JSON.stringify(body);
        title = `Prompt Preview (${taskType})`;
    } else if (action === 'full-formulation') {
        title = "Full Formulation";
    } else if (action === 'mission-control') {
        title = "Mission Control";
    } else if (action === 'planet-summary') {
        const planetId = document.getElementById('ai-debug-planet-id').value;
        if (!planetId) { alert("Planet ID is required"); return; }
        options.body = JSON.stringify({ planet_id: planetId });
        title = `Planet Summary (${planetId})`;
    } else if (action === 'inter-instrument-narration') {
        const prevId = document.getElementById('ai-debug-prev-inst').value;
        const nextId = document.getElementById('ai-debug-next-inst').value;
        if (!prevId || !nextId) { alert("Both prev and next instrument IDs are required"); return; }
        options.body = JSON.stringify({ prev_instrument_id: prevId, next_instrument_id: nextId });
        title = `Narration (${prevId} -> ${nextId})`;
    }
    
    renderAIDebugOverlay(title, "Loading... This may take several seconds for LLM generation.");
    
    try {
        const res = await api(url, options);
        renderAIDebugOverlay(title, res);
    } catch (e) {
        renderAIDebugOverlay(`Error: ${title}`, e.message || "An error occurred");
    }
}

async function narrateTask(taskType, extraBody = {}, silent = false) {
    if (!sessionState) { alert('Load a session first.'); return; }
    const sid = sessionState.session_id || sessionState.id;
    const outId = 'out-' + taskType.replace('_', '-');
    const outEl = document.getElementById(outId);
    if (!outEl) return;

    if (!silent) {
        outEl.classList.add('open');
        outEl.innerHTML = '<div class="narrative-card"><p style="color:var(--text-light);">Generating…</p></div>';
    }

    try {
        const body = { task_type: taskType, ...extraBody };
        const res = await api(`/sessions/${sid}/ai/narrate`, {
            method: 'POST',
            body: JSON.stringify(body)
        });

        if (!res.ready) {
            outEl.innerHTML = `<div class="narrative-card">
                <h4>Not Ready</h4>
                <p style="color:var(--text-light);">${res.readiness_reason || 'Insufficient data'}</p>
            </div>`;
            return;
        }

        if (res.error) {
            outEl.innerHTML = `<div class="narrative-card"><h4>Error</h4><p style="color:var(--danger);">${res.error}</p></div>`;
            return;
        }

        outEl.innerHTML = renderNarrativeCard(taskType, res, extraBody);
    } catch(e) {
        outEl.innerHTML = `<div class="narrative-card"><h4>Error</h4><p style="color:var(--danger);">${e.message}</p></div>`;
    }
}

async function narratePlanet(planetId) {
    if (!sessionState) return;
    const outEl = document.getElementById(`out-planet-summary-${planetId}`);
    if (outEl) { outEl.classList.add('open'); outEl.innerHTML = '<div class="narrative-card"><p style="color:var(--text-light);">Generating…</p></div>'; }
    
    // Patch ID for narrateTask compatibility
    const oldId = document.getElementById('out-planet-summary');
    if (oldId) oldId.id = 'out-planet-summary-old';
    if (outEl) outEl.id = 'out-planet-summary';
    
    await narrateTask('planet_summary', { planet_id: planetId });
    
    if (outEl) outEl.id = `out-planet-summary-${planetId}`; // restore
}

function renderNarrativeCard(taskType, res, extraParams = {}) {
    const n = res.narrative;
    const meta = `<div class="meta">${res.cached ? '✓ cached' : '⚡ generated'} · ${res.model_used || '—'} · ${res.generation_time_ms ? res.generation_time_ms+'ms' : ''}  </div>`;

    if (taskType === 'mission_control') {
        if (n.safety_triggered) {
            return `<div class="narrative-card">
                <h4>⚠ Safety Protocol</h4>
                <p style="color:var(--danger);">${n.safety_protocol || ''}</p>
                ${meta}
            </div>`;
        }
        return `<div class="narrative-card">
            ${n.cognitive_reflection ? `<p><strong>Reflect:</strong> ${n.cognitive_reflection}</p>` : ''}
            ${n.behavioral_observation ? `<p><strong>Notice:</strong> ${n.behavioral_observation}</p>` : ''}
            ${n.integration_prompt ? `<p><strong>Connect:</strong> ${n.integration_prompt}</p>` : ''}
            ${meta}
        </div>`;
    }

    if (taskType === 'planet_summary') {
        return `<div class="narrative-card">
            ${n.data_sufficiency_met === false ? `<p style="color:var(--text-light);">Insufficient data.</p>` : ''}
            ${n.core_tendencies ? `<p><strong>Core:</strong> ${n.core_tendencies}</p>` : ''}
            ${n.environmental_interaction ? `<p><strong>In context:</strong> ${n.environmental_interaction}</p>` : ''}
            ${meta}
        </div>`;
    }

    if (taskType === 'red_thread') {
        return `<div class="narrative-card">
            ${n.primary_red_thread ? `<p>${n.primary_red_thread}</p>` : ''}
            ${n.evolution_summary ? `<p style="color:var(--text-light);">${n.evolution_summary}</p>` : ''}
            ${meta}
        </div>`;
    }

    if (taskType === 'full_formulation') {
        let sections = '';
        const themeOrder = [
            'theme_1_current_distress',
            'theme_2_maintaining_processes',
            'theme_3_relational_cognitive_patterns',
            'theme_4_values_and_friction',
            'theme_5_protective_resources',
            'so_what_layer'
        ];
        themeOrder.forEach(t => {
            const text = n[t];
            if (!text) return;
            const label = t.replace(/^theme_\d_/, '').replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
            sections += `<div style="margin-bottom:0.75rem;"><strong style="font-size:0.78rem;color:var(--uranus);">${label}</strong><p style="margin:0.3rem 0;">${text}</p></div>`;
        });
        if (n.safety_paragraph) {
            sections = `<div style="background:rgba(239,68,68,0.08);padding:0.75rem;border-radius:4px;margin-bottom:0.75rem;"><p style="color:var(--danger);margin:0;">${n.safety_paragraph}</p></div>` + sections;
        }
        return `<div class="narrative-card">${sections}${meta}</div>`;
    }

    return `<div class="narrative-card"><pre style="font-size:0.78rem;white-space:pre-wrap;">${JSON.stringify(n,null,2)}</pre>${meta}</div>`;
}

// init
// createQuickStartSession();
"""

parts[1] = new_script + "\n</script>\n</body>\n</html>\n"

with open('dev_shell.html', 'w') as f:
    f.write(parts[0] + '<script>\n' + parts[1])

