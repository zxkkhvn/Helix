// ui_core.js

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
                        ${getFriendlyName(inst)}
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

function renderCoreFlowProgress(currentStepKey) {
    const area = document.getElementById('core-flow-progress-area');
    area.style.display = 'block';
    
    const steps = [
        {key: 'intake', label: 'Welcome'},
        {key: 'pbat', label: 'How you\'ve been'},
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
    if (!autoNarrate) html += '<button class="btn-outline" style="padding:0.2rem 0.5rem; font-size:0.75rem;" onclick="narrateTask(\'mission_control\')">Generate</button>';
    html += '</div><div id="out-mission-control" class="narrate-output"></div></div>';
    
    html += '<div style="flex: 1;"><div style="display:flex; justify-content:space-between; align-items:center;"><h4>Red Thread</h4>';
    if (!autoNarrate) html += '<button class="btn-outline" style="padding:0.2rem 0.5rem; font-size:0.75rem;" onclick="narrateTask(\'red_thread\')">Generate</button>';
    html += '</div><div id="out-red-thread" class="narrate-output"></div></div>';
    html += '</div>';
    
    html += '<div style="margin-top: 2rem;"><div style="display:flex; justify-content:space-between; align-items:center;"><h4>Full Formulation</h4>';
    if (!autoNarrate) html += '<button class="btn-outline" style="padding:0.2rem 0.5rem; font-size:0.75rem;" onclick="narrateTask(\'full_formulation\')">Generate</button>';
    html += '</div><div id="out-full-formulation" class="narrate-output"></div></div>';
    
    html += '</div>';
    area.innerHTML = html;
    
    if (autoNarrate && aiReadiness) {
        (async () => {
            const tasks = ['mission_control', 'red_thread', 'full_formulation'];
            for (const task of tasks) {
                if (aiReadiness[task] && aiReadiness[task].ready) {
                    const el = document.getElementById('out-' + task.replace('_', '-'));
                    if (el) el.classList.add('open');
                    await narrateTask(task, {}, true);
                    await new Promise(resolve => setTimeout(resolve, 2000));
                }
            }
        })();
    }
}

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
                    <div style="font-weight: 600; font-size: 1.1rem; margin-bottom: 0.5rem;">${getFriendlyName(inst)}</div>
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
            const apiRes = sessionState.completed.find(c => c.instrument_id === inst);
            const pastRes = window.storedResults && window.storedResults[inst];
            
            let scoreVal = null;
            let bandTxt = null;
            let bandDesc = null;
            
            if (apiRes && apiRes.total_score != null) {
                scoreVal = apiRes.total_score;
                bandTxt = apiRes.band;
                bandDesc = apiRes.band_description;
            } else if (pastRes && pastRes.score) {
                scoreVal = pastRes.score.total_score;
                bandTxt = pastRes.score.band;
                bandDesc = pastRes.score.band_description;
            }

            html += `
                <div class="planet-card" style="margin-bottom: 1rem; background: rgba(255,255,255,0.02); opacity: 0.8;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: ${bandDesc ? '1rem' : '0'};">
                        <div style="font-weight: 600;">${getFriendlyName(inst)}</div>
                        ${scoreVal != null ? `<div style="color: var(--primary); font-weight: bold;">Score: ${scoreVal} ${bandTxt ? `<span style="font-size: 0.8rem; margin-left: 0.5rem; color: var(--text);">${bandTxt.replace(/_/g, ' ').toUpperCase()}</span>` : ''}</div>` : '<div style="color: var(--success);">✓</div>'}
                    </div>
                    ${bandDesc ? `<div style="font-size: 0.85rem; color: var(--text-light); border-top: 1px solid var(--border); padding-top: 0.75rem; line-height: 1.4;">${bandDesc}</div>` : ''}
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
            const oldId = document.getElementById('out-planet-summary');
            if (oldId) oldId.id = 'out-planet-summary-old';
            document.getElementById(`out-planet-summary-${planetId}`).id = 'out-planet-summary';
            narratePlanet(planetId);
        }
    }
}
