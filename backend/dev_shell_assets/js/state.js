// state.js
let sessionState = null;
let currentInstData = null;
let currentResponses = {};
let selectedIntakeCats = [];

let currentView = 'welcome';
let currentPlanetId = null;
let lastResultData = null;
let autoNarrate = localStorage.getItem('helix_auto_narrate') === 'true';
let aiReadiness = null;
window.lastCompletedPlanetCount = 0;

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

document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.getElementById('auto-narrate-toggle');
    if (toggle) toggle.checked = autoNarrate;
});

function toggleAutoNarrate(el) {
    autoNarrate = el.checked;
    localStorage.setItem('helix_auto_narrate', autoNarrate);
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
    
    if (sessionState.state === 'SAFETY_PAUSED') {
        document.getElementById('safety-overlay').style.display = 'flex';
    } else {
        document.getElementById('safety-overlay').style.display = 'none';
    }
    
    if (sessionState.fatigue_nudge) {
        document.getElementById('fatigue-overlay').style.display = 'flex';
    } else {
        document.getElementById('fatigue-overlay').style.display = 'none';
    }
    
    renderPlanetNav();
    updateAIInvestigationPanel();
    updateReadinessDots();
    
    if (!preserveView) {
        if (sessionState.state === 'CORE_FLOW_IN_PROGRESS') {
            currentView = 'core-flow';
        } else if (sessionState.state === 'EXPLORING' && currentView === 'welcome') {
            currentView = 'dashboard';
        }
    }
    
    navigateTo(currentView, { renderOnly: true });
}

function navigateTo(view, params = {}) {
    if (!sessionState) return;
    if (!params.renderOnly) currentView = view;
    
    const breadcrumb = document.getElementById('breadcrumb-area');
    const cfProgress = document.getElementById('core-flow-progress-area');
    
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
