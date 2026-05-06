// ui_forms.js

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
            if (!isCoreFlow) navigateTo('instrument', { instrumentName: getFriendlyName(data.instrument_id) });
            else renderInstrumentForm(data);
        }
    } catch (e) { alert(e.message); }
}

function renderInstrumentForm(data) {
    currentResponses = {};
    const area = document.getElementById('content-area');
    
    let html = '';
    
    if (sessionState.state === 'EXPLORING' && currentPlanetId) {
        html += `<button class="btn-outline" style="margin-bottom: 1.5rem; padding: 0.3rem 0.8rem; font-size: 0.85rem;" onclick="navigateTo('planet-detail', {planetId: currentPlanetId})">← Back to ${getPlanetName(currentPlanetId)}</button>`;
    }
    
    if (window.pendingBridgeHtml) {
        html += window.pendingBridgeHtml;
        window.pendingBridgeHtml = null;
    }
    
    html += `
        <div class="framing-block">
            <h2>${getFriendlyName(data.instrument_id)}</h2>
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
            const min = opts[0].value;
            const max = opts[opts.length-1].value;
            const step = opts.length > 20 ? 1 : (max - min) / (opts.length - 1);
            
            html += `
                <input type="range" id="${item.item_id}" min="${min}" max="${max}" step="${step}" value="${min}" 
                       list="ticks-${item.item_id}" oninput="updateSliderLabel('${item.item_id}', this.value, '${item.response_options_key}')">
                <datalist id="ticks-${item.item_id}">
                    ${opts.map(o => `<option value="${o.value}"></option>`).join('')}
                </datalist>
                <div class="slider-labels-persistent">
                    ${opts.map(o => `<span>${o.label || o.text || o.value}</span>`).join('')}
                </div>
                <div class="slider-value-display" id="val-${item.item_id}">-</div>
            `;
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
    
    let label = val;
    if (opts.length < 20) {
        const closest = opts.reduce((prev, curr) => Math.abs(curr.value - val) < Math.abs(prev.value - val) ? curr : prev);
        label = closest.label || closest.text;
    }
    const labelEl = document.getElementById(`val-${itemId}`);
    if (labelEl) labelEl.textContent = label;
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
    
    currentInstData.items_to_render.forEach(item => {
        const el = document.getElementById(item.item_id);
        if (el && (el.type === 'number' || el.type === 'time')) {
            currentResponses[item.item_id] = el.type === 'number' ? parseFloat(el.value) : el.value;
        }
    });
    
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
        
        if (!window.storedResults) window.storedResults = {};
        window.storedResults[currentInstData.instrument_id] = res;
        lastResultData = res;
        
        sessionState = await api(`/sessions/${sessionState.session_id}`);
        
        if (res.ai_bridge) {
            const nextId = res.routing && res.routing.next_instrument_id;
            window.pendingBridgeHtml = `
                <div class="bridge-card">
                    <div class="bridge-label">AI Transition · ${currentInstData.instrument_id.toUpperCase()} → ${nextId ? nextId.toUpperCase() : 'next'}</div>
                    ${res.ai_bridge.convergent_narrative ? `<p>${res.ai_bridge.convergent_narrative}</p>` : ''}
                    ${res.ai_bridge.divergent_narrative ? `<p style="color:var(--text-light);">${res.ai_bridge.divergent_narrative}</p>` : ''}
                    ${res.ai_bridge.composite_reflection ? `<p style="font-size:0.82rem;color:var(--text-light);">${res.ai_bridge.composite_reflection}</p>` : ''}
                </div>
            `;
        }
        
        renderState(true);
        if (sessionState.state === 'CORE_FLOW_IN_PROGRESS') {
            const area = document.getElementById('content-area');
            const oldHtml = area.innerHTML;
            renderResultCard(res);
        } else {
            navigateTo('result');
        }
    } catch (e) { alert(e.message); }
}

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
    const subscores = submitRes.score.subscale_scores || {};
    if (Object.keys(subscores).length > 0) {
        subscalesHtml = '<div class="subscales-list">';
        for (const [key, val] of Object.entries(subscores)) {
            const scoreVal = typeof val === 'object' ? val.score : val;
            const desc = (submitRes.score.subscale_band_descriptions || {})[key];
            subscalesHtml += `
                <div class="subscale-item" style="margin-bottom: 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem;">
                    <span class="subscale-name" style="font-weight: bold;">${key.replace(/_/g, ' ').toUpperCase()}</span>
                    <div class="subscale-meta" style="margin-bottom: 0.5rem;">
                        <span style="color: var(--primary); font-weight: bold;">${scoreVal}</span>
                    </div>
                    ${desc ? `<div class="subscale-desc" style="font-size: 0.85rem; color: var(--text-light); line-height: 1.4;">${desc}</div>` : ''}
                </div>
            `;
        }
        subscalesHtml += '</div>';
    }
    
    let buttonsHtml = '';
    if (sessionState.state === 'CORE_FLOW_IN_PROGRESS') {
        buttonsHtml = `<button onclick="renderState()" style="margin-top: 2rem; width: 100%;">Continue to next step</button>`;
    } else if (submitRes.routing.action === 'next_instrument') {
        buttonsHtml = `<button onclick="loadInstrument('${submitRes.routing.next_instrument_id}')" style="margin-top: 2rem; width: 100%;">Continue to ${getFriendlyName(submitRes.routing.next_instrument_id)}</button>`;
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
            <h2>${currentInstData ? getFriendlyName(currentInstData.instrument_id) : 'Result'}</h2>
            <div class="result-score">${submitRes.score.total_score}</div>
            <div class="result-band">${submitRes.score.band ? submitRes.score.band.replace(/_/g, ' ').toUpperCase() : ''}</div>
            ${submitRes.score.band_description ? `<div class="result-band-desc" style="margin-top: 1rem; margin-bottom: 1.5rem; color: var(--text-light); font-size: 0.95rem; line-height: 1.5;">${submitRes.score.band_description}</div>` : ''}
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
    
    const oldId = document.getElementById('out-planet-summary');
    if (oldId) oldId.id = 'out-planet-summary-old';
    if (outEl) outEl.id = 'out-planet-summary';
    
    await narrateTask('planet_summary', { planet_id: planetId });
    
    if (outEl) outEl.id = `out-planet-summary-${planetId}`;
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
            const label = t.replace(/^theme_\\d_/, '').replace(/_/g,' ').replace(/\\b\\w/g,c=>c.toUpperCase());
            sections += `<div style="margin-bottom:0.75rem;"><strong style="font-size:0.78rem;color:var(--uranus);">${label}</strong><p style="margin:0.3rem 0;">${text}</p></div>`;
        });
        if (n.safety_paragraph) {
            sections = `<div style="background:rgba(239,68,68,0.08);padding:0.75rem;border-radius:4px;margin-bottom:0.75rem;"><p style="color:var(--danger);margin:0;">${n.safety_paragraph}</p></div>` + sections;
        }
        return `<div class="narrative-card">${sections}${meta}</div>`;
    }

    return `<div class="narrative-card"><pre style="font-size:0.78rem;white-space:pre-wrap;">${JSON.stringify(n,null,2)}</pre>${meta}</div>`;
}
