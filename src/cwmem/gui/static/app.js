/* cwmem GUI — SPA application logic */

// --- Fetch wrapper ---
async function api(path, opts = {}) {
  const resp = await fetch('/api' + path, opts);
  if (!resp.ok) {
    const text = await resp.text();
    let msg;
    try { msg = JSON.parse(text).detail || text; } catch { msg = text; }
    throw new Error(msg);
  }
  return resp.json();
}

async function apiPost(path, body, params = {}) {
  const qs = new URLSearchParams(params).toString();
  return api(path + (qs ? '?' + qs : ''), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

// --- Toast ---
let toastTimer = null;
function toast(msg, type = '') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast ' + type;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('hidden'), 3000);
}

// --- Tab routing ---
document.getElementById('tabs').addEventListener('click', e => {
  const btn = e.target.closest('.tab');
  if (!btn) return;
  const tabName = btn.dataset.tab;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t === btn));
  document.querySelectorAll('.tab-content').forEach(s =>
    s.classList.toggle('active', s.id === 'tab-' + tabName)
  );
  if (tabName === 'dashboard') loadDashboard();
  if (tabName === 'entries') loadEntries();
  if (tabName === 'events') loadEvents();
  if (tabName === 'graph') loadGraphOverview();
});

// --- Dashboard ---
async function loadDashboard() {
  try {
    const data = await api('/dashboard');
    const cards = document.getElementById('dashboard-cards');
    const stats = data.stats || {};
    const status = data.status || {};
    cards.innerHTML = [
      card('Initialized', status.initialized ? 'Yes' : 'No', status.initialized ? 'ok' : 'error'),
      card('Database', status.database_exists ? 'Present' : 'Missing', status.database_exists ? 'ok' : 'error'),
      card('Entries', stats.entries ?? '-'),
      card('Events', stats.events ?? '-'),
      card('Entities', stats.entities ?? '-'),
      card('Edges', stats.edges ?? '-'),
      card('Embeddings', stats.embeddings ?? '-'),
      card('Model', data.model_manifest_present ? 'Loaded' : 'Missing', data.model_manifest_present ? 'ok' : 'warn'),
    ].join('');

    const details = document.getElementById('dashboard-details');
    const sections = [];
    if (stats.last_build_at) {
      sections.push(`<p>Last build: <strong>${esc(shortTs(stats.last_build_at))}</strong></p>`);
    }
    if (stats.embedding_model) {
      sections.push(`<p>Embedding model: <strong>${esc(stats.embedding_model)}</strong></p>`);
    }
    if (data.lock_info) {
      const l = data.lock_info;
      sections.push(
        `<div class="card" style="margin-top:0.75rem;border-color:var(--warning)">` +
        `<div class="label">Active Lock</div>` +
        `<p style="margin-top:0.3rem">PID ${l.pid} on ${esc(l.hostname)} &mdash; ${esc(l.command)}</p></div>`
      );
    }
    if (status.missing_paths && status.missing_paths.length) {
      sections.push(
        `<div class="card" style="margin-top:0.75rem;border-color:var(--error)">` +
        `<div class="label">Missing Paths</div>` +
        `<p style="margin-top:0.3rem">${status.missing_paths.map(p => '<code>' + esc(p) + '</code>').join(', ')}</p></div>`
      );
    }
    details.innerHTML = sections.join('');
  } catch (err) {
    toast('Dashboard: ' + err.message, 'error');
  }
}

function card(label, value, cls = '') {
  return `<div class="card"><div class="label">${esc(label)}</div><div class="value ${cls}">${esc(String(value))}</div></div>`;
}

// --- Entries ---
async function loadEntries() {
  try {
    const tag = document.getElementById('entries-tag').value.trim();
    const type = document.getElementById('entries-type').value;
    const status = document.getElementById('entries-status').value;
    const author = document.getElementById('entries-author').value.trim();
    const params = new URLSearchParams();
    if (tag) params.set('tag', tag);
    if (type) params.set('type', type);
    if (status) params.set('status', status);
    if (author) params.set('author', author);
    const qs = params.toString();
    const entries = await api('/entries' + (qs ? '?' + qs : ''));
    const wrap = document.getElementById('entries-table-wrap');
    if (!entries.length) {
      wrap.innerHTML = emptyState('No entries found', 'Create entries with the Write tab or via cwmem add.');
      return;
    }
    wrap.innerHTML = buildTable(
      ['ID', 'Type', 'Status', 'Title', 'Author', 'Updated'],
      entries.map(e => [
        e.public_id,
        badge(e.type),
        badge(e.status, 'active'),
        trunc(e.title, 55),
        e.author || '<span style="color:var(--text-muted)">-</span>',
        shortTs(e.updated_at),
      ])
    );
    wrap.querySelectorAll('tr[data-idx]').forEach(tr => {
      tr.addEventListener('click', () => showEntryDetail(entries[+tr.dataset.idx]));
    });
  } catch (err) {
    toast('Entries: ' + err.message, 'error');
  }
}
document.getElementById('entries-filter-btn').addEventListener('click', loadEntries);

function showEntryDetail(entry) {
  const panel = document.getElementById('entries-detail');
  panel.classList.remove('hidden');
  panel.innerHTML = resourceDetailHtml(entry, 'entry');
}

// --- Search ---
document.getElementById('search-btn').addEventListener('click', doSearch);
document.getElementById('search-q').addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });

async function doSearch() {
  const q = document.getElementById('search-q').value.trim();
  if (!q) return;
  const mode = document.getElementById('search-mode').value;
  const tag = document.getElementById('search-tag').value.trim();
  const expand = document.getElementById('search-expand').checked;
  const params = new URLSearchParams({ q });
  if (mode) params.set('mode', mode);
  if (tag) params.set('tag', tag);
  if (expand) params.set('expand', 'true');
  try {
    const results = await api('/search?' + params.toString());
    const wrap = document.getElementById('search-results');
    if (!results.length) {
      wrap.innerHTML = emptyState('No results', 'Try different keywords or switch to Lexical mode.');
      return;
    }
    wrap.innerHTML = buildTable(
      ['ID', 'Kind', 'Modes', 'Score', 'Label', 'Summary'],
      results.map(r => [
        r.hit.resource_id,
        badge(r.kind),
        r.hit.match_modes.join(', '),
        '<span class="score">' + r.hit.score.toFixed(3) + '</span>',
        trunc(r.label, 40),
        trunc(r.summary, 50),
      ])
    );
    wrap.querySelectorAll('tr[data-idx]').forEach(tr => {
      tr.addEventListener('click', () => showSearchDetail(results[+tr.dataset.idx]));
    });
  } catch (err) {
    toast('Search: ' + err.message, 'error');
  }
}

function showSearchDetail(result) {
  const panel = document.getElementById('search-detail');
  panel.classList.remove('hidden');
  const r = result.resource;
  let html = resourceDetailHtml(r, result.kind);
  const expl = result.hit.explanation;
  if (expl) {
    html += '<div class="field"><div class="field-label">Explanation</div><div class="field-value">';
    if (expl.lexical_rank != null) html += `Lexical rank: ${expl.lexical_rank}<br>`;
    if (expl.semantic_rank != null) html += `Semantic rank: ${expl.semantic_rank}<br>`;
    if (expl.rrf_score != null) html += `RRF score: ${expl.rrf_score.toFixed(4)}<br>`;
    if (expl.matched_fields && expl.matched_fields.length) html += `Matched: ${expl.matched_fields.join(', ')}<br>`;
    html += '</div></div>';
  }
  panel.innerHTML = html;
}

// --- Events ---
async function loadEvents() {
  try {
    const resource = document.getElementById('events-resource').value.trim();
    const eventType = document.getElementById('events-type').value.trim();
    const params = new URLSearchParams();
    if (resource) params.set('resource', resource);
    if (eventType) params.set('event_type', eventType);
    const qs = params.toString();
    const events = await api('/events' + (qs ? '?' + qs : ''));
    const wrap = document.getElementById('events-table-wrap');
    if (!events.length) {
      wrap.innerHTML = emptyState('No events found', 'Events are created automatically when entries are added.');
      return;
    }
    wrap.innerHTML = buildTable(
      ['ID', 'Type', 'Occurred', 'Summary', 'Resources'],
      events.map(e => {
        const summary = (e.metadata && e.metadata.summary) || e.event_type;
        return [
          e.public_id,
          badge(e.event_type),
          shortTs(e.occurred_at),
          trunc(summary, 48),
          (e.resources || []).length,
        ];
      })
    );
    wrap.querySelectorAll('tr[data-idx]').forEach(tr => {
      tr.addEventListener('click', () => showEventDetail(events[+tr.dataset.idx]));
    });
  } catch (err) {
    toast('Events: ' + err.message, 'error');
  }
}
document.getElementById('events-filter-btn').addEventListener('click', loadEvents);

function showEventDetail(event) {
  const panel = document.getElementById('events-detail');
  panel.classList.remove('hidden');
  panel.innerHTML = resourceDetailHtml(event, 'event');
}

// --- Graph ---
document.getElementById('graph-btn').addEventListener('click', loadGraph);
document.getElementById('graph-id').addEventListener('keydown', e => { if (e.key === 'Enter') loadGraph(); });

let graphOverviewLoaded = false;

async function loadGraphOverview() {
  if (graphOverviewLoaded) return;
  const id = document.getElementById('graph-id').value.trim();
  if (id) return;
  try {
    const data = await api('/graph-overview');
    if (data.nodes && data.nodes.length === 0 && (!data.edges || data.edges.length === 0)) {
      document.getElementById('cy').innerHTML = emptyState(
        'No graph data yet',
        'Add entries, entities, and links to build a knowledge graph.'
      );
      return;
    }
    renderGraph(data);
    graphOverviewLoaded = true;
  } catch (err) {
    toast('Graph overview: ' + err.message, 'error');
  }
}

async function loadGraph() {
  const id = document.getElementById('graph-id').value.trim();
  if (!id) { loadGraphOverviewForced(); return; }
  const depth = document.getElementById('graph-depth').value || '2';
  const rel = document.getElementById('graph-relation').value.trim();
  const params = new URLSearchParams({ depth });
  if (rel) params.set('relation_type', rel);
  try {
    const data = await api('/graph/' + encodeURIComponent(id) + '?' + params.toString());
    renderGraph(data);
    graphOverviewLoaded = false;
  } catch (err) {
    toast('Graph: ' + err.message, 'error');
  }
}

async function loadGraphOverviewForced() {
  try {
    const data = await api('/graph-overview');
    renderGraph(data);
    graphOverviewLoaded = true;
  } catch (err) {
    toast('Graph overview: ' + err.message, 'error');
  }
}

// --- Write forms ---
document.querySelectorAll('.write-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.write-tab').forEach(b => b.classList.toggle('active', b === btn));
    document.querySelectorAll('.write-form').forEach(f =>
      f.classList.toggle('active', f.id === 'form-' + btn.dataset.form)
    );
  });
});

window.submitForm = async function submitForm(formName, dryRun) {
  const form = document.getElementById('form-' + formName);
  const resultBox = document.getElementById('result-' + formName);
  try {
    let result;
    if (formName === 'add-entry') {
      const d = formData(form);
      const body = {
        title: d.title, body: d.body, type: d.type, status: d.status,
        author: d.author || null,
        tags: d.tags ? d.tags.split(',').map(t => t.trim()).filter(Boolean) : [],
      };
      result = await apiPost('/entries', body, dryRun ? { dry_run: 'true' } : {});
    } else if (formName === 'mutate-tags') {
      const d = formData(form);
      const body = {
        resource_id: d.resource_id,
        tags: d.tags.split(',').map(t => t.trim()).filter(Boolean),
      };
      const add = d.action === 'add';
      result = await apiPost('/tags', body, { add, ...(dryRun ? { dry_run: 'true' } : {}) });
    } else if (formName === 'link-resources') {
      const d = formData(form);
      const body = {
        source_id: d.source_id, target_id: d.target_id,
        relation_type: d.relation_type,
        confidence: parseFloat(d.confidence) || 1.0,
      };
      result = await apiPost('/edges', body, dryRun ? { dry_run: 'true' } : {});
    }
    resultBox.classList.remove('hidden');
    resultBox.textContent = JSON.stringify(result, null, 2);
    toast(dryRun ? 'Dry-run complete' : 'Mutation applied', 'success');
  } catch (err) {
    resultBox.classList.remove('hidden');
    resultBox.textContent = 'Error: ' + err.message;
    toast(err.message, 'error');
  }
};

function formData(form) {
  const fd = new FormData(form);
  const obj = {};
  for (const [k, v] of fd.entries()) obj[k] = v;
  return obj;
}

// --- Helpers ---
function buildTable(headers, rows) {
  const ths = headers.map(h => `<th>${esc(h)}</th>`).join('');
  const trs = rows.map((r, i) =>
    `<tr data-idx="${i}">${r.map(c => `<td>${c}</td>`).join('')}</tr>`
  ).join('');
  return `<table><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
}

function badge(text, variant) {
  const v = variant || text;
  const cls = v === 'active' ? 'badge-active'
    : v === 'decision' ? 'badge-decision'
    : v === 'note' ? 'badge-note'
    : '';
  return `<span class="badge ${cls}">${esc(text)}</span>`;
}

function emptyState(title, subtitle) {
  return `<div class="empty-state"><strong>${esc(title)}</strong>${subtitle ? esc(subtitle) : ''}</div>`;
}

function resourceDetailHtml(r, kind) {
  let html = '';
  if (kind === 'entry') {
    html += `<h3>${esc(r.title)}</h3>`;
    html += field('ID', `<code>${esc(r.public_id)}</code>`);
    html += field('Type', badge(r.type));
    html += field('Status', badge(r.status, 'active'));
    html += field('Author', esc(r.author || 'n/a'));
    html += field('Updated', shortTs(r.updated_at));
    if (r.tags && r.tags.length) html += field('Tags', r.tags.map(t => `<span class="tag">${esc(t)}</span>`).join(' '));
    if (r.entity_refs && r.entity_refs.length) html += field('Entity refs', r.entity_refs.map(e => `<code>${esc(e)}</code>`).join(' '));
    if (r.related_ids && r.related_ids.length) html += field('Related', r.related_ids.map(e => `<code>${esc(e)}</code>`).join(' '));
    html += field('Body', '<pre style="white-space:pre-wrap;font-size:11px">' + esc(r.body) + '</pre>');
  } else if (kind === 'event') {
    const summary = (r.metadata && r.metadata.summary) || r.event_type;
    html += `<h3>${esc(summary)}</h3>`;
    html += field('ID', `<code>${esc(r.public_id)}</code>`);
    html += field('Event type', badge(r.event_type));
    html += field('Actor', esc(r.author || 'n/a'));
    html += field('Occurred', shortTs(r.occurred_at));
    if (r.tags && r.tags.length) html += field('Tags', r.tags.map(t => `<span class="tag">${esc(t)}</span>`).join(' '));
    if (r.resources && r.resources.length) {
      html += field('Resources', r.resources.map(x => `<code>${esc(x.resource_id)}</code> (${esc(x.role)})`).join(', '));
    }
    html += field('Body', '<pre style="white-space:pre-wrap;font-size:11px">' + esc(r.body) + '</pre>');
  } else if (kind === 'entity') {
    html += `<h3>${esc(r.name)}</h3>`;
    html += field('ID', `<code>${esc(r.public_id)}</code>`);
    html += field('Entity type', badge(r.entity_type));
    html += field('Status', badge(r.status, 'active'));
    html += field('Updated', shortTs(r.updated_at));
    if (r.aliases && r.aliases.length) html += field('Aliases', r.aliases.map(a => `<code>${esc(a)}</code>`).join(' '));
    if (r.tags && r.tags.length) html += field('Tags', r.tags.map(t => `<span class="tag">${esc(t)}</span>`).join(' '));
    html += field('Description', esc(r.description) || '<span style="color:var(--text-muted)">No description</span>');
  }
  const resourceId = r.public_id;
  if (resourceId) {
    html += `<div style="margin-top:0.75rem"><button class="btn" onclick="navigateToGraph('${esc(resourceId)}')">View in Graph</button></div>`;
  }
  return html;
}

window.navigateToGraph = function(id) {
  document.getElementById('graph-id').value = id;
  document.querySelector('.tab[data-tab="graph"]').click();
  loadGraph();
};

function field(label, value) {
  return `<div class="field"><div class="field-label">${esc(label)}</div><div class="field-value">${value}</div></div>`;
}

function esc(s) {
  if (s == null) return '';
  const div = document.createElement('div');
  div.textContent = String(s);
  return div.innerHTML;
}

function trunc(s, n) {
  if (!s) return '';
  s = String(s);
  return s.length <= n ? esc(s) : esc(s.slice(0, n - 1)) + '&hellip;';
}

function shortTs(s) {
  if (!s) return '';
  return esc(s.replace('T', ' ').slice(0, 19));
}

// --- Graph layout controls ---
function setupLayoutControls() {
  const controls = [
    { id: 'ctrl-repulsion', key: 'nodeRepulsion', outId: 'out-repulsion', parse: parseInt },
    { id: 'ctrl-edgeLength', key: 'idealEdgeLength', outId: 'out-edgeLength', parse: parseInt },
    { id: 'ctrl-gravity', key: 'gravity', outId: 'out-gravity', parse: parseFloat },
    { id: 'ctrl-spacing', key: 'componentSpacing', outId: 'out-spacing', parse: parseInt },
  ];
  for (const c of controls) {
    const el = document.getElementById(c.id);
    if (!el) continue;
    el.addEventListener('input', () => {
      const val = c.parse(el.value);
      layoutSettings[c.key] = val;
      document.getElementById(c.outId).textContent = el.value;
    });
  }
}
setupLayoutControls();

// --- Init ---
loadDashboard();
