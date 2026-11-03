(() => {
  'use strict';

  const state = { league: 'college', competition: 'all', days: '7', search: '', tracked: [], games: [] };
  const COLLEGE = new Set(['d1','d2','d3','naia']);
  const PROS = new Set(['gleague','nba']);
  const LABEL = {d1:'NCAA DIVISION I', d2:'NCAA DIVISION II', d3:'NCAA DIVISION III', naia:'NAIA', gleague:'NBA G LEAGUE', nba:'NBA'};
  const $ = (id) => document.getElementById(id);
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const d = (value) => { if (value == null || value === '') return null; const x = new Date(value); return Number.isNaN(x.valueOf()) ? null : x; };
  const arizonaDay = (date, options = {}) => date ? new Intl.DateTimeFormat('en-US', { timeZone: 'America/Phoenix', ...options }).format(date) : 'Unknown date';
  const initials = (name) => String(name).split(' ').filter(Boolean).slice(0,2).map(x => x[0]).join('').toUpperCase();

  function rangeMatches(game) {
    if (state.days === 'all') return true;
    const day = d(game.date);
    if (!day) return false;
    // Exact time window in days; no timezone boundary surprises for filtering.
    return day.getTime() >= Date.now() - Number(state.days) * 86400000;
  }

  function gameCard(game) {
    const isNba = PROS.has(game.league);
    const stats = Array.isArray(game.stats) ? game.stats : [];
    const outcome = game.outcome === 'W' ? 'win' : game.outcome === 'L' ? 'loss' : 'tie';
    const date = arizonaDay(d(game.date), {month:'short', day:'numeric', year:'numeric'}).toUpperCase();
    const opponent = `${game.home ? 'vs' : '@'} ${game.opponent || 'Unknown'}`;
    const url = /^https:\/\/(www\.espn\.com|www\.ncaa\.com|sport-stats\.mynaia\.org)\//.test(String(game.boxscore_url)) ? game.boxscore_url : '';
    return `<article class="game-card">
      <div class="game-upper">
        <div class="game-person"><div class="person-avatar ${isNba?'nba':''}" aria-hidden="true">${escapeHtml(initials(game.name))}</div><div><span class="league-tag">${escapeHtml(LABEL[game.league] || game.league)}</span><h3>${escapeHtml(game.name)}</h3><div class="person-meta">${escapeHtml(game.team)}${game.gcu_years ? ' · GCU ' + escapeHtml(game.gcu_years) : ''}</div></div></div>
        <div class="game-matchup"><div class="matchup-date">${date}</div><div class="opponent">${escapeHtml(opponent)}</div><div class="matchup-score"><span class="outcome ${outcome}">${escapeHtml(game.outcome)}</span> ${escapeHtml(game.score_for)}–${escapeHtml(game.score_against)}</div></div>
        <div class="game-key-stats"><div class="big-stat"><strong>${escapeHtml(game.pts)}</strong><span>PTS</span></div><div class="big-stat"><strong>${escapeHtml(game.reb)}</strong><span>REB</span></div><div class="big-stat"><strong>${escapeHtml(game.ast)}</strong><span>AST</span></div></div>
      </div>
      <details class="details-wrap"><summary><span>FULL STAT LINE <span style="opacity:.5">/ ${stats.length} FIELDS</span></span><span class="open-indicator" aria-hidden="true">+</span></summary><div class="detail-body"><div class="full-stats">${stats.map(s=>`<div class="full-stat"><span>${escapeHtml(s.label)}</span><strong>${escapeHtml(s.value)}</strong></div>`).join('')}</div>${url?`<a class="boxscore-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">VIEW ORIGINAL BOX SCORE / SOURCE ↗</a>`:''}</div></details>
    </article>`;
  }

  function emptyMessage() {
    const label = state.league === 'college' ? 'college transfer' : state.league === 'pros' ? 'professional alumni' : 'tracked';
    if (state.search) return { title: 'NO MATCHES FOUND', body: 'Try another player, school, or opponent.' };
    if (state.days !== 'all') return { title: 'NO RECENT GAMES FOUND', body: `There are no completed ${label} appearances in this time window. Choose “All time” or check back after games become final.` };
    if (state.league === 'pros' && !state.tracked.some(p => PROS.has(p.league))) return { title: 'PRO WATCHLIST IS READY', body: 'Add an NBA or G League alumnus in players.json to start tracking their games.' };
    return { title: 'WAITING FOR THE FIRST BOX SCORE', body: `Tracked ${label} players are ready. Completed games will appear automatically once the updater runs and the relevant data provider reports the appearance.` };
  }

  function renderFeed() {
    const games = state.games.filter(g => (state.league === 'all' || (state.league === 'college' ? COLLEGE.has(g.league) : PROS.has(g.league))) && (state.competition === 'all' || g.league === state.competition) && rangeMatches(g) && [g.name,g.team,g.opponent].some(v => String(v||'').toLowerCase().includes(state.search)));
    const target = $('feed-results');
    if (!games.length) {
      const {title,body} = emptyMessage();
      target.innerHTML = `<div class="empty-panel"><div class="empty-icon" aria-hidden="true">◎</div><h3>${title}</h3><p>${body}</p></div>`;
    } else {
      target.innerHTML = games.sort((a,b) => String(b.date).localeCompare(String(a.date))).map(gameCard).join('');
    }
  }

  function renderWatchlist() {
    const ordered = [...state.tracked].sort((a,b) => (COLLEGE.has(a.league) ? 0 : 1) - (COLLEGE.has(b.league) ? 0 : 1) || a.name.localeCompare(b.name));
    $('watchlist-grid').innerHTML = ordered.length ? ordered.map((p, i) => `<article class="watch-card"><div class="watch-num">${String(i+1).padStart(2,'0')} / ${escapeHtml(LABEL[p.league] || p.league)}</div><h3>${escapeHtml(p.name)}</h3><div class="watch-team">${escapeHtml(p.team)}</div><div class="watch-bottom"><span>${p.gcu_years ? 'GCU '+escapeHtml(p.gcu_years) : 'GCU ALUMNI'}</span><span>TRACKING</span></div></article>`).join('') : '<div class="empty-panel"><h3>NO PLAYERS YET</h3><p>Add a player in players.json and run the updater.</p></div>';
  }

  function renderSummary() {
    $('count-all').textContent = state.tracked.length;
    $('count-college').textContent = state.tracked.filter(p => COLLEGE.has(p.league)).length;
    $('count-nba').textContent = state.tracked.filter(p => PROS.has(p.league)).length;
    $('count-games').textContent = state.games.length;
    $('tab-college-count').textContent = state.games.filter(g => COLLEGE.has(g.league)).length;
    $('tab-nba-count').textContent = state.games.filter(g => PROS.has(g.league)).length;
  }

  document.querySelectorAll('[data-league]').forEach(btn => btn.addEventListener('click', () => {
    state.league = btn.dataset.league;
    document.querySelectorAll('[data-league]').forEach(tab => { const on = tab.dataset.league === state.league; tab.classList.toggle('active', on); tab.setAttribute('aria-pressed', String(on)); });
    renderFeed();
  }));
  $('league-filter').addEventListener('change', (e) => { state.competition = e.target.value; state.league = 'all'; document.querySelectorAll('[data-league]').forEach(tab => { const on = tab.dataset.league === 'all'; tab.classList.toggle('active', on); tab.setAttribute('aria-pressed', String(on)); }); renderFeed(); });
  $('date-range').addEventListener('change', (e) => { state.days = e.target.value; renderFeed(); });
  $('search').addEventListener('input', (e) => { state.search = e.target.value.trim().toLowerCase(); renderFeed(); });

  async function start() {
    try {
      const response = await fetch(`./data/results.json?t=${Date.now()}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      state.games = Array.isArray(data.games) ? data.games : [];
      state.tracked = Array.isArray(data.tracked) ? data.tracked : [];
      const noNaiaSource = state.tracked.some(p => p.league === 'naia') && !data.coverage?.naia?.configured;
      $('coverage-status').textContent = noNaiaSource ? 'NAIA requires a configured, current-season data feed. Without a verified provider key, NAIA games will not generate automatic phone alerts.' : '';
      const update = d(data.updated_at);
      $('updated-label').textContent = update ? `LAST SYNC ${arizonaDay(update, {month:'short',day:'numeric',hour:'numeric',minute:'2-digit',hour12:true}).toUpperCase()}` : 'AWAITING FIRST UPDATE';
      renderSummary(); renderFeed(); renderWatchlist();
    } catch (e) {
      $('updated-label').textContent = 'DATA UNAVAILABLE';
      $('feed-results').innerHTML = `<div class="empty-panel"><div class="empty-icon">!</div><h3>COULD NOT LOAD THE FEED</h3><p>Run the tracker updater and serve this folder via a local web server or GitHub Pages. Check the browser console if the issue persists.</p></div>`;
      $('watchlist-grid').innerHTML = '<div class="loading-panel">Watchlist unavailable.</div>';
      console.error('Lopes Tracker loading failed', e);
    }
  }
  start();
})();
