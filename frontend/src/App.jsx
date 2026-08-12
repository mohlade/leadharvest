import { useCallback, useEffect, useRef, useState } from 'react';
import { API_URL } from './config.js';

// ─── Small helpers ────────────────────────────────────────────────────────────

function StatusBadge({ status }) {
  const map = {
    running: { cls: 'badge badge-running', dot: 'pulse-dot pulse-dot-yellow', label: 'Running' },
    done:    { cls: 'badge badge-done',    dot: 'pulse-dot pulse-dot-green',  label: 'Done'    },
    failed:  { cls: 'badge badge-failed',  dot: 'pulse-dot pulse-dot-red',    label: 'Failed'  },
  };
  const cfg = map[status] || { cls: 'badge', dot: '', label: status };
  return (
    <span className={cfg.cls}>
      {cfg.dot && <span className={cfg.dot} />}
      {cfg.label}
    </span>
  );
}

function EmailTypeBadge({ status }) {
  const cls = status === 'personal' ? 'badge badge-personal'
    : status === 'generic' ? 'badge badge-generic'
    : 'badge badge-invalid';
  return <span className={cls}>{status}</span>;
}

function Confidence({ value }) {
  const pct = Math.round((value || 0) * 100);
  const color = pct >= 75 ? 'var(--green)' : pct >= 50 ? 'var(--yellow)' : 'var(--red)';
  return (
    <div className="confidence-wrap">
      <span className="confidence-value" style={{ color }}>{pct}%</span>
      <div className="confidence-bar-bg">
        <div className="confidence-bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

// ─── Search Form ──────────────────────────────────────────────────────────────

function SearchForm({ onStart, onBulkStart, busy }) {
  const [role, setRole]                   = useState('');
  const [location, setLocation]           = useState('');
  const [country, setCountry]             = useState('US');
  const [maxPages, setMaxPages]           = useState(50);
  const [personalOnly, setPersonalOnly]   = useState(false);
  const [bulkMode, setBulkMode]           = useState(false);
  const [bulkText, setBulkText]           = useState('');

  const submit = (e) => {
    e.preventDefault();
    if (busy) return;
    if (bulkMode) {
      const lines = bulkText
        .split('\n')
        .map((l) => l.trim())
        .filter(Boolean)
        .map((l) => {
          const parts = l.split(',');
          return { role: parts[0]?.trim(), location: parts.slice(1).join(',').trim() };
        })
        .filter((r) => r.role && r.location);
      if (!lines.length) return;
      onBulkStart(lines.map((r) => ({ ...r, country, max_pages: Number(maxPages), personal_only: personalOnly })));
    } else {
      if (!role.trim() || !location.trim()) return;
      onStart({ role, location, country, max_pages: Number(maxPages), personal_only: personalOnly });
    }
  };

  return (
    <div className="search-card">
      {/* Mode tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        <button
          type="button"
          id="btn-single-mode"
          className={`btn btn-sm ${!bulkMode ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setBulkMode(false)}
        >
          Single search
        </button>
        <button
          type="button"
          id="btn-bulk-mode"
          className={`btn btn-sm ${bulkMode ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setBulkMode(true)}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/>
            <line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>
          </svg>
          Bulk mode
        </button>
      </div>

      <form onSubmit={submit}>
        {bulkMode ? (
          /* ── Bulk Mode ── */
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <label className="form-label">
              Bulk Searches — one per line: <span style={{ textTransform: 'none', color: 'var(--text-muted)', fontWeight: 400 }}>Role, Location</span>
              <textarea
                id="input-bulk"
                className="form-input"
                style={{ resize: 'vertical', minHeight: 120, fontFamily: 'monospace', lineHeight: 1.7 }}
                value={bulkText}
                onChange={(e) => setBulkText(e.target.value)}
                placeholder={"real estate agent, Texas\nmortgage broker, California\ninsurance agent, Florida"}
              />
            </label>
            <div className="form-grid" style={{ gridTemplateColumns: 'auto auto auto auto 1fr' }}>
              <label className="form-label">
                Country
                <select id="input-country-bulk" className="form-input" value={country} onChange={(e) => setCountry(e.target.value)}>
                  <option value="US">🇺🇸 United States</option>
                  <option value="CA">🇨🇦 Canada</option>
                  <option value="UK">🇬🇧 United Kingdom</option>
                  <option value="AU">🇦🇺 Australia</option>
                  <option value="IE">🇮🇪 Ireland</option>
                </select>
              </label>
              <label className="form-label">
                Max Pages
                <input id="input-max-pages-bulk" type="number" min={1} max={500} className="form-input" value={maxPages} onChange={(e) => setMaxPages(e.target.value)} />
              </label>
              <div className="toggle-wrap">
                Filter
                <label className="toggle-inner" htmlFor="input-personal-only-bulk">
                  <input id="input-personal-only-bulk" type="checkbox" checked={personalOnly} onChange={(e) => setPersonalOnly(e.target.checked)} />
                  <span className="toggle-label-text">Personal only</span>
                </label>
              </div>
              <div style={{ display: 'flex', alignItems: 'end' }}>
                <button type="submit" disabled={busy} id="btn-run-bulk" className="btn btn-primary" style={{ width: '100%' }}>
                  {busy ? <><span className="spinner" />Running…</> : <>Run all searches</>}
                </button>
              </div>
            </div>
          </div>
        ) : (
          /* ── Single Mode ── */
          <div className="form-grid">
            <label className="form-label">
              Role / Title
              <input id="input-role" className="form-input" value={role} onChange={(e) => setRole(e.target.value)} placeholder="e.g. real estate agent" required />
            </label>
            <label className="form-label">
              Location
              <input id="input-location" className="form-input" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="e.g. Texas, or Newark, Trenton" required />
            </label>
            <label className="form-label">
              Country
              <select id="input-country" className="form-input" value={country} onChange={(e) => setCountry(e.target.value)}>
                <option value="US">🇺🇸 United States</option>
                <option value="CA">🇨🇦 Canada</option>
                <option value="UK">🇬🇧 United Kingdom</option>
                <option value="AU">🇦🇺 Australia</option>
                <option value="IE">🇮🇪 Ireland</option>
              </select>
            </label>
            <label className="form-label">
              Max Pages
              <input id="input-max-pages" type="number" min={1} max={500} className="form-input" value={maxPages} onChange={(e) => setMaxPages(e.target.value)} />
            </label>
            <div className="toggle-wrap">
              Email Filter
              <label className="toggle-inner" htmlFor="input-personal-only">
                <input id="input-personal-only" type="checkbox" checked={personalOnly} onChange={(e) => setPersonalOnly(e.target.checked)} />
                <span className="toggle-label-text">Personal only</span>
              </label>
            </div>
            <div style={{ display: 'flex', alignItems: 'end' }}>
              <button type="submit" disabled={busy} id="btn-search" className="btn btn-primary" style={{ width: '100%' }}>
                {busy ? (
                  <><span className="spinner" />Searching…</>
                ) : (
                  <>
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
                    </svg>
                    Find Emails
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </form>
    </div>
  );
}

// ─── Bulk queue display ───────────────────────────────────────────────────────

function BulkQueue({ queue }) {
  if (!queue.length) return null;
  const done    = queue.filter((q) => q.status === 'done').length;
  const failed  = queue.filter((q) => q.status === 'failed').length;
  const running = queue.filter((q) => q.status === 'running').length;
  const pending = queue.filter((q) => q.status === 'pending').length;

  return (
    <div className="card" style={{ marginBottom: 24, animation: 'fadeIn 0.3s ease' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 700, fontSize: 15 }}>Bulk Queue</span>
        <span className="badge badge-done">{done} done</span>
        {running > 0 && <span className="badge badge-running">{running} running</span>}
        {pending > 0 && <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{pending} pending</span>}
        {failed > 0  && <span className="badge badge-failed">{failed} failed</span>}
      </div>
      <div style={{ display: 'grid', gap: 6 }}>
        {queue.map((item, i) => (
          <div key={i} style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '8px 12px', borderRadius: 8, background: 'rgba(255,255,255,0.02)',
            border: '1px solid var(--border)',
          }}>
            <span style={{ fontSize: 13, color: item.status === 'pending' ? 'var(--text-muted)' : 'var(--text)' }}>
              {item.role} · {item.location}
            </span>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 12, color: 'var(--text-muted)' }}>
              {item.emails_found != null && <span>{item.emails_found} found</span>}
              <StatusBadge status={item.status === 'pending' ? 'pending' : item.status} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [active, setActive]               = useState(null);
  const [searches, setSearches]           = useState([]);
  const [error, setError]                 = useState(null);
  const [minConfidence, setMinConfidence] = useState(0);
  const [bulkQueue, setBulkQueue]         = useState([]);
  const pollRef  = useRef(null);
  const bulkRef  = useRef([]);   // mirrors bulkQueue for async access

  const refreshHistory = useCallback(async () => {
    try {
      const res  = await fetch(`${API_URL}/api/contacts`);
      const data = await res.json();
      setSearches(data.searches || []);
    } catch {
      setError('Backend unreachable – is the server running?');
    }
  }, []);

  const loadActive = useCallback(async (id) => {
    try {
      const res  = await fetch(`${API_URL}/api/contacts/search/${id}`);
      const data = await res.json();
      if (data.error) { setError(data.error); return; }
      setActive(data);
      if (data.status === 'done' || data.status === 'failed') {
        clearInterval(pollRef.current);
        pollRef.current = null;
        refreshHistory();
      }
    } catch {
      setError('Backend unreachable');
    }
  }, [refreshHistory]);

  useEffect(() => {
    refreshHistory();
    return () => clearInterval(pollRef.current);
  }, [refreshHistory]);

  // ── single search ──
  const startSearch = async (payload) => {
    setError(null);
    try {
      const res  = await fetch(`${API_URL}/api/contacts/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.error) {
        setError(data.error);
        return;
      }
      if (data.contacts) {
        setActive(data);
        refreshHistory();
        return;
      }
      // Set optimistic active state immediately so UI updates without needing a refresh
      setActive({
        search_id: data.search_id,
        role: payload.role,
        location: payload.location,
        status: data.status || 'running',
        pages_checked: 0,
        emails_found: 0,
        contacts: [],
      });
      refreshHistory();
      clearInterval(pollRef.current);
      pollRef.current = setInterval(() => loadActive(data.search_id), 1500);
      loadActive(data.search_id);
    } catch {
      setError('Could not start search');
    }
  };

  // ── bulk search ──
  const startBulkSearch = async (payloads) => {
    setError(null);
    const initial = payloads.map((p) => ({ ...p, status: 'pending', emails_found: null, search_id: null }));
    setBulkQueue(initial);
    bulkRef.current = [...initial];

    for (let i = 0; i < payloads.length; i++) {
      // mark as running
      bulkRef.current = bulkRef.current.map((q, idx) => idx === i ? { ...q, status: 'running' } : q);
      setBulkQueue([...bulkRef.current]);

      try {
        const res  = await fetch(`${API_URL}/api/contacts/search`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payloads[i]),
        });
        const startData = await res.json();
        const sid = startData.search_id;

        if (startData.contacts) {
          bulkRef.current = bulkRef.current.map((q, idx) =>
            idx === i ? { ...q, status: startData.status, emails_found: startData.emails_found, search_id: sid } : q
          );
          setBulkQueue([...bulkRef.current]);
          continue;
        }

        // poll until done
        await new Promise((resolve) => {
          const iv = setInterval(async () => {
            try {
              const r = await fetch(`${API_URL}/api/contacts/search/${sid}`);
              const d = await r.json();
              bulkRef.current = bulkRef.current.map((q, idx) =>
                idx === i ? { ...q, status: d.status, emails_found: d.emails_found, search_id: sid } : q
              );
              setBulkQueue([...bulkRef.current]);
              if (d.status === 'done' || d.status === 'failed' || d.status === 'stopped') {
                clearInterval(iv);
                resolve();
              }
            } catch {
              clearInterval(iv);
              resolve();
            }
          }, 2500);
        });
      } catch {
        bulkRef.current = bulkRef.current.map((q, idx) => idx === i ? { ...q, status: 'failed' } : q);
        setBulkQueue([...bulkRef.current]);
      }
    }
    refreshHistory();
  };

  const openSearch = (id) => {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(() => loadActive(id), 2000);
    loadActive(id);
  };

  const stopSearch = async () => {
    if (!active?.search_id) return;
    try {
      const res  = await fetch(`${API_URL}/api/contacts/search/${active.search_id}/stop`, { method: 'POST' });
      const data = await res.json();
      if (data.contacts) {
        setActive(data);
        refreshHistory();
      } else {
        loadActive(active.search_id);
      }
    } catch {
      setError('Could not stop search');
    }
  };

  const busy = (active && active.status === 'running') || bulkQueue.some((q) => q.status === 'running');

  const csvUrl = active
    ? `${API_URL}/api/contacts/export.csv?search_id=${active.search_id}`
    : `${API_URL}/api/contacts/export.csv`;

  const visibleContacts = active
    ? active.contacts.filter((c) => (c.confidence || 0) >= minConfidence / 100)
    : [];

  const personalCount = visibleContacts.filter((c) => c.status === 'personal').length;
  const genericCount  = visibleContacts.filter((c) => c.status === 'generic').length;
  const dupCount      = visibleContacts.filter((c) => c.first_seen_search_id).length;

  return (
    <div className="app-wrapper">

      {/* ── Header ── */}
      <header className="app-header">
        <div className="header-badge">
          <span className="header-badge-dot" />
          AI-Verified Lead Finder
        </div>
        <h1 className="app-title">LeadHarvest</h1>
        <p className="app-subtitle">
          Deep-search the web for real contacts by role &amp; location — verified by AI, exported in one click.
        </p>
      </header>

      {/* ── Search Form ── */}
      <SearchForm onStart={startSearch} onBulkStart={startBulkSearch} busy={busy} />

      {/* ── Error ── */}
      {error && (
        <div className="error-banner" role="alert">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          {error}
        </div>
      )}

      {/* ── Bulk Queue ── */}
      <BulkQueue queue={bulkQueue} />

      {/* ── Active Results ── */}
      {active && (
        <section className="results-section">

          {busy && active.status === 'running' && (
            <div className="progress-wrap">
              <div className="progress-fill" style={{ width: '100%' }} />
            </div>
          )}

          <div className="results-header">
            <div>
              <h2 className="results-title">{active.role} · {active.location}</h2>
            </div>
            <StatusBadge status={active.status} />
            <div className="results-actions">
              <div className="filter-wrap">
                <span>Min confidence</span>
                <select id="select-confidence" className="filter-select" value={minConfidence} onChange={(e) => setMinConfidence(Number(e.target.value))}>
                  <option value={0}>All</option>
                  <option value={50}>50%+</option>
                  <option value={70}>70%+</option>
                  <option value={90}>90%+</option>
                </select>
              </div>
              <button id="btn-copy-emails" className="btn btn-ghost btn-sm"
                onClick={() => navigator.clipboard.writeText(visibleContacts.map((c) => c.email).join(', '))}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                </svg>
                Copy all
              </button>
              {active.status === 'running' && (
                <button
                  id="btn-stop-search"
                  className="btn btn-sm"
                  style={{ background: 'rgba(239,68,68,0.15)', color: '#f87171', border: '1px solid rgba(239,68,68,0.3)' }}
                  onClick={stopSearch}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                    <rect x="6" y="6" width="12" height="12" rx="2" />
                  </svg>
                  Stop &amp; Save
                </button>
              )}
              <a id="btn-export-csv" href={csvUrl} download className="btn btn-ghost btn-sm">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                Export CSV
              </a>
            </div>
          </div>

          {/* Stats chips */}
          <div className="stats-row">
            <div className="stat-chip">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
              </svg>
              <span className="stat-chip-num">{active.pages_checked ?? 0}</span>
              <span className="stat-chip-label">pages scanned</span>
            </div>
            <div className="stat-chip">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/>
              </svg>
              <span className="stat-chip-num">{active.emails_found ?? 0}</span>
              <span className="stat-chip-label">emails found</span>
            </div>
            {visibleContacts.length > 0 && (
              <>
                <div className="stat-chip">
                  <span className="badge badge-personal" style={{ fontSize: 10, padding: '2px 7px' }}>personal</span>
                  <span className="stat-chip-num">{personalCount}</span>
                </div>
                <div className="stat-chip">
                  <span className="badge badge-generic" style={{ fontSize: 10, padding: '2px 7px' }}>generic</span>
                  <span className="stat-chip-num">{genericCount}</span>
                </div>
                {dupCount > 0 && (
                  <div className="stat-chip">
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>🔁</span>
                    <span className="stat-chip-num">{dupCount}</span>
                    <span className="stat-chip-label">seen before</span>
                  </div>
                )}
                {visibleContacts.length !== active.contacts.length && (
                  <div className="stat-chip">
                    <span className="stat-chip-label">showing</span>
                    <span className="stat-chip-num">{visibleContacts.length}</span>
                    <span className="stat-chip-label">above {minConfidence}%</span>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Warning message */}
          {active.message && (
            <div className="warning-box">{active.message}</div>
          )}

          {/* Email quick-copy textarea */}
          {visibleContacts.length > 0 && (
            <div className="email-textarea-wrap">
              <span className="email-textarea-label">All emails — click to select &amp; copy</span>
              <textarea
                id="textarea-all-emails"
                className="email-textarea"
                readOnly
                rows={3}
                onFocus={(e) => e.target.select()}
                value={visibleContacts.map((c) => c.email).join(', ')}
              />
            </div>
          )}

          {/* Table or empty state */}
          {visibleContacts.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">{active.status === 'done' ? '📭' : '🔍'}</div>
              <p>{active.status === 'done' ? 'No valid emails found for this search.' : 'Scanning the web… results will appear shortly.'}</p>
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Email</th>
                    <th>Name</th>
                    <th>Company</th>
                    <th>Type</th>
                    <th>Confidence</th>
                    <th>Dup</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleContacts.map((c) => (
                    <tr key={c.id}>
                      <td>
                        <a href={`mailto:${c.email}`} className="email-link">{c.email}</a>
                      </td>
                      <td style={{ color: c.name ? 'var(--text)' : 'var(--text-muted)' }}>
                        {c.name || '—'}
                      </td>
                      <td style={{ color: c.company ? 'var(--text)' : 'var(--text-muted)' }}>
                        {c.company || '—'}
                      </td>
                      <td><EmailTypeBadge status={c.status} /></td>
                      <td><Confidence value={c.confidence} /></td>
                      <td title={c.first_seen_search_id ? `First seen in search ${c.first_seen_search_id.slice(0, 8)}…` : ''}>
                        {c.first_seen_search_id ? (
                          <span style={{ fontSize: 16, cursor: 'help' }} title={`Seen in a previous search`}>🔁</span>
                        ) : '—'}
                      </td>
                      <td>
                        {c.source_url ? (
                          <a href={c.source_url} target="_blank" rel="noreferrer" className="source-link">view ↗</a>
                        ) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* ── Divider ── */}
      {searches.length > 0 && <div className="divider" />}

      {/* ── Past Searches ── */}
      {searches.length > 0 && (
        <section className="past-section">
          <p className="section-title">Past Searches</p>
          <div className="search-history-list">
            {searches.map((s) => (
              <button key={s.id} id={`history-${s.id}`} className="history-item" onClick={() => openSearch(s.id)}>
                <div className="history-item-left">
                  <span className="history-role">{s.role}</span>
                  <span className="history-location">{s.location}</span>
                </div>
                <div className="history-item-right">
                  <StatusBadge status={s.status} />
                  <span className="history-count">{s.saved} saved</span>
                  <span className="history-date">
                    {s.started_at
                      ? new Date(s.started_at + 'Z').toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
                      : ''}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
