const $ = (selector) => document.querySelector(selector);
const shell = $('#app-shell');
const chatScroll = $('#chat-scroll');
const chatStream = $('#chat-stream');

const defaultTraceId = 'development-dev_task41_seed42_risk';
const storyOrder = [
  defaultTraceId, 'fault-risk', 'fault-none',
  'held-out-heldout_task17_seed42_risk', 'held-out-heldout_task42_seed42_risk',
];

const policyLabels = {
  none: 'No checks', 'final-only': 'Final-only', exhaustive: 'Check every write',
  random: 'Random checks', risk: 'Risk-based checks',
};

const toolNames = {
  find_user_id_by_name_zip: 'Find customer',
  get_user_details: 'Read customer record',
  get_order_details: 'Read order details',
  get_product_details: 'Read product details',
  list_all_product_types: 'List product types',
  modify_pending_order_address: 'Change order address',
  modify_user_address: 'Change saved address',
  modify_pending_order_items: 'Change order items',
  modify_pending_order_payment: 'Change payment method',
  cancel_pending_order: 'Cancel order',
  return_delivered_order_items: 'Return items',
  exchange_delivered_order_items: 'Exchange items',
};

const state = {
  catalog: [], summary: null, selectedId: null, trace: null, timeline: [],
  visibleCount: 0, selectedStep: null, playing: false, timer: null, view: 'conversation',
};

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);
}

function titleCase(value) {
  return String(value || '').split('-').map((part) => part[0]?.toUpperCase() + part.slice(1)).join(' ');
}

function humanTool(name) {
  return toolNames[name] || String(name || 'Tool call').replaceAll('_', ' ').replace(/^./, (letter) => letter.toUpperCase());
}

function safeJson(value) {
  try { return JSON.stringify(value, null, 2); } catch { return String(value); }
}

function parseResponse(value) {
  if (typeof value !== 'string') return value;
  try { return JSON.parse(value); } catch { return value; }
}

function streetOf(data) {
  return data?.address?.address1 || null;
}

function latestVisibleStreet(timeline, throughIndex) {
  const pattern = /\b\d{1,6}\s+[A-Za-z][A-Za-z .'-]{0,50}?\s+(?:Street|St|Road|Rd|Avenue|Ave|Drive|Dr|Lane|Ln|Boulevard|Blvd|Court|Ct|Way)\b/gi;
  let street = null;
  for (let index = 0; index <= throughIndex; index++) {
    const entry = timeline[index];
    if (entry?.type !== 'message' || entry.role !== 'user') continue;
    const matches = [...entry.content.matchAll(pattern)];
    if (matches.length) street = matches[matches.length - 1][0];
  }
  return street;
}

function buildTimeline(trace) {
  const timeline = [];
  const pending = new Map();
  let eventIndex = 0;
  for (const message of trace.messages || []) {
    if (message.role === 'assistant') {
      if (message.content) timeline.push({ type: 'message', role: 'assistant', content: message.content, turn: message.turn_idx });
      for (const call of message.tool_calls || []) {
        const event = trace.events?.[eventIndex++];
        pending.set(call.id, { call, event, eventIndex: eventIndex - 1 });
      }
    } else if (message.role === 'user') {
      if (message.content && message.content !== '###STOP###') {
        timeline.push({ type: 'message', role: 'user', content: message.content, turn: message.turn_idx });
      }
    } else if (message.role === 'tool') {
      const linked = pending.get(message.id);
      if (linked) {
        timeline.push({ type: 'tool', ...linked, response: message.content, turn: message.turn_idx });
        pending.delete(message.id);
      }
    }
  }
  if (trace.policy === 'final-only') {
    for (let index = 0; index < (trace.events || []).length; index++) {
      if (trace.events[index].verification) timeline.push({ type: 'audit', event: trace.events[index], eventIndex: index });
    }
  }
  return timeline;
}

function statusOf(entry) {
  const event = entry.event || {};
  const verdict = event.verification?.verdict;
  if (event.executed === false || event.rejected_after_verification_fail) return { text: 'REJECTED', kind: 'rejected' };
  if (entry.type === 'audit') return { text: verdict || 'CHECK', kind: verdict?.toLowerCase() || 'read' };
  if (event.mutating && state.trace?.policy === 'final-only') return { text: 'WRITE', kind: 'write' };
  if (verdict) return { text: verdict, kind: verdict.toLowerCase() };
  return event.mutating ? { text: 'WRITE', kind: 'write' } : { text: 'READ', kind: 'read' };
}

function toolSummary(entry) {
  const event = entry.event || {};
  if (entry.type === 'audit') return 'Post-run verification. This check did not affect the agent.';
  if (event.executed === false || event.rejected_after_verification_fail) return 'Stopped after an earlier failed outcome check.';
  const reported = parseResponse(event.response ?? entry.response);
  const reportedStreet = streetOf(reported);
  const observedStreet = streetOf(event.verification?.evidence);
  if (event.verification?.verdict === 'FAIL' && observedStreet) return `Independent readback found ${observedStreet}.`;
  if (event.verification?.verdict === 'PASS' && observedStreet) return `Readback confirmed ${observedStreet}.`;
  if (event.verification?.verdict === 'INCONCLUSIVE') return 'The available readback could not establish the requested outcome.';
  if (reportedStreet) return `Tool response reported ${reportedStreet}.`;
  if (typeof reported === 'string') return reported.length > 85 ? `${reported.slice(0, 82)}…` : reported;
  if (reported?.status) return `Tool response reported status: ${reported.status}.`;
  if (event.mutating) return 'State-changing tool call completed.';
  return 'Read-only tool call completed.';
}

function entryHtml(entry, index) {
  if (entry.type === 'message') {
    const role = entry.role === 'user' ? 'user' : 'assistant';
    const speaker = role === 'user' ? 'Customer' : 'Agent';
    const avatar = role === 'user' ? 'C' : 'A';
    return `<div class="stream-entry message-row ${role}"><div class="avatar" aria-hidden="true">${avatar}</div><div class="message-body"><div class="speaker">${speaker}</div><div class="bubble">${escapeHtml(entry.content)}</div></div></div>`;
  }
  const event = entry.event || {};
  const status = statusOf(entry);
  const name = entry.type === 'audit' ? `Final check · ${humanTool(event.tool)}` : humanTool(event.tool || entry.call?.name);
  const symbol = entry.type === 'audit' ? '✓' : event.mutating ? '↗' : '⌕';
  const active = state.selectedStep === index ? ' selected' : '';
  const type = event.mutating ? 'write' : 'read';
  const checkpoint = event.verification
    ? `<span class="checkpoint-note"><span class="checkpoint-pip"></span>${entry.type === 'audit' ? 'Post-run audit' : 'Independent outcome check'} · ${escapeHtml(event.verification.verdict)}</span>`
    : '';
  return `<button type="button" class="stream-entry tool-step ${type} ${status.kind}${active}" data-step="${index}" aria-label="Inspect ${escapeHtml(name)}"><span class="tool-symbol" aria-hidden="true">${symbol}</span><span class="tool-content"><span class="tool-topline"><span class="tool-name">${escapeHtml(name)}</span><span class="mini-badge ${status.kind}">${escapeHtml(status.text)}</span></span><span class="tool-summary">${escapeHtml(toolSummary(entry))}</span>${checkpoint}</span><span class="arrow" aria-hidden="true">›</span></button>`;
}

function bindStep(button) {
  button.addEventListener('click', () => selectStep(Number(button.dataset.step)));
}

function renderChat({ scroll = false } = {}) {
  const entries = state.timeline.slice(0, state.visibleCount);
  chatStream.innerHTML = entries.map(entryHtml).join('') || '<div class="inspector-empty"><h3>Starting replay</h3><p>The saved customer conversation will appear here.</p></div>';
  chatStream.querySelectorAll('[data-step]').forEach(bindStep);
  $('#playback-cursor').hidden = !state.playing;
  if (scroll) chatScroll.scrollTop = chatScroll.scrollHeight;
  updatePlaybackControls();
}

function selectStep(index) {
  state.selectedStep = index;
  chatStream.querySelectorAll('.tool-step').forEach((button) => button.classList.toggle('selected', Number(button.dataset.step) === index));
  renderInspector();
  if (window.innerWidth < 1181) shell.classList.add('inspector-open');
  else shell.classList.remove('inspector-hidden');
}

function metric(label, value) {
  return `<div class="kv"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value ?? '—')}</strong></div>`;
}

function jsonDetails(label, value) {
  return `<details><summary class="json-toggle">${escapeHtml(label)} ↓</summary><pre class="json-block">${escapeHtml(safeJson(value))}</pre></details>`;
}

function stateSummary(data) {
  if (!data || typeof data !== 'object') return '<p class="muted">No readback available.</p>';
  const address = streetOf(data);
  const items = Array.isArray(data.items) ? data.items.length : null;
  const rows = [
    address ? metric('Street', address) : '',
    data.status ? metric('Order status', data.status) : '',
    items !== null ? metric('Items', String(items)) : '',
    data.order_id ? metric('Order', data.order_id) : '',
  ].filter(Boolean).join('');
  return rows || '<p class="muted">Readback returned a record.</p>';
}

function renderInspector() {
  const trace = state.trace;
  const entry = state.timeline[state.selectedStep];
  if (!trace || !entry || !['tool', 'audit'].includes(entry.type)) {
    $('#inspector-title').textContent = 'Run details';
    const checks = (trace?.events || []).filter((event) => event.verification).length;
    const reads = (trace?.events || []).reduce((sum, event) => sum + (event.verification?.read_calls || 0), 0);
    $('#inspector-content').innerHTML = `<div class="inspector-empty"><h3>Select a tool step</h3><p>Click a tool card in the conversation to see its arguments, response, risk score, and readback evidence.</p></div><div class="inspector-section" style="margin-top:20px"><h3>RUN SETTINGS</h3>${metric('Benchmark task', trace?.task_id || '—')}${metric('Seed', trace?.seed ?? '—')}${metric('Tool calls', trace?.events?.length || 0)}${metric('Checks', checks)}${metric('Readbacks', reads)}${metric('Model', trace?.model || '—')}${metric('Elapsed', trace?.elapsed_seconds ? `${trace.elapsed_seconds.toFixed(1)} s` : '—')}</div>`;
    return;
  }
  const event = entry.event || {};
  const check = event.verification;
  const status = statusOf(entry);
  const stepLabel = entry.type === 'audit' ? 'POST-RUN CHECK' : `TOOL STEP ${entry.eventIndex + 1}`;
  $('#inspector-title').textContent = humanTool(event.tool || entry.call?.name);
  const risk = event.risk;
  const riskRows = risk && typeof risk === 'object' ? [
    ['Impact', risk.impact], ['Downstream dependence', risk.downstream],
    ['Irreversibility', risk.irreversibility], ['Uncertainty', risk.uncertainty],
  ].map(([label, value]) => `<div class="risk-row"><div class="risk-label"><span>${label}</span><span>${Number(value).toFixed(2)}</span></div><div class="risk-track"><span style="width:${Math.max(0, Math.min(100, Number(value) * 100))}%"></span></div></div>`).join('') : '';
  const reported = parseResponse(event.response ?? entry.response);
  const toolStreet = streetOf(reported);
  const observedStreet = streetOf(check?.evidence);
  const customerStreet = latestVisibleStreet(state.timeline, state.selectedStep);
  const comparison = check && (toolStreet || observedStreet) ? `<div class="inspector-section"><h3>ADDRESS EVIDENCE</h3>${customerStreet ? metric('Customer stated', customerStreet) : ''}${toolStreet ? metric('Tool reported', toolStreet) : ''}${observedStreet ? metric('Readback found', observedStreet) : ''}</div>` : '';
  const verdict = check ? `<div class="inspector-section"><h3>${entry.type === 'audit' ? 'FINAL-ONLY AUDIT' : 'OUTCOME CHECK'}</h3><div class="inspector-highlight ${escapeHtml(check.verdict?.toLowerCase() || '')}"><span class="mini-badge ${escapeHtml(check.verdict?.toLowerCase() || 'read')}">${escapeHtml(check.verdict || 'CHECK')}</span><p>${escapeHtml(check.reason || 'No reason recorded.')}</p></div>${metric('Read-tool calls', check.read_calls ?? 0)}${entry.type === 'audit' ? '<p class="muted">This check ran after the conversation. The agent did not receive its verdict.</p>' : ''}</div>` : `<div class="inspector-section"><h3>OUTCOME CHECK</h3><p class="muted">${event.mutating ? 'No checkpoint selected for this write.' : 'This tool call only read state.'}</p></div>`;
  const riskSection = riskRows ? `<div class="inspector-section"><h3>CHECKPOINT DECISION</h3>${metric('Selected', event.checkpoint ? 'Yes' : 'No')}${metric('Risk score', Number(risk.score).toFixed(3))}${metric('Threshold', Number(trace.threshold ?? .55).toFixed(2))}${riskRows}</div>` : '';
  const intervention = event.correction_opportunity || event.rejected_after_verification_fail || event.escalated
    ? `<div class="inspector-section"><h3>INTERVENTION</h3>${event.correction_opportunity ? '<p>The agent received one opportunity to correct the failed write.</p>' : ''}${event.rejected_after_verification_fail ? '<p>This bundled tool call was rejected after the failed check.</p>' : ''}${event.escalated ? '<p>The controller stopped or escalated this action.</p>' : ''}</div>` : '';
  $('#inspector-content').innerHTML = `<div class="inspector-section"><span class="inspector-eyebrow">${stepLabel}</span><p><span class="mini-badge ${status.kind}">${escapeHtml(status.text)}</span></p>${metric('Tool', event.tool || entry.call?.name || '—')}${metric('Type', event.mutating ? 'State-changing write' : 'Read-only action')}${metric('Tool-boundary time', event.elapsed_seconds != null ? `${(Number(event.elapsed_seconds) * 1000).toFixed(0)} ms` : '—')}</div>${verdict}${comparison}${intervention}${riskSection}<div class="inspector-section"><h3>TOOL INPUT AND OUTPUT</h3>${jsonDetails('Arguments', event.arguments || entry.call?.arguments || {})}${jsonDetails('Tool response', reported)}</div>${check ? `<div class="inspector-section"><h3>READBACK RECORDS</h3>${event.pre_state ? jsonDetails('Before the write', event.pre_state) : ''}${jsonDetails('After the write', check.evidence)}</div>` : ''}`;
}

function traceLabel(item) {
  return item.title || `Retail task ${item.task_id}`;
}

function traceSubtitle(item) {
  if (item.collection === 'controlled fault') return item.fault_recovered ? 'Controlled test · address repaired' : 'Controlled test · wrong address remained';
  return `Benchmark run · ${item.reward === 1 ? 'task completed' : 'task incomplete'}`;
}

function traceCard(item) {
  const dot = item.collection === 'controlled fault' ? 'fault' : item.reward === 1 ? 'success' : '';
  return `<button type="button" class="trace-card ${item.id === state.selectedId ? 'active' : ''}" data-trace="${escapeHtml(item.id)}"><span class="trace-title"><span class="trace-icon ${dot}" aria-hidden="true"></span>${escapeHtml(traceLabel(item))}</span><span class="trace-subtitle">${escapeHtml(traceSubtitle(item))}</span></button>`;
}

function bindTraceCards() {
  document.querySelectorAll('[data-trace]').forEach((button) => button.addEventListener('click', () => loadTrace(button.dataset.trace)));
}

function renderLibrary() {
  $('#library-total').textContent = String(state.catalog.length);
  const byId = new Map(state.catalog.map((item) => [item.id, item]));
  const items = storyOrder.map((id) => byId.get(id)).filter(Boolean);
  $('#trace-list').innerHTML = `<div class="section-heading"><span>Five guided examples</span></div>${items.map(traceCard).join('')}`;
  bindTraceCards();
}

function runTitle(item) {
  return traceLabel(item);
}

function renderHeader() {
  const item = state.catalog.find((entry) => entry.id === state.selectedId);
  if (!item) return;
  const fault = item.collection === 'controlled fault';
  $('#run-overline').textContent = fault ? 'CONTROLLED ERROR TEST' : 'RETAIL BENCHMARK RUN';
  $('#run-title').textContent = runTitle(item);
  $('#run-description').textContent = item.intro || '';
  $('#story-goal').textContent = item.customer_goal || '';
  $('#story-happened').textContent = item.what_happened || '';
  $('#story-insight').textContent = item.why_it_matters || '';
  $('#story-box').open = true;
  $('#run-result').textContent = fault ? (item.fault_recovered ? 'ADDRESS REPAIRED' : 'ERROR REMAINED') : (item.reward === 1 ? 'TASK COMPLETED' : 'TASK INCOMPLETE');
  $('#run-result').className = `result-badge ${fault ? 'controlled' : item.reward === 1 ? 'success' : 'failure'}`;
  const facts = [
    ['Checking strategy', policyLabels[item.policy] || titleCase(item.policy)],
    ['Checks made', item.check_count], ['Extra read calls', item.readback_calls],
  ];
  if (fault && item.fault_final_street) facts.push(['Final saved street', item.fault_final_street]);
  $('#run-facts').innerHTML = facts.map(([key, value]) => `<span class="run-fact"><span>${escapeHtml(key)}</span><strong>${escapeHtml(value)}</strong></span>`).join('');
  $('#fault-notice').hidden = !fault;
}

function updatePlaybackControls() {
  const count = state.timeline.length;
  const visible = Math.min(state.visibleCount, count);
  $('#progress-fill').style.width = `${count ? visible / count * 100 : 0}%`;
  $('#playback-detail').textContent = state.playing ? `Step ${visible} of ${count} · ${Number($('#speed-slider').value).toFixed(2).replace(/\.00$/, '').replace(/0$/, '')}×` : visible < count ? `Paused at step ${visible} of ${count}` : `${count} recorded steps · full trace shown`;
  $('#play-label').textContent = state.playing ? 'Pause replay' : visible < count ? 'Continue replay' : 'Replay simulation';
  $('#play-icon').textContent = state.playing ? 'Ⅱ' : '▶';
}

function stopPlayback() {
  clearTimeout(state.timer);
  state.timer = null;
  state.playing = false;
  updatePlaybackControls();
  $('#playback-cursor').hidden = true;
}

function scheduleNext() {
  if (!state.playing) return;
  if (state.visibleCount >= state.timeline.length) {
    stopPlayback();
    return;
  }
  const next = state.timeline[state.visibleCount];
  let delay;
  if (next.type === 'message') {
    const words = next.content.trim().split(/\s+/).length;
    delay = next.role === 'assistant'
      ? Math.min(6500, 1700 + words * 45)
      : Math.min(4800, 1200 + words * 35);
    $('#playback-activity').textContent = next.role === 'assistant' ? 'Agent is preparing a response…' : 'Customer is replying…';
  } else {
    delay = next.event?.verification ? 3000 : next.event?.mutating ? 2400 : 1700;
    $('#playback-activity').textContent = next.event?.verification
      ? 'Checking the resulting state…' : `Running ${humanTool(next.event?.tool || next.call?.name).toLowerCase()}…`;
  }
  delay /= Number($('#speed-slider').value) || 1;
  state.timer = setTimeout(() => {
    if (state.visibleCount === 0) chatStream.innerHTML = '';
    const index = state.visibleCount;
    state.visibleCount += 1;
    chatStream.insertAdjacentHTML('beforeend', entryHtml(next, index));
    const inserted = chatStream.lastElementChild;
    if (inserted?.matches('[data-step]')) bindStep(inserted);
    chatScroll.scrollTop = chatScroll.scrollHeight;
    updatePlaybackControls();
    scheduleNext();
  }, delay);
}

function togglePlayback() {
  if (state.playing) { stopPlayback(); return; }
  if (state.visibleCount >= state.timeline.length) {
    state.visibleCount = 0;
    state.selectedStep = null;
    renderInspector();
    chatScroll.scrollTop = 0;
  }
  state.playing = true;
  renderChat();
  scheduleNext();
}

function showAll() {
  stopPlayback();
  state.visibleCount = state.timeline.length;
  renderChat();
  chatScroll.scrollTop = 0;
}

function jumpToCheckpoint() {
  stopPlayback();
  state.visibleCount = state.timeline.length;
  renderChat();
  const start = state.selectedStep === null ? 0 : state.selectedStep + 1;
  let index = state.timeline.findIndex((entry, position) => position >= start && entry.event?.verification);
  if (index < 0) index = state.timeline.findIndex((entry) => entry.event?.verification);
  if (index < 0) { toast('This run has no verification checkpoints.'); return; }
  selectStep(index);
  chatStream.querySelector(`[data-step="${index}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
}

function showView(name) {
  if (name !== 'conversation') stopPlayback();
  state.view = name;
  $('#home-view').hidden = name !== 'home';
  $('#conversation-view').hidden = name !== 'conversation';
  $('#results-view').hidden = name !== 'results';
  $('#home-tab').classList.toggle('active', name === 'home');
  $('#conversation-tab').classList.toggle('active', name === 'conversation');
  $('#results-tab').classList.toggle('active', name === 'results');
  shell.classList.toggle('results-mode', name === 'results');
  if (name !== 'conversation') shell.classList.add('inspector-hidden');
  shell.classList.remove('inspector-open');
  $('#inspector-button').hidden = name !== 'conversation';
  document.title = `${name === 'home' ? 'Home' : name === 'results' ? 'Results' : 'Conversation'} — Outcome`;
  const url = new URL(location.href);
  if (name === 'conversation' && state.selectedId) url.searchParams.set('trace', state.selectedId);
  else url.searchParams.delete('trace');
  history.replaceState(null, '', url);
}

async function loadTrace(identifier) {
  const item = state.catalog.find((entry) => entry.id === identifier);
  if (!item) return;
  stopPlayback();
  try {
    const response = await fetch(`/data/traces/${encodeURIComponent(identifier)}.json`);
    if (!response.ok) throw new Error(`Trace unavailable (${response.status})`);
    state.trace = await response.json();
    state.selectedId = identifier;
    state.timeline = buildTimeline(state.trace);
    state.visibleCount = state.timeline.length;
    state.selectedStep = null;
    renderLibrary();
    renderHeader();
    renderChat();
    renderInspector();
    showView('conversation');
    shell.classList.add('inspector-hidden');
    chatScroll.scrollTop = 0;
    shell.classList.remove('sidebar-open');
    $('#mobile-scrim').hidden = true;
  } catch (error) {
    toast(`Could not load trace: ${error.message}`);
  }
}

function renderResults() {
  const summary = state.summary;
  const rows = summary.heldout_seed42;
  const byPolicy = Object.fromEntries(rows.map((row) => [row.policy, row]));
  $('#results-cards').innerHTML = [
    ['Risk success', `${byPolicy.risk.successes}/${byPolicy.risk.trials}`, `${byPolicy.risk.readbacks} readbacks at seed 42`],
    ['No-check success', `${byPolicy.none.successes}/${byPolicy.none.trials}`, '0 readbacks at seed 42'],
    ['Readback reduction', `${Math.round((1 - byPolicy.risk.readbacks / byPolicy.exhaustive.readbacks) * 100)}%`, `${byPolicy.risk.readbacks} risk versus ${byPolicy.exhaustive.readbacks} exhaustive`],
  ].map(([label, value, description]) => `<div class="result-card"><div class="card-label">${escapeHtml(label)}</div><strong>${escapeHtml(value)}</strong><span>${escapeHtml(description)}</span></div>`).join('');
  const maxReadbacks = Math.max(...rows.map((row) => row.readbacks), 1);
  $('#policy-rows').innerHTML = `<table class="policy-table"><thead><tr><th>Policy</th><th>Official success</th><th>Checks</th><th class="bar-cell">Readback calls</th><th>Inconclusive</th></tr></thead><tbody>${rows.map((row) => `<tr><td>${escapeHtml(titleCase(row.policy))}</td><td>${row.successes}/${row.trials}</td><td>${row.checks}</td><td class="bar-cell"><span class="tiny-bar" style="width:${Math.max(row.readbacks ? 3 : 0, row.readbacks / maxReadbacks * 95)}px"></span> &nbsp;${row.readbacks}</td><td>${row.inconclusive}</td></tr>`).join('')}</tbody></table>`;
  const risk = summary.repeated_heldout.risk;
  const none = summary.repeated_heldout.none;
  const paired = summary.paired_outcomes;
  $('#repeat-panel').innerHTML = `<h2>Repeated held-out trials</h2><p>Risk and no-check policies on five test tasks across seeds 42, 43, and 44.</p><div class="repeat-numbers"><div><strong>${risk.successes}/${risk.trials}</strong><span>risk success · ${risk.readbacks} reads</span></div><div><strong>${none.successes}/${none.trials}</strong><span>no-check success · ${none.readbacks} reads</span></div></div><p class="muted">Risk won ${paired.risk} paired trials. No checks won ${paired.none}. ${paired.ties} tied. No natural verifier FAIL occurred.</p>`;
}

function toast(message) {
  const element = $('#toast');
  element.textContent = message;
  element.hidden = false;
  setTimeout(() => { element.hidden = true; }, 4500);
}

function setupControls() {
  $('#home-tab').addEventListener('click', () => showView('home'));
  $('#home-browse-button').addEventListener('click', () => {
    const folder = $('.trace-folder');
    folder.open = true;
    if (window.innerWidth <= 760) {
      shell.classList.add('sidebar-open');
      $('#mobile-scrim').hidden = false;
    } else {
      folder.scrollIntoView({ block: 'start', behavior: 'smooth' });
      folder.querySelector('summary').focus();
    }
  });
  $('#conversation-tab').addEventListener('click', () => {
    if (state.trace) showView('conversation');
    else loadTrace(defaultTraceId);
  });
  $('#results-tab').addEventListener('click', () => showView('results'));
  $('#play-button').addEventListener('click', togglePlayback);
  $('#checkpoint-button').addEventListener('click', jumpToCheckpoint);
  $('#show-all-button').addEventListener('click', showAll);
  $('#speed-slider').addEventListener('input', (event) => {
    const value = Number(event.target.value);
    $('#speed-value').textContent = `${Number.isInteger(value) ? value : value.toFixed(2).replace(/0$/, '')}×`;
    if (state.playing) {
      clearTimeout(state.timer);
      scheduleNext();
    }
    updatePlaybackControls();
  });
  $('#inspector-button').addEventListener('click', () => {
    if (window.innerWidth < 1181) shell.classList.toggle('inspector-open');
    else shell.classList.toggle('inspector-hidden');
  });
  $('#inspector-close').addEventListener('click', () => {
    if (window.innerWidth < 1181) shell.classList.remove('inspector-open');
    else shell.classList.add('inspector-hidden');
  });
  $('#menu-button').addEventListener('click', () => {
    shell.classList.add('sidebar-open');
    $('#mobile-scrim').hidden = false;
  });
  $('#mobile-scrim').addEventListener('click', () => {
    shell.classList.remove('sidebar-open');
    shell.classList.remove('inspector-open');
    $('#mobile-scrim').hidden = true;
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      shell.classList.remove('sidebar-open', 'inspector-open');
      $('#mobile-scrim').hidden = true;
    }
  });
}

async function start() {
  setupControls();
  try {
    const [catalogResponse, summaryResponse] = await Promise.all([
      fetch('/data/catalog.json'), fetch('/data/summary.json'),
    ]);
    if (!catalogResponse.ok || !summaryResponse.ok) throw new Error('Replay data is missing. Start the app with scripts.serve_demo.');
    state.catalog = await catalogResponse.json();
    state.summary = await summaryResponse.json();
    renderResults();
    renderLibrary();
    const requested = new URL(location.href).searchParams.get('trace');
    if (state.catalog.some((item) => item.id === requested)) await loadTrace(requested);
    else showView('home');
  } catch (error) {
    chatStream.innerHTML = `<div class="inspector-empty"><h3>Could not load saved traces</h3><p>${escapeHtml(error.message)}</p></div>`;
    toast(error.message);
  }
}

start();
