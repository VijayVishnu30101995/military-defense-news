const API_BASE = window.API_BASE || 'http://localhost:8001/api/v1';

const authCard = document.getElementById('authCard');
const dashboardEl = document.getElementById('dashboard');
const dashboardView = document.getElementById('dashboardView');
const sourceView = document.getElementById('sourceView');
const loginForm = document.getElementById('loginForm');
const emailInput = document.getElementById('emailInput');
const passwordInput = document.getElementById('passwordInput');
const logoutBtn = document.getElementById('logoutBtn');
const viewSwitcher = document.getElementById('viewSwitcher');
const themeToggleBtn = document.getElementById('themeToggleBtn');
const navTabs = document.querySelectorAll('.nav-tab');
const statsGrid = document.getElementById('statsGrid');
const topDevelopments = document.getElementById('topDevelopments');
const leadGrid = document.getElementById('leadGrid');
const newsletterPanel = document.getElementById('newsletterPanel');
const generateBriefBtn = document.getElementById('generateBriefBtn');
const searchInput = document.getElementById('searchInput');
const articleFilterForm = document.getElementById('articleFilterForm');
const categoryFilter = document.getElementById('categoryFilter');
const categoryChips = document.getElementById('categoryChips');
const countryFilter = document.getElementById('countryFilter');
const regionFilter = document.getElementById('regionFilter');
const sourceFilter = document.getElementById('sourceFilter');
const dateFromFilter = document.getElementById('dateFromFilter');
const dateToFilter = document.getElementById('dateToFilter');
const resetFiltersBtn = document.getElementById('resetFiltersBtn');
const articleCountLabel = document.getElementById('articleCountLabel');
const articleResults = document.getElementById('articleResults');
const sourceForm = document.getElementById('sourceForm');
const sourceTable = document.getElementById('sourceTable');
const collectAllBtn = document.getElementById('collectAllBtn');
const collectionStatusEl = document.getElementById('collectionStatus');
const collectionProgressEl = document.getElementById('collectionProgress');
const sourceName = document.getElementById('sourceName');
const sourceWebsite = document.getElementById('sourceWebsite');
const sourceFeed = document.getElementById('sourceFeed');
const sourceType = document.getElementById('sourceType');
const sourceReliability = document.getElementById('sourceReliability');
const sourceFrequency = document.getElementById('sourceFrequency');
const sourceActive = document.getElementById('sourceActive');
const articleDetailModal = document.getElementById('articleDetailModal');
const articleDetailContent = document.getElementById('articleDetailContent');
const closeModalBtn = document.getElementById('closeModalBtn');

const tokenKey = 'defense-brief-token';
const themeKey = 'defense-brief-theme';

const HEALTH_REFRESH_INTERVAL_MS = 60000; // 60s
let healthRefreshTimer = null;

const COLLECTION_POLL_INTERVAL_MS = 2000;
let collectionPollTimer = null;
let lastCollectionStatus = 'idle';
const COLLECTION_STATUS = {
  idle: { label: 'Idle', className: 'status-neutral' },
  in_progress: { label: 'In progress', className: 'status-info' },
  completed: { label: 'Completed', className: 'status-ok' },
  completed_with_errors: { label: 'Completed with errors', className: 'status-warning' },
  failed: { label: 'Failed', className: 'status-paused' },
};
const SOURCE_RUN_STATUS = {
  pending: { label: 'Waiting', className: 'status-neutral' },
  running: { label: 'Collecting', className: 'status-info' },
  succeeded: { label: 'Done', className: 'status-ok' },
  failed: { label: 'Failed', className: 'status-paused' },
};

const PAGE_SIZE = 12;
const state = {
  user: null,
  countries: [],
  regions: [],
  categories: [],
  sources: [],
  currentPage: 1,
  // The current page of results and the total matching the filters, for selection.
  pageItems: [],
  filteredTotal: 0,
};

function getToken() {
  return localStorage.getItem(tokenKey);
}

function setToken(token) {
  if (token) {
    localStorage.setItem(tokenKey, token);
  } else {
    localStorage.removeItem(tokenKey);
  }
}

function getTheme() {
  return localStorage.getItem(themeKey) || 'dark';
}

function setTheme(theme) {
  const resolved = theme === 'light' ? 'light' : 'dark';
  document.body.dataset.theme = resolved;
  localStorage.setItem(themeKey, resolved);
  themeToggleBtn.textContent = resolved === 'dark' ? 'Light mode' : 'Dark mode';
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function cssUrl(value) {
  return String(value || '').replace(/'/g, "\\'");
}

// A story with no usable picture gets a labelled tile rather than a stock photo, so
// the page never implies a photograph belongs to a story it was not taken for.
function placeholderHtml(categories, className = '') {
  const label = Array.isArray(categories) && categories.length ? categories[0] : 'Defense';
  return `<div class="img-placeholder ${className}" role="img" aria-label="No photograph available">
    <span>${escapeHtml(label)}</span>
  </div>`;
}

function imageHtml(url, categories, className = '') {
  if (!url) return placeholderHtml(categories, className);
  return `<img class="${className}" src="${escapeHtml(url)}" alt="" loading="lazy" decoding="async"
    data-placeholder="${escapeHtml(JSON.stringify(categories || []))}">`;
}

// A picture that fails to load is replaced by the same labelled tile. It must never be
// swapped for another story's photograph, which is what made cards disagree with the
// article they opened.
document.addEventListener('error', (event) => {
  const img = event.target;
  if (!(img instanceof HTMLImageElement) || !img.dataset.placeholder) return;
  let categories = [];
  try {
    categories = JSON.parse(img.dataset.placeholder);
  } catch (error) {
    categories = [];
  }
  img.insertAdjacentHTML('afterend', placeholderHtml(categories, img.className));
  img.remove();
}, true);

function getSourceName(id) {
  const match = state.sources.find((item) => Number(item.id) === Number(id));
  return match ? match.name : '';
}

function isAdmin() {
  return state.user?.role === 'admin';
}

function setCurrentUser(user) {
  state.user = user;
  if (user?.role) {
    document.body.dataset.role = user.role;
  } else {
    delete document.body.dataset.role;
  }
}

function getLabelById(list, id) {
  if (id == null || id === '') return 'General';
  const match = list.find((item) => Number(item.id) === Number(id));
  return match ? match.name : 'General';
}

async function api(path, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const errorText = await response.text();
    if (response.status === 401 && token && getToken() === token) {
      logout();
    }
    let message = errorText;
    try {
      const { detail } = JSON.parse(errorText);
      if (typeof detail === 'string') message = detail;
      // Validation errors arrive as a list; show their messages rather than raw JSON.
      if (Array.isArray(detail)) {
        message = detail.map((item) => String(item.msg || '').replace(/^Value error, /, '')).filter(Boolean).join(' ') || message;
      }
    } catch {
      // Not JSON; show the raw text.
    }
    throw new Error(message || 'Request failed');
  }

  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json();
  }

  return response.text();
}

function renderStats(data) {
  const stats = data?.statistics || {};
  const cards = [
    { label: 'Total stories', value: stats.total_news ?? 0, tone: 'blue' },
    { label: 'Important', value: stats.important_news ?? 0, tone: 'cyan' },
    { label: 'Categories', value: stats.categories ?? 0, tone: 'green' },
    { label: 'Sources', value: data?.source_count ?? 0, tone: 'purple' },
  ];

  statsGrid.innerHTML = cards.map((card) => `
    <div class="stat-card ${card.tone}">
      <div class="label">${card.label}</div>
      <div class="value">${card.value}</div>
    </div>
  `).join('');

  // Insert aggregate health card placeholder (updated separately by renderAggregateHealth)
  const existingHealth = document.getElementById('healthAggregateCard');
  if (!existingHealth) {
    const node = document.createElement('div');
    node.id = 'healthAggregateCard';
    node.className = 'stat-card health admin-only';
    node.innerHTML = `<div class="label">Healthy sources</div><div class="value">0</div>`;
    statsGrid.prepend(node);
  }
}

function renderAggregateHealth() {
  const healthCard = document.getElementById('healthAggregateCard');
  if (!healthCard) return;
  const total = Array.isArray(state.sources) ? state.sources.length : 0;
  const healthy = Array.isArray(state.sources)
    ? state.sources.filter((s) => formatSourceStatus(s).className === 'status-ok').length
    : 0;
  const unhealthy = total - healthy;
  healthCard.querySelector('.label').textContent = `Healthy sources`;
  healthCard.querySelector('.value').textContent = `${healthy}/${total}`;
  // color hint via class toggles
  healthCard.classList.toggle('health', unhealthy === 0);
  healthCard.classList.toggle('status-warning', unhealthy > 0 && unhealthy <= Math.max(1, Math.floor(total * 0.2)));
  healthCard.classList.toggle('status-paused', unhealthy > Math.max(1, Math.floor(total * 0.2)));
}

// Render a small alerts banner for sources with warning/critical/paused states
function renderSourceAlerts(healthList) {
  const containerId = 'alertsPanel';
  let container = document.getElementById(containerId);
  if (!container) {
    container = document.createElement('div');
    container.id = containerId;
    container.className = 'alerts-panel';
    // insert before the stats grid so alerts are visible near the top
    const beforeEl = statsGrid || document.querySelector('#dashboardView');
    if (beforeEl && beforeEl.parentNode) {
      beforeEl.parentNode.insertBefore(container, beforeEl);
    } else if (dashboardView) {
      dashboardView.insertBefore(container, dashboardView.firstChild);
    }
  }

  if (!Array.isArray(healthList) || healthList.length === 0) {
    container.innerHTML = '';
    return;
  }

  const critical = healthList.filter((h) => h.status === 'critical');
  const warning = healthList.filter((h) => h.status === 'warning');
  const paused = healthList.filter((h) => h.status === 'paused');

  if (!critical.length && !warning.length && !paused.length) {
    container.innerHTML = '';
    return;
  }

  const parts = [];
  if (critical.length) parts.push(`<span class="alert-pill alert-critical">${critical.length} critical</span>`);
  if (warning.length) parts.push(`<span class="alert-pill alert-warning">${warning.length} warning</span>`);
  if (paused.length) parts.push(`<span class="alert-pill alert-paused">${paused.length} paused</span>`);

  const heading = `<div class="alerts-banner"><strong>Source health:</strong> ${parts.join(' ')} <button id="viewSourcesHealthBtn" class="secondary small-btn">View</button></div>`;
  container.innerHTML = heading;

  const viewBtn = document.getElementById('viewSourcesHealthBtn');
  if (viewBtn) {
    viewBtn.addEventListener('click', () => {
      // populate the sourceHealthModal with a compact list of affected sources
      const list = [...critical, ...warning, ...paused];
      const content = list
        .map((h) => `<div class="alert-source-row"><button type="button" class="link" data-source-id="${h.source_id}">${escapeHtml(h.name)}</button> <span class="muted">[${escapeHtml(h.status)}]</span></div>`)
        .join('');
      const modal = document.getElementById('sourceHealthModal');
      const contentEl = document.getElementById('sourceHealthContent');
      if (modal && contentEl) {
        contentEl.innerHTML = `<div class="alerts-list">${content}</div>`;
        modal.classList.remove('hidden');
        modal.setAttribute('aria-hidden', 'false');
        // attach handlers to each button that fetch the full health and show details
        Array.from(contentEl.querySelectorAll('[data-source-id]')).forEach((btn) => {
          btn.addEventListener('click', async (e) => {
            const sid = Number(btn.dataset.sourceId);
            try {
              const health = await api(`/sources/${sid}/health`);
              showSourceHealthModal(health);
            } catch (err) {
              alert(`Unable to fetch source health: ${err.message}`);
            }
          });
        });
      } else {
        alert(list.map((h) => `${h.name} (${h.status})`).join('\n'));
      }
    });
  }
}
function summarizeText(value) {
  const text = String(value ?? 'No summary available.').replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim() || 'No summary available.';
  return text.length > 170 ? `${text.slice(0, 170).trim()}...` : text;
}

function renderLead(items) {
  if (!leadGrid) return;
  if (!items || !items.length) {
    leadGrid.classList.add('hidden');
    return;
  }
  leadGrid.classList.remove('hidden');

  // Lead on the strongest story rather than whichever recent one happened to have a
  // picture; a photo still breaks ties, since the lead slot is mostly image.
  const leadScore = (item) => (item.relevance_score || 0) + (item.importance_score || 0)
    + (item.image_url ? 25 : 0);
  const leadIndex = items.reduce(
    (best, item, index) => (leadScore(item) > leadScore(items[best]) ? index : best),
    0,
  );
  const lead = items[leadIndex];
  const rest = items.filter((_, index) => index !== leadIndex).slice(0, 2);

  const when = (item) => (item.published_at
    ? new Date(item.published_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
    : 'Today');
  const tag = (item) => (Array.isArray(item.categories) && item.categories.length ? item.categories[0] : 'Defense');
  const meta = (item) => [getSourceName(item.source_id), when(item)].filter(Boolean).map(escapeHtml).join(' · ');

  const card = (item, className) => `
    <article class="lead-card ${className}" data-open-article="${item.id}" tabindex="0" role="button" aria-label="Open brief: ${escapeHtml(item.title)}">
      ${imageHtml(item.image_url, item.categories, 'lead-img')}
      <div class="lead-shade"></div>
      <div class="lead-text">
        <span class="story-tag lead-tag">${escapeHtml(tag(item))}</span>
        <h3>${escapeHtml(item.title)}</h3>
        ${className === 'lead-main' ? `<p>${escapeHtml(summarizeText(item.summary || item.description || ''))}</p>` : ''}
        <span class="lead-meta">${meta(item)}</span>
      </div>
    </article>
  `;

  leadGrid.innerHTML = card(lead, 'lead-main') + `<div class="lead-side">${rest.map((item) => card(item, 'lead-small')).join('')}</div>`;
}

function renderNewsList(container, items) {
  if (!items || !items.length) {
    container.innerHTML = '<div class="news-item empty"><p>No stories available yet.</p></div>';
    return;
  }

  container.innerHTML = items.map((item) => {
    const summary = item.summary || item.description || 'No summary available.';
    const primaryCategory = Array.isArray(item.categories) && item.categories.length ? item.categories[0] : 'Defense';
    const publishedValue = item.published_at ? new Date(item.published_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : 'Today';
    return `
      <article class="news-item">
        <div class="news-thumb">${imageHtml(item.image_url, item.categories)}</div>
        <div class="news-body">
          <div class="story-meta">
            <span class="story-tag">${escapeHtml(primaryCategory)}</span>
            <span>${escapeHtml(publishedValue)}</span>
          </div>
          <h3><a href="${escapeHtml(item.original_url || '#')}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a></h3>
          <p>${escapeHtml(summarizeText(summary))}</p>
        </div>
      </article>
    `;
  }).join('');
}

function renderTicker(items) {
  const ticker = document.getElementById('newsTicker');
  if (!ticker) return;

  if (!items.length) {
    ticker.classList.remove('scrolling');
    ticker.innerHTML = '<span class="ticker-item">Awaiting incoming reports…</span>';
    return;
  }

  const markup = items.map((item) => {
    const tag = Array.isArray(item.categories) && item.categories.length ? item.categories[0] : 'Defense';
    return `
      <span class="ticker-item">
        <span class="ticker-tag">${escapeHtml(tag)}</span>
        <a href="${escapeHtml(item.original_url || '#')}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a>
      </span>
    `;
  }).join('');

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  // The list is rendered twice so the scroll can loop seamlessly at -50%.
  ticker.innerHTML = reduceMotion ? markup : markup + markup.replace(/<a /g, '<a tabindex="-1" aria-hidden="true" ');
  ticker.classList.toggle('scrolling', !reduceMotion);
  ticker.style.setProperty('--ticker-duration', `${Math.max(30, items.length * 7)}s`);
}

function startClock() {
  const clock = document.getElementById('utcClock');
  const heroDate = document.getElementById('heroDate');

  const tick = () => {
    const now = new Date();
    if (clock) clock.textContent = now.toISOString().slice(11, 19);
    if (heroDate) {
      heroDate.textContent = now.toLocaleDateString(undefined, {
        weekday: 'short',
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      });
    }
  };

  tick();
  setInterval(tick, 1000);
}

function renderNewsletter(newsletter) {
  if (!newsletter || !newsletter.id) {
    newsletterPanel.innerHTML = '<p>No newsletter generated yet.</p>';
    return;
  }

  const items = (newsletter.articles || []).slice(0, 3).map((article) => `<li>${escapeHtml(article.title)}</li>`).join('');
  newsletterPanel.innerHTML = `
    <div class="newsletter-layout">
      <div>
        <h3>${escapeHtml(newsletter.title || 'Daily Defense Brief')}</h3>
        <div class="meta">${escapeHtml(newsletter.newsletter_date || 'Today')} • Newsletter available • PDF ready</div>
        <ul>${items || '<li>No article highlights available.</li>'}</ul>
      </div>
      <div class="newsletter-actions">
        <button type="button" class="secondary" data-download-pdf="${newsletter.id}">Download PDF</button>
      </div>
    </div>
  `;
}

async function downloadNewsletterPdf(newsletterId, button) {
  const label = button.textContent;
  button.disabled = true;
  button.textContent = 'Preparing...';

  try {
    // A plain link can't send the Bearer token, so fetch the file and save the blob.
    const response = await fetch(`${API_BASE}/newsletters/${newsletterId}/pdf`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (response.status === 401) {
      logout();
      return;
    }
    if (!response.ok) {
      throw new Error((await response.text()) || 'Request failed');
    }

    const disposition = response.headers.get('content-disposition') || '';
    const filename = /filename="?([^";]+)"?/.exec(disposition)?.[1] || `defense-brief-${newsletterId}.pdf`;
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  } catch (error) {
    alert(`Unable to download PDF: ${error.message}`);
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

newsletterPanel.addEventListener('click', (event) => {
  const button = event.target.closest('[data-download-pdf]');
  if (button) {
    downloadNewsletterPdf(Number(button.dataset.downloadPdf), button);
  }
});

function renderFilterSelects() {
  const fill = (select, items, label) => {
    if (!select) return;
    const options = [`<option value="">${label}</option>`];
    items.forEach((item) => {
      options.push(`<option value="${item.id}">${escapeHtml(item.name)}</option>`);
    });
    select.innerHTML = options.join('');
  };

  fill(categoryFilter, state.categories, 'All categories');
  fill(countryFilter, state.countries, 'All countries');
  fill(regionFilter, state.regions, 'All regions');
  fill(sourceFilter, state.sources, 'All sources');
  renderCategoryChips();
}

function formatSourceStatus(source) {
  const hasRecentSuccess = source.last_success_at && new Date(source.last_success_at).getTime() > Date.now() - 1000 * 60 * 60 * 24 * 7;
  const hasFailure = source.last_failure_at && new Date(source.last_failure_at).getTime() > Date.now() - 1000 * 60 * 60 * 24 * 7;

  if (!source.is_active) {
    return { label: 'Paused', className: 'status-paused' };
  }
  if (hasFailure && !hasRecentSuccess) {
    return { label: 'Check feed', className: 'status-warning' };
  }
  if (hasRecentSuccess) {
    return { label: 'Healthy', className: 'status-ok' };
  }
  return { label: 'Queued', className: 'status-neutral' };
}

function renderSourceTable(sources) {
  const sourceSummaryCount = document.getElementById('sourceSummaryCount');
  const sourceSummaryHealthy = document.getElementById('sourceSummaryHealthy');
  const sourceManagerHealthy = document.getElementById('sourceManagerHealthy');
  const totalSources = Array.isArray(sources) ? sources.length : 0;
  const healthySources = Array.isArray(sources)
    ? sources.filter((source) => formatSourceStatus(source).className === 'status-ok').length
    : 0;

  if (sourceSummaryCount) sourceSummaryCount.textContent = String(totalSources);
  if (sourceSummaryHealthy) sourceSummaryHealthy.textContent = String(healthySources);
  if (sourceManagerHealthy) sourceManagerHealthy.textContent = String(healthySources);

  if (!sources.length) {
    sourceTable.innerHTML = '<p class="empty-state">No sources tracked yet.</p>';
    return;
  }

  sourceTable.innerHTML = sources.map((source) => {
    const status = formatSourceStatus(source);
    const lastSuccess = source.last_success_at ? new Date(source.last_success_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : 'Never';
    const lastFailure = source.last_failure_at ? new Date(source.last_failure_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : null;
    const reliability = source.reliability_score ?? 0;
    return `
      <div class="source-row">
        <div class="source-main">
          <strong>${escapeHtml(source.name)}</strong>
          <small>${escapeHtml(source.source_type || 'RSS')} • ${escapeHtml(source.language || 'en')} • Last success: ${escapeHtml(lastSuccess)}${lastFailure ? ' • Last failure: ' + escapeHtml(lastFailure) : ''}</small>
        </div>
        <div class="source-meta">
          <span class="status-pill ${status.className}">${status.label}</span>
          <span class="reliability-tag">${reliability}%</span>
          <button type="button" class="secondary small-btn" title="View health details" data-source-health="${source.id}">Health</button>
        </div>
        <div class="source-actions">
          <button type="button" class="secondary small-btn" data-source-collect="${source.id}">Collect</button>
          <button type="button" class="secondary small-btn" data-edit-source="${source.id}">Edit</button>
          <button type="button" class="secondary small-btn danger-btn" data-delete-source="${source.id}">Delete</button>
        </div>
      </div>
    `;
  }).join('');
}

function renderPagination(total, page) {
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const el = document.getElementById('articlePagination');
  if (totalPages <= 1) { el.innerHTML = ''; return; }
  const prev = `<button class="pg-btn" data-pg="${page - 1}" ${page === 1 ? 'disabled' : ''}>&#8592; Prev</button>`;
  const next = `<button class="pg-btn" data-pg="${page + 1}" ${page === totalPages ? 'disabled' : ''}>Next &#8594;</button>`;
  const nums = Array.from({ length: totalPages }, (_, i) => i + 1)
    .map(n => `<button class="pg-btn pg-num ${n === page ? 'active' : ''}" data-pg="${n}">${n}</button>`)
    .join('');
  el.innerHTML = prev + nums + next;
}

const resultViewKey = 'defense-brief-results-view';

function applyResultView(view) {
  articleResults.classList.toggle('list-view', view === 'list');
  document.querySelectorAll('[data-results-view]').forEach((btn) => {
    const active = btn.dataset.resultsView === view;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-pressed', String(active));
  });
}

function setResultView(view) {
  try {
    localStorage.setItem(resultViewKey, view);
  } catch (error) {
    // Storage can be blocked; the choice then lasts only for this page load.
  }
  applyResultView(view);
}

function getResultView() {
  try {
    return localStorage.getItem(resultViewKey) === 'list' ? 'list' : 'cards';
  } catch (error) {
    return 'cards';
  }
}

function renderArticleResults(result) {
  const pageItems = Array.isArray(result.items) ? result.items : [];
  const total = result.total || 0;
  const page = result.page || 1;
  articleCountLabel.textContent = `${total} item${total === 1 ? '' : 's'}`;
  state.pageItems = pageItems;
  state.filteredTotal = total;
  renderSelectionBar();

  if (!total) {
    articleResults.innerHTML = '<div class="empty-state">No stories match the current filters.</div>';
    renderPagination(0, 1);
    return;
  }

  articleResults.innerHTML = pageItems.map((article) => {
    const categories = Array.isArray(article.categories) && article.categories.length ? article.categories : ['Defense'];
    const summary = article.summary || article.description || 'No summary available.';
    const published = article.published_at ? new Date(article.published_at).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    }) : 'Recent';

    const source = getSourceName(article.source_id);
    const selected = reportSelection.has(article.id);
    return `
      <article class="article-card${isPriority(article) ? ' priority' : ''}${selected ? ' selected' : ''}" data-open-article="${article.id}"
        tabindex="0" role="button" aria-label="Open brief: ${escapeHtml(article.title)}">
        <div class="article-card-image">
          <label class="select-box" title="Select for report">
            <input type="checkbox" data-select-article="${article.id}" ${selected ? 'checked' : ''}
              aria-label="Select for report: ${escapeHtml(article.title)}" />
          </label>
          ${imageHtml(article.image_url, categories)}
          ${source ? `<span class="card-source">${escapeHtml(source)}</span>` : ''}
        </div>
        <div class="article-card-body">
          <div class="chip-row">
            ${isPriority(article) ? '<span class="story-tag priority-tag">Priority</span>' : ''}
            ${categories.slice(0, 3).map((category) => `<span class="story-tag">${escapeHtml(category)}</span>`).join('')}
          </div>
          <h4>${escapeHtml(article.title)}</h4>
          <p>${escapeHtml(summarizeText(summary))}</p>
          <div class="article-card-footer">
            <span>${escapeHtml(published)}</span>
            <span class="card-cta">View brief</span>
          </div>
        </div>
      </article>
    `;
  }).join('');
  renderPagination(total, page);
}

// Stories the backend ranked as both strongly defense-related and consequential.
const PRIORITY_RELEVANCE = 70;
const PRIORITY_IMPORTANCE = 70;

function isPriority(article) {
  return (article.relevance_score || 0) >= PRIORITY_RELEVANCE
    && (article.importance_score || 0) >= PRIORITY_IMPORTANCE;
}

function parseKeyPoints(value) {
  if (!value) return [];
  return String(value)
    .split(/\n|\.|\;\s*/)
    .map((part) => part.trim())
    .filter(Boolean)
    .slice(0, 6);
}

// A summary that is only the headline again, often with the outlet's name appended
// ("Eleven sailors missing ... Reuters"), says nothing new.
function repeatsHeadline(summary, title) {
  const words = (text) => String(text || '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
  const head = words(title);
  return Boolean(head) && words(summary).startsWith(head) && words(summary).length - head.length <= 30;
}

// Feed descriptions are often just the opening of the body cut off with "...", so when the
// full text is present its first paragraph becomes the standfirst instead of the truncated teaser.
function articleText(article) {
  const paragraphs = String(article.content_excerpt || '')
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean);
  let summary = String(article.summary || article.description || '').trim();
  if (paragraphs.length && repeatsHeadline(summary, article.title)) summary = '';
  const teaser = summary.replace(/\s*(\[?(\.\.\.|…)\]?)\s*$/, '').slice(0, 100);
  if (paragraphs.length && (!summary || paragraphs.join(' ').startsWith(teaser))) {
    return { standfirst: paragraphs[0], paragraphs: paragraphs.slice(1) };
  }
  return { standfirst: summary, paragraphs };
}

// Why a story has no text to show: video and live pages have none; other publishers
// keep their full report on their own site.
function missingTextNote(url, sourceName) {
  const site = hostOf(url) || 'the publisher\'s site';
  if (/\/videos?\//i.test(url || '')) return `This is a video report. Watch it on ${site}.`;
  if (/\/(live|liveblog)\//i.test(url || '')) return `This is a live page that ${sourceName} keeps updating. Follow it on ${site}.`;
  return `${sourceName} shares only a summary of this story. The complete report is available on ${site}.`;
}

function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return '';
  }
}

function renderRelatedArticles(container, items) {
  if (!items.length) {
    container.closest('.article-related')?.remove();
    return;
  }
  container.innerHTML = items.map((item) => {
    const tag = Array.isArray(item.categories) && item.categories.length ? item.categories[0] : 'Defense';
    const when = item.published_at
      ? new Date(item.published_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
      : 'Recent';
    const meta = [getSourceName(item.source_id), when].filter(Boolean).map(escapeHtml).join(' · ');
    return `
      <button type="button" class="related-card" data-open-article="${item.id}">
        <span class="related-thumb">${imageHtml(item.image_url, item.categories)}</span>
        <span class="related-text">
          <span class="story-tag">${escapeHtml(tag)}</span>
          <strong>${escapeHtml(item.title)}</strong>
          <small>${meta}</small>
        </span>
      </button>
    `;
  }).join('');
}

function openArticleDetail(articleId) {
  api(`/articles/${articleId}`)
    .then((article) => {
      const categories = Array.isArray(article.categories) && article.categories.length ? article.categories : ['Defense'];
      const keyPoints = parseKeyPoints(article.key_points);
      const sourceName = getSourceName(article.source_id) || hostOf(article.original_url) || 'Source';
      const { standfirst: summary, paragraphs } = articleText(article);
      const published = article.published_at
        ? new Date(article.published_at).toLocaleString(undefined, { dateStyle: 'long', timeStyle: 'short' })
        : 'Recently published';
      const byline = [
        article.author ? `By <strong>${escapeHtml(article.author)}</strong>` : '',
        escapeHtml(sourceName),
        `<time datetime="${escapeHtml(article.published_at || '')}">${escapeHtml(published)}</time>`,
      ].filter(Boolean).join('<span aria-hidden="true">·</span>');
      const readTime = paragraphs.length
        ? Math.max(1, Math.round(`${summary} ${paragraphs.join(' ')}`.split(/\s+/).length / 230))
        : 0;

      articleDetailContent.innerHTML = `
        <div class="article-detail-hero">
          ${imageHtml(article.image_url, categories, 'hero-img')}
          <div class="article-detail-overlay">
            <p class="eyebrow">${escapeHtml(categories[0])}${readTime ? ` · ${readTime} min read` : ''}</p>
            <h3 id="articleDetailTitle">${escapeHtml(article.title)}</h3>
          </div>
        </div>
        <div class="article-detail-body">
          <div class="chip-row">
            ${categories.map((category) => `<span class="story-tag">${escapeHtml(category)}</span>`).join('')}
          </div>
          <p class="article-byline">${byline}</p>
          ${article.image_credit ? `<p class="photo-credit">Photo: ${escapeHtml(article.image_credit)}, from its report of the same story</p>` : ''}
          ${summary ? `<p class="article-standfirst">${escapeHtml(summary)}</p>` : ''}
          ${paragraphs.length
            ? `<div class="article-body-text">${paragraphs.map((p) => `<p>${escapeHtml(p)}</p>`).join('')}</div>`
            : `<div class="article-detail-section">
                <h4>Full report</h4>
                <p>${escapeHtml(missingTextNote(article.original_url, sourceName))}</p>
              </div>`}
          ${article.text_credit && paragraphs.length ? `<p class="photo-credit">Text: ${escapeHtml(article.text_credit)}, from its report of the same story</p>` : ''}
          ${keyPoints.length ? `
            <div class="article-detail-section">
              <h4>Key points</h4>
              <ul>${keyPoints.map((point) => `<li>${escapeHtml(point)}</li>`).join('')}</ul>
            </div>` : ''}
          <div class="article-detail-actions">
            <a href="${escapeHtml(article.original_url || '#')}" target="_blank" rel="noreferrer">
              <button type="button">Read on ${escapeHtml(sourceName)}</button>
            </a>
          </div>
          <section class="article-related" aria-labelledby="relatedHeading">
            <h4 id="relatedHeading">Related coverage</h4>
            <div class="related-grid" id="relatedArticles"><p class="muted">Loading related stories…</p></div>
          </section>
        </div>
      `;
      articleDetailModal.classList.remove('hidden');
      articleDetailModal.setAttribute('aria-hidden', 'false');
      articleDetailModal.querySelector('.modal-panel').scrollTop = 0;

      const relatedContainer = document.getElementById('relatedArticles');
      api(`/articles/${article.id}/related?limit=4`)
        .then((items) => renderRelatedArticles(relatedContainer, Array.isArray(items) ? items : []))
        .catch(() => relatedContainer.closest('.article-related')?.remove());
    })
    .catch((error) => {
      alert(`Unable to open article: ${error.message}`);
    });
}

articleDetailContent.addEventListener('click', (event) => {
  const card = event.target.closest('[data-open-article]');
  if (card) openArticleDetail(Number(card.dataset.openArticle));
});

function showSourceHealthModal(health) {
  const modal = document.getElementById('sourceHealthModal');
  const content = document.getElementById('sourceHealthContent');
  const publishedMeta = health.source_id ? `Source ID ${health.source_id}` : '';
  const errorId = `source-health-error-${health.source_id || Date.now()}`;

  modal.setAttribute('aria-labelledby', 'sourceHealthTitle');
  if (health.job_last_error) {
    modal.setAttribute('aria-describedby', errorId);
  } else {
    modal.removeAttribute('aria-describedby');
  }

  content.innerHTML = `
    <div class="article-detail-hero plain">
      <div class="article-detail-overlay">
        <p class="eyebrow">Source health</p>
        <h3 id="sourceHealthTitle">${escapeHtml(health.name || 'Unknown')}</h3>
      </div>
    </div>
    <div class="article-detail-body">
      <p class="article-detail-meta">${escapeHtml(publishedMeta)}</p>
      <div class="article-detail-section">
        <h4>Status</h4>
        <p>${health.is_active ? 'Active' : 'Paused'}</p>
      </div>
      <div class="article-detail-section">
        <h4>Last successful collection</h4>
        <p>${health.last_success_at ? escapeHtml(new Date(health.last_success_at).toLocaleString()) : 'Never'}</p>
      </div>
      <div class="article-detail-section">
        <h4>Last failure</h4>
        <p>${health.last_failure_at ? escapeHtml(new Date(health.last_failure_at).toLocaleString()) : 'None'}</p>
      </div>
      <div class="article-detail-section">
        <h4>Job last run</h4>
        <p>${health.job_last_run_at ? escapeHtml(new Date(health.job_last_run_at).toLocaleString()) : 'N/A'}</p>
      </div>
      <div class="article-detail-section">
        <h4>Job last success</h4>
        <p>${health.job_last_success_at ? escapeHtml(new Date(health.job_last_success_at).toLocaleString()) : 'N/A'}</p>
      </div>
      <div class="article-detail-section">
        <h4>Job last failure</h4>
        <p>${health.job_last_failure_at ? escapeHtml(new Date(health.job_last_failure_at).toLocaleString()) : 'N/A'}</p>
      </div>
      <div class="article-detail-section">
        <h4>Last job error</h4>
        <p id="${errorId}" class="health-error-text">${health.job_last_error ? escapeHtml(health.job_last_error) : 'None'}</p>
      </div>
    </div>
  `;

  // Close modal handler
  const backdrop = modal.querySelector('[data-close-health-modal]');
  const closeBtn = document.getElementById('closeHealthModalBtn');
  const onClose = () => closeSourceHealthModal();
  if (backdrop) backdrop.addEventListener('click', onClose);
  if (closeBtn) closeBtn.addEventListener('click', onClose);

  const statusText = health.is_active ? 'Active' : 'Paused';
  const statusAnnouncement = document.createElement('div');
  statusAnnouncement.className = 'sr-only';
  statusAnnouncement.setAttribute('role', 'status');
  statusAnnouncement.setAttribute('aria-live', 'polite');
  statusAnnouncement.textContent = `Source health for ${health.name || 'Unknown'}: ${statusText}. ${health.job_last_error ? `Last error: ${health.job_last_error}` : 'No recent errors.'}`;

  const existingStatus = modal.querySelector('.sr-only[role="status"]');
  if (existingStatus) existingStatus.remove();
  modal.appendChild(statusAnnouncement);

  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
  const firstFocusable = modal.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
  if (firstFocusable) firstFocusable.focus();
}

function closeSourceHealthModal() {
  const modal = document.getElementById('sourceHealthModal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
}

function closeArticleDetail() {
  articleDetailModal.classList.add('hidden');
  articleDetailModal.setAttribute('aria-hidden', 'true');
}

async function loadReferenceData() {
  try {
    const [countries, regions, categories, sources] = await Promise.all([
      api('/countries'),
      api('/regions'),
      api('/categories'),
      api('/sources'),
    ]);

    state.countries = countries;
    state.regions = regions;
    state.categories = categories;
    state.sources = sources;

    renderFilterSelects();
    renderSourceTable(sources);
    // update aggregate health card now that sources are loaded
    renderAggregateHealth();
  } catch (error) {
    sourceTable.innerHTML = `<p class="empty-state">Unable to load sources: ${error.message}</p>`;
  }
}

let articleRequestId = 0;

function renderCategoryChips() {
  const chips = [{ id: '', name: 'All' }, ...state.categories];
  categoryChips.innerHTML = chips.map((item) =>
    `<button type="button" class="chip" data-category="${escapeHtml(item.id)}">${escapeHtml(item.name)}</button>`
  ).join('');
  syncCategoryChips();
}

function syncCategoryChips() {
  categoryChips.querySelectorAll('[data-category]').forEach((btn) => {
    const active = btn.dataset.category === String(categoryFilter.value);
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-pressed', String(active));
  });
}

categoryChips.addEventListener('click', (event) => {
  const chip = event.target.closest('[data-category]');
  if (!chip) return;
  categoryFilter.value = chip.dataset.category;
  loadArticles();
});

// The filters as API query parameters, shared by the result list and "Select all".
function currentFilterParams() {
  const params = new URLSearchParams();
  const search = searchInput.value.trim();
  if (search) params.set('q', search);
  if (categoryFilter.value) params.set('category_id', categoryFilter.value);
  if (countryFilter.value) params.set('country_id', countryFilter.value);
  if (regionFilter.value) params.set('region_id', regionFilter.value);
  if (sourceFilter.value) params.set('source_id', sourceFilter.value);
  if (dateFromFilter.value) params.set('published_from', dateFromFilter.value);
  if (dateToFilter.value) params.set('published_to', dateToFilter.value);
  return params;
}

async function loadArticles(page = 1) {
  const requestId = ++articleRequestId;
  syncCategoryChips();
  const params = currentFilterParams();
  params.set('page', String(page));
  params.set('page_size', String(PAGE_SIZE));

  try {
    const result = await api(`/articles?${params}`);
    if (requestId !== articleRequestId) return;
    state.currentPage = result.page;
    renderArticleResults(result);
  } catch (error) {
    articleResults.innerHTML = `<div class="empty-state">Unable to load articles: ${escapeHtml(error.message)}</div>`;
  }
}

async function loadDashboard() {
  try {
    const dashboard = await api('/dashboard');
    renderStats(dashboard);
    renderNewsList(topDevelopments, dashboard.top_developments || dashboard.important_articles || []);
    renderLead(dashboard.latest_news || dashboard.latest_articles || []);

    const seen = new Set();
    const tickerItems = [
      ...(dashboard.top_developments || []),
      ...(dashboard.latest_news || []),
    ].filter((item) => item && !seen.has(item.id) && seen.add(item.id));
    renderTicker(tickerItems);

    const newsletter = dashboard.newsletter || {};
    if (newsletter.available) {
      const details = await api(`/newsletters/${newsletter.id}`);
      renderNewsletter(details);
    } else {
      newsletterPanel.innerHTML = '<p>No newsletter generated yet.</p>';
    }
  } catch (error) {
    newsletterPanel.innerHTML = `<p>Unable to load dashboard: ${error.message}</p>`;
  }
}

async function login(event) {
  event.preventDefault();
  const email = emailInput.value.trim();
  const password = passwordInput.value;

  try {
    const result = await api('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
      headers: { 'Content-Type': 'application/json' },
    });

    setToken(result.access_token);
  } catch (error) {
    const el = document.getElementById('loginError');
    el.textContent = 'Invalid email or password. Please try again.';
    el.classList.remove('hidden');
    loginForm.classList.add('shake');
    loginForm.addEventListener('animationend', () => loginForm.classList.remove('shake'), { once: true });
    return;
  }

  await startSession();
}

async function startSession() {
  let user = null;
  for (let attempt = 0; attempt < 5 && !user; attempt++) {
    try {
      user = await api('/auth/me');
    } catch (error) {
      // api() already logged out on 401, which clears the token.
      if (!getToken()) return;
      console.warn('Unable to load current user, retrying:', error);
      await new Promise((resolve) => setTimeout(resolve, 3000 * (attempt + 1)));
    }
  }

  if (!user) {
    authCard.classList.remove('hidden');
    const el = document.getElementById('loginError');
    el.textContent = 'Could not reach the server. Please try signing in again in a moment.';
    el.classList.remove('hidden');
    return;
  }

  setCurrentUser(user);
  document.getElementById('loginError').classList.add('hidden');
  authCard.classList.add('hidden');
  dashboardEl.classList.remove('hidden');
  logoutBtn.classList.remove('hidden');
  // Watchlist alert emails link to #watchlists.
  showView(window.location.hash === '#watchlists' ? 'watchlists' : 'dashboard');
  startWatchlistRefresh();
  await Promise.all([loadDashboard(), loadReferenceData(), loadArticles()]);

  if (isAdmin()) {
    startHealthRefresh();
    pollCollection();
  }
}

function startHealthRefresh() {
  stopHealthRefresh();
  // Periodic refresh for sources and aggregate health
  healthRefreshTimer = setInterval(async () => {
    try {
      await refreshSourcesAndHealth();
    } catch (e) {
      // ignore refresh errors — keep timer running
      console.warn('Health refresh failed', e);
    }
  }, HEALTH_REFRESH_INTERVAL_MS);
}

function stopHealthRefresh() {
  if (healthRefreshTimer) {
    clearInterval(healthRefreshTimer);
    healthRefreshTimer = null;
  }
}

async function generateBrief() {
  try {
    await api('/newsletters/generate', {
      method: 'POST',
      body: JSON.stringify({}),
    });
    await loadDashboard();
  } catch (error) {
    alert(`Unable to generate brief: ${error.message}`);
  }
}

async function submitSource(event) {
  event.preventDefault();

  const payload = {
    name: sourceName.value.trim(),
    website_url: sourceWebsite.value.trim(),
    feed_url: sourceFeed.value.trim() || null,
    source_type: sourceType.value.trim() || 'RSS',
    reliability_score: Number(sourceReliability.value || 85),
    collection_frequency: Number(sourceFrequency.value || 360),
    is_active: sourceActive.value === 'true',
  };

  try {
    const sourceId = sourceForm.dataset.editingSourceId;
    if (sourceId) {
      // The form has no country, region or language fields, so an edit leaves them as they are.
      await api(`/sources/${sourceId}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });
    } else {
      await api('/sources', {
        method: 'POST',
        body: JSON.stringify({ ...payload, country_id: null, region_id: null, language: 'en' }),
      });
    }

    resetSourceForm();
    await loadReferenceData();
    await loadArticles();
  } catch (error) {
    const actionLabel = sourceForm.dataset.editingSourceId ? 'update source' : 'add source';
    alert(`Unable to ${actionLabel}: ${error.message}`);
  }
}

// Collecting a single source runs through the same tracked collection as "Collect latest
// news", so its progress shows in the panel and it never overlaps another collection.
function collectSource(sourceId) {
  sourceView.scrollIntoView({ behavior: 'smooth', block: 'start' });
  return startCollection([sourceId]);
}

function formatClock(value) {
  return value ? new Date(value).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '';
}

function collectionHeadline(run) {
  const total = run.total_sources;
  const created = run.articles_created;
  const newArticles = `${created} new article${created === 1 ? '' : 's'}`;
  switch (run.status) {
    case 'in_progress':
      if (run.waiting) return 'Collection started. Waiting for a scheduled collection to finish first…';
      return run.current_source
        ? `Collecting ${run.current_source} · ${run.completed_sources} of ${total} sources done`
        : `Collection started · ${run.completed_sources} of ${total} sources done`;
    case 'completed':
      return total ? `Collection completed: ${newArticles} from ${total} source${total === 1 ? '' : 's'}.` : 'No active sources with a feed to collect.';
    case 'completed_with_errors':
      return `Completed with errors: ${run.failed_sources} of ${total} sources failed · ${newArticles}.`;
    case 'failed':
      return run.error || 'Collection failed.';
    default:
      return 'No collection has run yet. Click “Collect latest news” to fetch every active source.';
  }
}

function sourceRunDetail(item) {
  if (item.status === 'failed') return `<span class="run-error">${escapeHtml(item.error || 'Collection failed.')}</span>`;
  if (item.status === 'succeeded') {
    const counts = `${item.articles_created} new · ${item.articles_found} in feed`;
    return item.warning ? `${escapeHtml(counts)} · <span class="run-warning">${escapeHtml(item.warning)}</span>` : escapeHtml(counts);
  }
  return '';
}

function renderCollectionRun(run) {
  const status = COLLECTION_STATUS[run.status] || COLLECTION_STATUS.idle;
  const inProgress = run.status === 'in_progress';
  collectionStatusEl.className = `status-pill ${status.className}`;
  collectionStatusEl.textContent = status.label;
  collectAllBtn.disabled = inProgress;
  collectAllBtn.textContent = inProgress ? 'Collecting…' : 'Collect latest news';

  if (run.status === 'idle') {
    collectionProgressEl.innerHTML = `<p class="collection-summary">${escapeHtml(collectionHeadline(run))}</p>`;
    return;
  }

  const total = run.total_sources || 0;
  const percent = total ? Math.round((run.completed_sources / total) * 100) : 100;
  const timing = run.finished_at
    ? `Started ${formatClock(run.started_at)} · Finished ${formatClock(run.finished_at)}`
    : `Started ${formatClock(run.started_at)}`;
  const failedIds = (run.sources || []).filter((item) => item.status === 'failed').map((item) => item.source_id);

  collectionProgressEl.innerHTML = `
    <p class="collection-summary">${escapeHtml(collectionHeadline(run))}</p>
    <div class="collection-bar" role="progressbar" aria-label="Sources completed" aria-valuemin="0" aria-valuemax="${total}" aria-valuenow="${run.completed_sources}">
      <span style="width: ${percent}%"></span>
    </div>
    <dl class="collection-stats">
      <div><dt>Sources done</dt><dd>${run.completed_sources} / ${total}</dd></div>
      <div><dt>New articles</dt><dd>${run.articles_created}</dd></div>
      <div><dt>Failed</dt><dd class="${run.failed_sources ? 'is-failed' : ''}">${run.failed_sources}</dd></div>
      <div><dt>Time</dt><dd>${escapeHtml(timing)}</dd></div>
    </dl>
    ${(run.sources || []).length ? `<ul class="collection-sources">
      ${run.sources.map((item) => {
        const itemStatus = SOURCE_RUN_STATUS[item.status] || SOURCE_RUN_STATUS.pending;
        return `<li>
          <span class="status-pill ${itemStatus.className}">${itemStatus.label}</span>
          <strong>${escapeHtml(item.name)}</strong>
          <span class="collection-source-detail">${sourceRunDetail(item)}</span>
        </li>`;
      }).join('')}
    </ul>` : ''}
    ${!inProgress && failedIds.length
      ? `<button type="button" class="secondary" data-retry-sources="${failedIds.join(',')}">Retry failed source${failedIds.length === 1 ? '' : 's'} (${failedIds.length})</button>`
      : ''}
  `;
}

async function startCollection(sourceIds = null) {
  collectAllBtn.disabled = true;
  try {
    const run = await api('/sources/collection-runs', {
      method: 'POST',
      body: JSON.stringify(sourceIds ? { source_ids: sourceIds } : {}),
    });
    lastCollectionStatus = run.status;
    renderCollectionRun(run);
  } catch (error) {
    // Another collection is already running: show its progress instead of an error, but
    // say so when a single source was asked for, since it is not added to that run.
    if (!error.message.includes('already in progress')) {
      alert(`Unable to start collection: ${error.message}`);
    } else if (sourceIds) {
      alert('A collection is already in progress. Collect this source again once it finishes.');
    }
  }
  await pollCollection();
}

async function pollCollection() {
  clearTimeout(collectionPollTimer);
  collectionPollTimer = null;
  let run;
  try {
    run = await api('/sources/collection-runs/latest');
  } catch (error) {
    if (!getToken()) return;
    console.warn('Unable to load collection status', error);
    collectionPollTimer = setTimeout(pollCollection, COLLECTION_POLL_INTERVAL_MS * 3);
    return;
  }

  const wasRunning = lastCollectionStatus === 'in_progress';
  lastCollectionStatus = run.status;
  renderCollectionRun(run);

  if (run.status === 'in_progress') {
    collectionPollTimer = setTimeout(pollCollection, COLLECTION_POLL_INTERVAL_MS);
  } else if (wasRunning) {
    await Promise.all([refreshSourcesAndHealth(), loadDashboard(), loadArticles()]);
  }
}

function stopCollectionPolling() {
  clearTimeout(collectionPollTimer);
  collectionPollTimer = null;
  lastCollectionStatus = 'idle';
}

function resetFilters() {
  searchInput.value = '';
  categoryFilter.value = '';
  countryFilter.value = '';
  regionFilter.value = '';
  sourceFilter.value = '';
  dateFromFilter.value = '';
  dateToFilter.value = '';
  syncDateLimits();
  loadArticles();
}

// ---------------------------------------------------------------- report builder
//
// Readers tick stories across any filters and pages, then build a PDF from them. The
// selection lives in localStorage so it survives filter changes, paging and reloads; a
// Map keeps the order stories were ticked in, which is the "My order" starting point.

const MAX_REPORT_ARTICLES = 50;
const selectionKey = 'defense-brief-report-selection';
const reportSelection = new Map();

const selectionCountEl = document.getElementById('selectionCount');
const selectAllBtn = document.getElementById('selectAllBtn');
const deselectAllBtn = document.getElementById('deselectAllBtn');
const openReportBtn = document.getElementById('openReportBtn');
const reportModal = document.getElementById('reportModal');
const reportTitleInput = document.getElementById('reportTitle');
const reportDateFrom = document.getElementById('reportDateFrom');
const reportDateTo = document.getElementById('reportDateTo');
const reportOrder = document.getElementById('reportOrder');
const reportArticleList = document.getElementById('reportArticleList');
const reportSelectedCount = document.getElementById('reportSelectedCount');
const reportNote = document.getElementById('reportNote');
const previewReportBtn = document.getElementById('previewReportBtn');
const downloadReportBtn = document.getElementById('downloadReportBtn');
const reportPreviewFrame = document.getElementById('reportPreviewFrame');
const reportPreviewLink = document.getElementById('reportPreviewLink');
const reportPreviewEmpty = document.getElementById('reportPreviewEmpty');
const reportOptionInputs = {
  include_summary: document.getElementById('optSummary'),
  include_dates: document.getElementById('optDates'),
  include_sources: document.getElementById('optSources'),
  include_images: document.getElementById('optImages'),
  include_links: document.getElementById('optLinks'),
};
// The last PDF built, so Download right after Preview doesn't build it again.
let lastReport = null;

function selectionEntry(article) {
  return {
    id: article.id,
    title: article.title,
    source_id: article.source_id,
    published_at: article.published_at,
  };
}

function saveSelection() {
  try {
    localStorage.setItem(selectionKey, JSON.stringify([...reportSelection.values()]));
  } catch (error) {
    // Storage can be blocked; the selection then lasts only for this page load.
  }
}

function restoreSelection() {
  try {
    const saved = JSON.parse(localStorage.getItem(selectionKey) || '[]');
    if (Array.isArray(saved)) {
      saved.filter((item) => item && Number.isInteger(item.id)).forEach((item) => reportSelection.set(item.id, item));
    }
  } catch (error) {
    // A missing or unreadable selection just starts empty.
  }
}

function renderSelectionBar() {
  const count = reportSelection.size;
  selectionCountEl.textContent = String(count);
  openReportBtn.disabled = count === 0;
  selectAllBtn.textContent = state.filteredTotal ? `Select all ${state.filteredTotal}` : 'Select all';
  selectAllBtn.disabled = !state.filteredTotal;
  deselectAllBtn.disabled = count === 0;
}

function syncVisibleCheckboxes() {
  articleResults.querySelectorAll('[data-select-article]').forEach((checkbox) => {
    const selected = reportSelection.has(Number(checkbox.dataset.selectArticle));
    checkbox.checked = selected;
    checkbox.closest('.article-card')?.classList.toggle('selected', selected);
  });
}

// Every story matching the current filters, across all pages.
async function fetchFilteredSelection() {
  return api(`/articles/selection?${currentFilterParams()}`);
}

async function selectAllFiltered() {
  selectAllBtn.disabled = true;
  try {
    const result = await fetchFilteredSelection();
    result.items.forEach((item) => {
      if (!reportSelection.has(item.id)) reportSelection.set(item.id, selectionEntry(item));
    });
    saveSelection();
    syncVisibleCheckboxes();
  } catch (error) {
    alert(`Unable to select stories: ${error.message}`);
  } finally {
    renderSelectionBar();
  }
}

// "Deselect all" acts on the current filters, like "Select all"; with no filters set
// that is the whole selection.
async function deselectAllFiltered() {
  deselectAllBtn.disabled = true;
  try {
    if (currentFilterParams().toString()) {
      const result = await fetchFilteredSelection();
      result.items.forEach((item) => reportSelection.delete(item.id));
    } else {
      reportSelection.clear();
    }
    saveSelection();
    syncVisibleCheckboxes();
  } catch (error) {
    alert(`Unable to deselect stories: ${error.message}`);
  } finally {
    renderSelectionBar();
  }
}

function localDay(value) {
  // en-CA formats as YYYY-MM-DD, the value a date input expects.
  return value ? new Date(value).toLocaleDateString('en-CA') : '';
}

function publishedTime(item) {
  return item.published_at ? new Date(item.published_at).getTime() : null;
}

// The selection in the order the report will use.
function orderedSelection() {
  const items = [...reportSelection.values()];
  if (reportOrder.value === 'custom') return items;
  const direction = reportOrder.value === 'oldest' ? 1 : -1;
  return items.sort((a, b) => {
    const left = publishedTime(a);
    const right = publishedTime(b);
    if (left === null || right === null) return (left === null) - (right === null);
    return (left - right) * direction;
  });
}

function formatShortDate(value) {
  return value ? new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : 'Undated';
}

function renderReportList() {
  const items = orderedSelection();
  reportSelectedCount.textContent = `(${items.length})`;
  reportArticleList.innerHTML = items.map((item, index) => `
    <li class="report-item" data-report-id="${item.id}">
      <span class="report-item-num">${String(index + 1).padStart(2, '0')}</span>
      <div class="report-item-text">
        <strong>${escapeHtml(item.title)}</strong>
        <small>${escapeHtml([getSourceName(item.source_id), formatShortDate(item.published_at)].filter(Boolean).join(' · '))}</small>
      </div>
      <div class="report-item-actions">
        <button type="button" class="secondary icon-btn" data-move="-1" aria-label="Move up" ${index === 0 ? 'disabled' : ''}>&uarr;</button>
        <button type="button" class="secondary icon-btn" data-move="1" aria-label="Move down" ${index === items.length - 1 ? 'disabled' : ''}>&darr;</button>
        <button type="button" class="secondary icon-btn" data-remove aria-label="Remove from report">&times;</button>
      </div>
    </li>
  `).join('') || '<li class="report-empty">No articles selected. Tick stories in the results to add them.</li>';

  const over = items.length - MAX_REPORT_ARTICLES;
  reportNote.classList.toggle('hidden', over <= 0);
  reportNote.textContent = over > 0
    ? `A report can hold up to ${MAX_REPORT_ARTICLES} articles. Remove ${over} to continue.`
    : '';
  previewReportBtn.disabled = !items.length || over > 0;
  downloadReportBtn.disabled = !items.length || over > 0;
}

function moveReportItem(id, step) {
  const items = orderedSelection();
  const from = items.findIndex((item) => item.id === id);
  const to = from + step;
  if (from < 0 || to < 0 || to >= items.length) return;
  [items[from], items[to]] = [items[to], items[from]];
  // Reordering by hand turns the displayed order into "My order".
  reportSelection.clear();
  items.forEach((item) => reportSelection.set(item.id, item));
  reportOrder.value = 'custom';
  saveSelection();
  renderReportList();
  reportArticleList.querySelector(`[data-report-id="${id}"] [data-move="${step}"]`)?.focus();
}

// The report's dates follow the filter until the reader edits them; with no date
// filter they span the selected stories.
function fillReportDates() {
  const days = [...reportSelection.values()].map((item) => localDay(item.published_at)).filter(Boolean).sort();
  if (reportDateFrom.dataset.edited !== 'true') reportDateFrom.value = dateFromFilter.value || days[0] || '';
  if (reportDateTo.dataset.edited !== 'true') reportDateTo.value = dateToFilter.value || days[days.length - 1] || '';
}

function openReportBuilder() {
  fillReportDates();
  renderReportList();
  reportModal.classList.remove('hidden');
  reportModal.setAttribute('aria-hidden', 'false');
  reportTitleInput.focus();
}

function closeReportBuilder() {
  reportModal.classList.add('hidden');
  reportModal.setAttribute('aria-hidden', 'true');
  syncVisibleCheckboxes();
  renderSelectionBar();
  openReportBtn.focus();
}

function reportPayload() {
  const payload = {
    title: reportTitleInput.value.trim() || 'Daily Defence News Report',
    date_from: reportDateFrom.value || null,
    date_to: reportDateTo.value || null,
    article_ids: orderedSelection().map((item) => item.id),
    order: reportOrder.value,
  };
  Object.entries(reportOptionInputs).forEach(([key, input]) => { payload[key] = input.checked; });
  return payload;
}

async function buildReport(button) {
  const payload = reportPayload();
  if (payload.date_from && payload.date_to && payload.date_from > payload.date_to) {
    throw new Error('The start date must be on or before the end date.');
  }
  const key = JSON.stringify(payload);
  if (lastReport && lastReport.key === key) return lastReport;

  const label = button.textContent;
  button.disabled = true;
  button.textContent = 'Building...';
  try {
    // A plain link can't send the Bearer token, so fetch the file as a blob.
    const response = await fetch(`${API_BASE}/reports/pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
      body: key,
    });
    if (response.status === 401) {
      logout();
      throw new Error('Your session has expired. Please sign in again.');
    }
    if (!response.ok) {
      const text = await response.text();
      let message = text;
      try {
        const { detail } = JSON.parse(text);
        if (typeof detail === 'string') message = detail;
        else if (Array.isArray(detail) && detail[0]?.msg) message = detail[0].msg.replace(/^Value error, /, '');
      } catch {
        // Not JSON; show the raw text.
      }
      throw new Error(message || 'Request failed');
    }
    const disposition = response.headers.get('content-disposition') || '';
    const filename = /filename="?([^";]+)"?/.exec(disposition)?.[1] || 'defence-news-report.pdf';
    if (lastReport) URL.revokeObjectURL(lastReport.url);
    lastReport = { key, filename, url: URL.createObjectURL(await response.blob()) };
    return lastReport;
  } finally {
    button.textContent = label;
    renderReportList();
  }
}

async function previewReport() {
  try {
    const report = await buildReport(previewReportBtn);
    reportPreviewFrame.src = report.url;
    reportPreviewFrame.classList.remove('hidden');
    reportPreviewEmpty.classList.add('hidden');
    reportPreviewLink.href = report.url;
    reportPreviewLink.classList.remove('hidden');
  } catch (error) {
    alert(`Unable to preview the report: ${error.message}`);
  }
}

async function downloadReport() {
  try {
    const report = await buildReport(downloadReportBtn);
    const link = document.createElement('a');
    link.href = report.url;
    link.download = report.filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } catch (error) {
    alert(`Unable to download the report: ${error.message}`);
  }
}

restoreSelection();
renderSelectionBar();
selectAllBtn.addEventListener('click', selectAllFiltered);
deselectAllBtn.addEventListener('click', deselectAllFiltered);
openReportBtn.addEventListener('click', openReportBuilder);
document.getElementById('closeReportBtn').addEventListener('click', closeReportBuilder);
reportModal.addEventListener('click', (event) => {
  if (event.target.dataset.closeReport === 'true') closeReportBuilder();
});
reportModal.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') closeReportBuilder();
});
document.getElementById('clearSelectionBtn').addEventListener('click', () => {
  if (!reportSelection.size || !confirm('Remove all articles from this report?')) return;
  reportSelection.clear();
  saveSelection();
  renderReportList();
});
reportArticleList.addEventListener('click', (event) => {
  const row = event.target.closest('[data-report-id]');
  if (!row) return;
  const id = Number(row.dataset.reportId);
  const move = event.target.closest('[data-move]');
  if (move) {
    moveReportItem(id, Number(move.dataset.move));
  } else if (event.target.closest('[data-remove]')) {
    reportSelection.delete(id);
    saveSelection();
    renderReportList();
  }
});
reportOrder.addEventListener('change', renderReportList);
[reportDateFrom, reportDateTo].forEach((input) => input.addEventListener('input', () => {
  input.dataset.edited = 'true';
}));
// A filter change re-links the report dates to the filter.
[dateFromFilter, dateToFilter].forEach((input) => input.addEventListener('change', () => {
  delete reportDateFrom.dataset.edited;
  delete reportDateTo.dataset.edited;
}));
previewReportBtn.addEventListener('click', previewReport);
downloadReportBtn.addEventListener('click', downloadReport);

function resetSourceForm() {
  sourceForm.reset();
  sourceType.value = 'RSS';
  sourceReliability.value = 85;
  sourceFrequency.value = 360;
  sourceActive.value = 'true';
  delete sourceForm.dataset.editingSourceId;
  sourceForm.querySelector('button[type="submit"]').textContent = 'Add source';
}

function populateSourceForm(source) {
  sourceForm.dataset.editingSourceId = String(source.id);
  sourceName.value = source.name || '';
  sourceWebsite.value = source.website_url || '';
  sourceFeed.value = source.feed_url || '';
  sourceType.value = source.source_type || 'RSS';
  sourceReliability.value = source.reliability_score ?? 85;
  sourceFrequency.value = source.collection_frequency ?? 360;
  sourceActive.value = String(Boolean(source.is_active));
  sourceForm.querySelector('button[type="submit"]').textContent = 'Update source';
  sourceName.focus();
}

async function deleteSource(sourceId) {
  const confirmed = window.confirm('Delete this source from the dashboard?');
  if (!confirmed) return;

  try {
    await api(`/sources/${sourceId}`, { method: 'DELETE' });
    if (Number(sourceForm.dataset.editingSourceId) === sourceId) {
      resetSourceForm();
    }
    await loadReferenceData();
    await loadArticles();
  } catch (error) {
    alert(`Unable to delete source: ${error.message}`);
  }
}

function showView(viewName) {
  const known = ['dashboard', 'watchlists', 'sources'];
  const view = !known.includes(viewName) || (viewName === 'sources' && !isAdmin()) ? 'dashboard' : viewName;
  viewSwitcher.classList.toggle('hidden', !getToken());
  dashboardView.classList.toggle('hidden', view !== 'dashboard');
  sourceView.classList.toggle('hidden', view !== 'sources');
  watchlistView.classList.toggle('hidden', view !== 'watchlists');

  navTabs.forEach((tab) => {
    const active = tab.dataset.view === view;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-pressed', String(active));
  });
  if (view === 'watchlists' && getToken()) loadWatchlists();
}

function logout() {
  setToken(null);
  setCurrentUser(null);
  stopHealthRefresh();
  stopCollectionPolling();
  stopWatchlistRefresh();
  authCard.classList.remove('hidden');
  dashboardEl.classList.add('hidden');
  logoutBtn.classList.add('hidden');
  showView('dashboard');
  emailInput.focus();
}

document.addEventListener('click', (e) => {
  const btn = e.target.closest('.pg-btn');
  if (!btn || btn.disabled) return;
  loadArticles(parseInt(btn.dataset.pg, 10));
  document.querySelector('.command-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
});

document.getElementById('togglePassword').addEventListener('click', () => {
  const isPassword = passwordInput.type === 'password';
  passwordInput.type = isPassword ? 'text' : 'password';
  document.getElementById('togglePassword').textContent = isPassword ? '🙈' : '👁';
});
[emailInput, passwordInput].forEach(el => el.addEventListener('input', () => {
  document.getElementById('loginError').classList.add('hidden');
}));
loginForm.addEventListener('submit', login);
logoutBtn.addEventListener('click', logout);
generateBriefBtn.addEventListener('click', generateBrief);
sourceForm.addEventListener('submit', submitSource);
collectAllBtn.addEventListener('click', () => startCollection());
collectionProgressEl.addEventListener('click', (event) => {
  const retry = event.target.closest('[data-retry-sources]');
  if (retry) startCollection(retry.dataset.retrySources.split(',').map(Number));
});
resetFiltersBtn.addEventListener('click', resetFilters);
let searchDebounceTimer = null;
searchInput.addEventListener('input', () => {
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(() => loadArticles(), 300);
});
// Enter in the search box submits the form; search in place instead of reloading the page.
articleFilterForm.addEventListener('submit', (event) => {
  event.preventDefault();
  clearTimeout(searchDebounceTimer);
  loadArticles();
});
categoryFilter.addEventListener('change', () => loadArticles());
countryFilter.addEventListener('change', () => loadArticles());
regionFilter.addEventListener('change', () => loadArticles());
sourceFilter.addEventListener('change', () => loadArticles());
// Each date picker can't cross the other, so the range is always valid.
function syncDateLimits() {
  dateToFilter.min = dateFromFilter.value;
  dateFromFilter.max = dateToFilter.value;
}
[dateFromFilter, dateToFilter].forEach((input) => input.addEventListener('change', () => {
  syncDateLimits();
  loadArticles();
}));
closeModalBtn.addEventListener('click', closeArticleDetail);
articleDetailModal.addEventListener('click', (event) => {
  if (event.target.dataset.closeModal === 'true') {
    closeArticleDetail();
  }
});
sourceTable.addEventListener('click', (event) => {
  const collectButton = event.target.closest('[data-source-collect]');
  if (collectButton) {
    collectSource(Number(collectButton.dataset.sourceCollect));
    return;
  }

  const healthButton = event.target.closest('[data-source-health]');
  if (healthButton) {
    const sourceId = Number(healthButton.dataset.sourceHealth);
    api(`/sources/${sourceId}/health`)
      .then((health) => {
        const parts = [];
        parts.push(`Source: ${health.name} (ID ${health.source_id})`);
        parts.push(`Active: ${health.is_active ? 'Yes' : 'No'}`);
        if (health.last_success_at) parts.push(`Last successful collection: ${new Date(health.last_success_at).toLocaleString()}`);
        if (health.last_failure_at) parts.push(`Last failure: ${new Date(health.last_failure_at).toLocaleString()}`);
        if (health.job_last_run_at) parts.push(`Job last run: ${new Date(health.job_last_run_at).toLocaleString()}`);
        if (health.job_last_error) parts.push(`Last job error: ${health.job_last_error}`);
        alert(parts.join('\n'));
      })
      .catch((err) => {
        alert(`Unable to fetch health for source ${sourceId}: ${err.message}`);
      });
    return;
  }

  const editButton = event.target.closest('[data-edit-source]');
  if (editButton) {
    const source = state.sources.find((entry) => Number(entry.id) === Number(editButton.dataset.editSource));
    if (source) {
      populateSourceForm(source);
      showView('sources');
    }
    return;
  }

  const deleteButton = event.target.closest('[data-delete-source]');
  if (deleteButton) {
    deleteSource(Number(deleteButton.dataset.deleteSource));
  }
});

const clearNewsBtn = document.getElementById('clearNewsBtn');
if (clearNewsBtn) {
  clearNewsBtn.addEventListener('click', async () => {
    if (!confirm('Delete ALL articles and newsletters? This cannot be undone.')) return;
    clearNewsBtn.disabled = true;
    const orig = clearNewsBtn.textContent;
    clearNewsBtn.textContent = 'Clearing...';
    try {
      const data = await api('/articles', { method: 'DELETE' });
      alert(`Cleared ${data.deleted_articles} articles and ${data.deleted_newsletters} newsletters.`);
      await loadDashboard();
    } catch (e) {
      alert(`Failed to clear news: ${e.message || e}`);
    } finally {
      clearNewsBtn.textContent = orig;
      clearNewsBtn.disabled = false;
    }
  });
}

// Inline popover helper: shows brief health summary next to the clicked button
function showSourceHealthPopover(buttonEl, health) {
  // Remove any existing popover
  const existing = document.querySelector('.health-popover');
  if (existing) existing.remove();

  const pop = document.createElement('div');
  pop.className = 'health-popover';

  // accessible labeling
  const titleId = `health-pop-title-${Date.now()}`;
  const errorId = `health-pop-error-${Date.now()}`;
  pop.setAttribute('role', 'dialog');
  pop.setAttribute('aria-modal', 'false');
  pop.setAttribute('aria-labelledby', titleId);
  if (health.job_last_error) {
    pop.setAttribute('aria-describedby', errorId);
  }
  pop.tabIndex = -1;

  pop.innerHTML = `
    <div class="popover-arrow" aria-hidden="true"></div>
    <h4 id="${titleId}">${escapeHtml(health.name || 'Unknown')}</h4>
    <p><strong>Status:</strong> ${health.is_active ? 'Active' : 'Paused'}</p>
    <p><strong>Last success:</strong> ${health.last_success_at ? escapeHtml(new Date(health.last_success_at).toLocaleString()) : 'Never'}</p>
    <p><strong>Last failure:</strong> ${health.last_failure_at ? escapeHtml(new Date(health.last_failure_at).toLocaleString()) : 'None'}</p>
    ${health.job_last_error ? `<p id="${errorId}" class="health-error-text"><strong>Last error:</strong> ${escapeHtml(health.job_last_error)}</p>` : ''}
    <div class="actions">
      <button type="button" class="secondary small-btn" data-pop-details aria-label="View health details">Details</button>
      <button type="button" class="secondary small-btn" data-pop-collect aria-label="Collect now">Collect</button>
    </div>
  `;

  document.body.appendChild(pop);

  // Position helper with arrow alignment and boundary clamping
  function positionPopover() {
    const rect = buttonEl.getBoundingClientRect();
    pop.style.visibility = 'hidden';
    // allow layout to measure
    pop.style.top = '0px';
    pop.style.left = '0px';
    const popW = pop.offsetWidth;
    const popH = pop.offsetHeight;

    const margin = 8;
    let top = rect.bottom + window.scrollY + margin;
    let left = rect.left + window.scrollX + Math.round(rect.width / 2) - Math.round(popW / 2);

    // clamp left so popover stays within viewport with small padding
    left = Math.max(12 + window.scrollX, Math.min(left, window.scrollX + window.innerWidth - popW - 12));

    // if not enough space below, place above
    if (top + popH > window.scrollY + window.innerHeight - margin) {
      top = rect.top + window.scrollY - popH - margin;
      pop.classList.add('popover-above');
    } else {
      pop.classList.remove('popover-above');
    }

    pop.style.top = `${top}px`;
    pop.style.left = `${left}px`;
    pop.style.visibility = 'visible';

    // position arrow centered relative to button
    const arrow = pop.querySelector('.popover-arrow');
    if (arrow) {
      const arrowLeft = Math.min(popW - 20, Math.max(12, rect.left + window.scrollX + Math.round(rect.width / 2) - left - 8));
      arrow.style.left = `${arrowLeft}px`;
    }
  }

  positionPopover();

  // Reposition on scroll/resize
  const onScrollResize = () => positionPopover();
  window.addEventListener('scroll', onScrollResize, true);
  window.addEventListener('resize', onScrollResize);

  // Accessibility: focus management and keyboard trapping
  const focusableSelector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
  const focusable = Array.from(pop.querySelectorAll(focusableSelector));
  let lastFocused = document.activeElement;
  // mark trigger as expanded for assistive tech
  try { buttonEl.setAttribute('aria-expanded', 'true'); } catch (e) {}

  function focusFirst() {
    if (focusable.length) {
      focusable[0].focus();
    } else {
      pop.focus();
    }
  }

  function onKeyDown(e) {
    if (e.key === 'Escape') {
      e.preventDefault();
      cleanup();
      return;
    }
    if (e.key === 'Tab') {
      // simple focus trap
      if (focusable.length === 0) {
        e.preventDefault();
        return;
      }
      const currentIndex = focusable.indexOf(document.activeElement);
      if (e.shiftKey) {
        if (currentIndex === 0 || document.activeElement === pop) {
          e.preventDefault();
          focusable[focusable.length - 1].focus();
        }
      } else {
        if (currentIndex === focusable.length - 1) {
          e.preventDefault();
          focusable[0].focus();
        }
      }
    }
  }

  // Attach actions
  const detailsBtn = pop.querySelector('[data-pop-details]');
  const collectBtn = pop.querySelector('[data-pop-collect]');

  detailsBtn.addEventListener('click', () => {
    showSourceHealthModal(health);
    cleanup();
  });

  collectBtn.addEventListener('click', async (evt) => {
    const btn = evt.currentTarget;
    try {
      btn.disabled = true;
      btn.classList.add('loading');
      btn.dataset.origText = btn.textContent;
      btn.textContent = 'Collecting...';
      if (health.source_id) await collectSource(health.source_id);
    } catch (e) {
      // collectSource shows its own error alert
    } finally {
      btn.disabled = false;
      btn.classList.remove('loading');
      btn.textContent = btn.dataset.origText || 'Collect';
      cleanup();
    }
  });

  // Close popover when clicking outside
  function onDocClick(e) {
    if (!pop.contains(e.target) && e.target !== buttonEl) {
      cleanup();
    }
  }

  function cleanup() {
    try { buttonEl.setAttribute('aria-expanded', 'false'); } catch (e) {}
    pop.remove();
    window.removeEventListener('scroll', onScrollResize, true);
    window.removeEventListener('resize', onScrollResize);
    document.removeEventListener('click', onDocClick);
    document.removeEventListener('keydown', onKeyDown);
    // restore focus
    try { if (lastFocused && lastFocused.focus) lastFocused.focus(); } catch (e) {}
  }

  setTimeout(() => {
    document.addEventListener('click', onDocClick);
    document.addEventListener('keydown', onKeyDown);
    focusFirst();
  });
}


// capture-phase handler: fetch health and show popover next to button
document.addEventListener('click', (event) => {
  const healthBtn = event.target.closest('[data-source-health]');
  if (healthBtn) {
    event.stopPropagation();
    event.preventDefault();
    const sourceId = Number(healthBtn.dataset.sourceHealth);
    api(`/sources/${sourceId}/health`)
      .then((health) => showSourceHealthPopover(healthBtn, health))
      .catch((err) => alert(`Unable to fetch health for source ${sourceId}: ${err.message}`));
  }
}, true);

navTabs.forEach((tab) => {
  tab.addEventListener('click', () => showView(tab.dataset.view));
});

document.addEventListener('click', (event) => {
  const switchButton = event.target.closest('[data-view-switch]');
  if (switchButton) {
    showView(switchButton.dataset.viewSwitch);
  }
});

leadGrid.addEventListener('click', (event) => {
  const card = event.target.closest('[data-open-article]');
  if (card) openArticleDetail(Number(card.dataset.openArticle));
});
leadGrid.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  const card = event.target.closest('[data-open-article]');
  if (card) {
    event.preventDefault();
    openArticleDetail(Number(card.dataset.openArticle));
  }
});

articleResults.addEventListener('click', (event) => {
  // The selection checkbox sits on the card; ticking it must not open the story.
  if (event.target.closest('.select-box')) return;
  const card = event.target.closest('[data-open-article]');
  if (card) openArticleDetail(Number(card.dataset.openArticle));
});
articleResults.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  // Space on the checkbox ticks it; it shouldn't also open the story.
  if (event.target.closest('.select-box')) return;
  const card = event.target.closest('[data-open-article]');
  if (card) {
    event.preventDefault();
    openArticleDetail(Number(card.dataset.openArticle));
  }
});
articleResults.addEventListener('change', (event) => {
  const checkbox = event.target.closest('[data-select-article]');
  if (!checkbox) return;
  const id = Number(checkbox.dataset.selectArticle);
  const article = state.pageItems.find((item) => item.id === id);
  if (checkbox.checked && article) {
    reportSelection.set(id, selectionEntry(article));
  } else {
    reportSelection.delete(id);
  }
  checkbox.closest('.article-card')?.classList.toggle('selected', checkbox.checked);
  saveSelection();
  renderSelectionBar();
});

themeToggleBtn.addEventListener('click', () => {
  const nextTheme = document.body.dataset.theme === 'light' ? 'dark' : 'light';
  setTheme(nextTheme);
});

// ---------- Watchlists ----------

const watchlistView = document.getElementById('watchlistView');
const watchlistBadge = document.getElementById('watchlistBadge');
const watchlistList = document.getElementById('watchlistList');
const watchlistMatches = document.getElementById('watchlistMatches');
const watchlistForm = document.getElementById('watchlistForm');
const watchlistName = document.getElementById('watchlistName');
const watchlistTerms = document.getElementById('watchlistTerms');
const watchlistExclude = document.getElementById('watchlistExclude');
const watchlistEmail = document.getElementById('watchlistEmail');
const watchlistPreview = document.getElementById('watchlistPreview');
const watchlistFormError = document.getElementById('watchlistFormError');
const deleteWatchlistBtn = document.getElementById('deleteWatchlistBtn');
const saveWatchlistBtn = document.getElementById('saveWatchlistBtn');

const WATCHLIST_REFRESH_MS = 60000;
const WATCHLIST_PAGE_SIZE = 20;
const EMAIL_LABELS = { off: 'In-app alerts only', instant: 'Instant email', daily: 'Daily email digest' };
const watchlistState = { items: [], selectedId: null, editingId: null, emailAvailable: false, backfillDays: 7 };
let watchlistTimer = null;
let watchlistPreviewTimer = null;
let watchlistPreviewSeq = 0;

function splitTerms(value) {
  return String(value || '').split(/[,;\n]/).map((term) => term.trim()).filter(Boolean);
}

function storyCount(count) {
  return `${count} ${count === 1 ? 'story' : 'stories'}`;
}

function setWatchlistBadge(count) {
  watchlistBadge.textContent = !count ? '' : count > 99 ? '99+' : String(count);
  watchlistBadge.title = `${storyCount(count)} not yet read`;
  watchlistBadge.classList.toggle('hidden', !count);
}

async function refreshWatchlists() {
  const data = await api('/watchlists');
  watchlistState.items = Array.isArray(data.items) ? data.items : [];
  watchlistState.emailAvailable = Boolean(data.email_available);
  watchlistState.backfillDays = data.backfill_days || 7;
  setWatchlistBadge(data.unread_total || 0);
  return data;
}

function startWatchlistRefresh() {
  stopWatchlistRefresh();
  refreshWatchlists().catch(() => {});
  watchlistTimer = setInterval(async () => {
    try {
      await refreshWatchlists();
      if (!watchlistView.classList.contains('hidden')) renderWatchlistList();
    } catch {
      // The next tick tries again.
    }
  }, WATCHLIST_REFRESH_MS);
}

function stopWatchlistRefresh() {
  if (watchlistTimer) {
    clearInterval(watchlistTimer);
    watchlistTimer = null;
  }
  setWatchlistBadge(0);
}

async function loadWatchlists() {
  try {
    await refreshWatchlists();
  } catch (error) {
    watchlistList.innerHTML = `<p class="empty-state">Could not load your watchlists: ${escapeHtml(error.message)}</p>`;
    return;
  }
  renderWatchlistList();
  if (!watchlistForm.classList.contains('hidden')) return;
  if (!watchlistState.items.length) {
    openWatchlistForm(null);
    return;
  }
  const selected = watchlistState.items.find((item) => item.id === watchlistState.selectedId) || watchlistState.items[0];
  selectWatchlist(selected.id);
}

function renderWatchlistList() {
  const { items, selectedId } = watchlistState;
  if (!items.length) {
    watchlistList.innerHTML = '<p class="empty-state">No watchlists yet. Create one to start tracking a topic.</p>';
    return;
  }
  watchlistList.innerHTML = items.map((item) => `
    <button type="button" class="watchlist-item${item.id === selectedId ? ' active' : ''}${item.is_active ? '' : ' paused'}"
      data-watchlist="${item.id}" aria-pressed="${item.id === selectedId}">
      <span class="watchlist-item-head">
        <strong>${escapeHtml(item.name)}</strong>
        ${item.unread_count ? `<span class="nav-badge" title="${storyCount(item.unread_count)} not yet read">${item.unread_count}</span>` : ''}
      </span>
      <span class="watchlist-item-terms">${escapeHtml(item.terms.join(', '))}</span>
      <span class="watchlist-item-meta">${item.is_active ? EMAIL_LABELS[item.email_frequency] : 'Paused'} · ${storyCount(item.match_count)}</span>
    </button>
  `).join('');
}

function watchlistHeader(item) {
  const terms = item.terms.map((term) => `<span class="story-tag">${escapeHtml(term)}</span>`).join('');
  const excluded = item.exclude_terms.map((term) => `<span class="story-tag exclude-tag">not ${escapeHtml(term)}</span>`).join('');
  return `
    <header class="watchlist-head">
      <div>
        <p class="eyebrow">${item.is_active ? escapeHtml(EMAIL_LABELS[item.email_frequency]) : 'Paused: no new matches or emails'}</p>
        <h3>${escapeHtml(item.name)}</h3>
        <div class="chip-row">${terms}${excluded}</div>
      </div>
      <div class="watchlist-head-actions">
        <button type="button" class="secondary small-btn" data-watchlist-toggle>${item.is_active ? 'Pause' : 'Resume'}</button>
        <button type="button" class="secondary small-btn" data-watchlist-edit>Edit</button>
      </div>
    </header>
  `;
}

function watchlistStory(article) {
  const source = getSourceName(article.source_id);
  const when = article.published_at
    ? new Date(article.published_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : 'Recent';
  return `
    <article class="news-item watchlist-story${article.is_new ? ' is-new' : ''}" data-open-article="${article.id}"
      tabindex="0" role="button" aria-label="Open brief: ${escapeHtml(article.title)}">
      <div class="news-thumb">${imageHtml(article.image_url, article.categories)}</div>
      <div class="news-body">
        <div class="story-meta">
          ${article.is_new ? '<span class="story-tag new-tag">New</span>' : ''}
          ${source ? `<span>${escapeHtml(source)}</span>` : ''}
          <span>${escapeHtml(when)}</span>
        </div>
        <h3>${escapeHtml(article.title)}</h3>
        <p>${escapeHtml(summarizeText(article.summary || article.description))}</p>
        <p class="matched-terms">Mentions ${article.matched_terms.map((term) => `<strong>${escapeHtml(term)}</strong>`).join(', ')}</p>
      </div>
    </article>
  `;
}

async function selectWatchlist(id, page = 1) {
  watchlistState.selectedId = id;
  closeWatchlistForm();
  renderWatchlistList();
  const item = watchlistState.items.find((entry) => entry.id === id);
  if (!item) return;
  watchlistMatches.innerHTML = `${watchlistHeader(item)}<p class="muted">Loading stories…</p>`;

  let data;
  try {
    data = await api(`/watchlists/${id}/matches?page=${page}&page_size=${WATCHLIST_PAGE_SIZE}`);
  } catch (error) {
    watchlistMatches.innerHTML = `${watchlistHeader(item)}<p class="empty-state">Could not load stories: ${escapeHtml(error.message)}</p>`;
    return;
  }
  // The reader picked another watchlist while this one was loading.
  if (watchlistState.selectedId !== id) return;

  const pages = Math.ceil(data.total / WATCHLIST_PAGE_SIZE);
  const pager = pages > 1 ? `
    <div class="pagination">
      <button type="button" class="pg-btn" data-watchlist-page="${page - 1}" ${page === 1 ? 'disabled' : ''}>&#8592; Newer</button>
      <span class="muted">Page ${page} of ${pages}</span>
      <button type="button" class="pg-btn" data-watchlist-page="${page + 1}" ${page === pages ? 'disabled' : ''}>Older &#8594;</button>
    </div>` : '';
  watchlistMatches.innerHTML = `
    ${watchlistHeader(item)}
    <p class="watchlist-count">${storyCount(data.total)}</p>
    ${data.items.length
      ? `<div class="list-group watchlist-stories">${data.items.map(watchlistStory).join('')}</div>${pager}`
      : `<p class="empty-state">No stories have mentioned these terms in the last ${watchlistState.backfillDays} days. New ones will appear here as they are collected.</p>`}
  `;

  // Opening the watchlist reads its new stories; they keep their "New" tag until the next visit.
  if (item.unread_count) {
    api(`/watchlists/${id}/seen`, { method: 'POST' })
      .then(refreshWatchlists)
      .then(renderWatchlistList)
      .catch(() => {});
  }
}

function openWatchlistForm(item) {
  watchlistState.editingId = item ? item.id : null;
  document.getElementById('watchlistFormKicker').textContent = item ? 'Edit watchlist' : 'New watchlist';
  document.getElementById('watchlistFormTitle').textContent = item ? item.name : 'What do you want to follow?';
  watchlistName.value = item ? item.name : '';
  watchlistTerms.value = item ? item.terms.join(', ') : '';
  watchlistExclude.value = item ? item.exclude_terms.join(', ') : '';
  watchlistEmail.value = item ? item.email_frequency : 'off';
  deleteWatchlistBtn.classList.toggle('hidden', !item);
  document.getElementById('watchlistEmailNote').classList.toggle('hidden', watchlistState.emailAvailable);
  watchlistFormError.classList.add('hidden');
  watchlistForm.classList.remove('hidden');
  watchlistMatches.classList.add('hidden');
  updateWatchlistPreview();
  watchlistName.focus();
}

function closeWatchlistForm() {
  watchlistForm.classList.add('hidden');
  watchlistMatches.classList.remove('hidden');
  watchlistState.editingId = null;
  clearTimeout(watchlistPreviewTimer);
  watchlistPreviewSeq += 1;
}

function showWatchlistError(message) {
  watchlistFormError.textContent = message;
  watchlistFormError.classList.remove('hidden');
}

function updateWatchlistPreview() {
  clearTimeout(watchlistPreviewTimer);
  const terms = splitTerms(watchlistTerms.value);
  if (!terms.length) {
    watchlistPreview.innerHTML = '';
    return;
  }
  watchlistPreview.innerHTML = '<p class="muted">Checking recent stories…</p>';
  const seq = ++watchlistPreviewSeq;
  watchlistPreviewTimer = setTimeout(async () => {
    try {
      const data = await api('/watchlists/preview', {
        method: 'POST',
        body: JSON.stringify({ terms, exclude_terms: splitTerms(watchlistExclude.value) }),
      });
      if (seq !== watchlistPreviewSeq) return;
      watchlistPreview.innerHTML = `
        <p><strong>${storyCount(data.total)}</strong> from the last ${data.days} days ${data.total === 1 ? 'matches' : 'match'}.</p>
        ${data.items.length ? `<ul>${data.items.map((story) => `<li>${escapeHtml(story.title)}</li>`).join('')}</ul>` : ''}
      `;
    } catch (error) {
      if (seq === watchlistPreviewSeq) watchlistPreview.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
    }
  }, 400);
}

watchlistTerms.addEventListener('input', updateWatchlistPreview);
watchlistExclude.addEventListener('input', updateWatchlistPreview);
watchlistForm.addEventListener('input', () => watchlistFormError.classList.add('hidden'));

watchlistForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const body = {
    name: watchlistName.value.trim(),
    terms: splitTerms(watchlistTerms.value),
    exclude_terms: splitTerms(watchlistExclude.value),
    email_frequency: watchlistEmail.value,
  };
  if (!body.name) return showWatchlistError('Give the watchlist a name.');
  if (!body.terms.length) return showWatchlistError('Add at least one word or phrase to watch for.');

  const editingId = watchlistState.editingId;
  saveWatchlistBtn.disabled = true;
  try {
    const saved = await api(editingId ? `/watchlists/${editingId}` : '/watchlists', {
      method: editingId ? 'PATCH' : 'POST',
      body: JSON.stringify(body),
    });
    await refreshWatchlists();
    selectWatchlist(saved.id);
  } catch (error) {
    showWatchlistError(error.message);
  } finally {
    saveWatchlistBtn.disabled = false;
  }
});

document.getElementById('cancelWatchlistBtn').addEventListener('click', () => {
  closeWatchlistForm();
  const fallback = watchlistState.items.find((item) => item.id === watchlistState.selectedId) || watchlistState.items[0];
  if (fallback) selectWatchlist(fallback.id);
  else watchlistMatches.innerHTML = '<p class="empty-state">Create a watchlist to start tracking a topic.</p>';
});

deleteWatchlistBtn.addEventListener('click', async () => {
  const id = watchlistState.editingId;
  const item = watchlistState.items.find((entry) => entry.id === id);
  if (!item || !confirm(`Delete the watchlist "${item.name}"? Its alerts will stop.`)) return;
  try {
    await api(`/watchlists/${id}`, { method: 'DELETE' });
    watchlistState.selectedId = null;
    closeWatchlistForm();
    await loadWatchlists();
  } catch (error) {
    showWatchlistError(error.message);
  }
});

document.getElementById('newWatchlistBtn').addEventListener('click', () => openWatchlistForm(null));

watchlistList.addEventListener('click', (event) => {
  const button = event.target.closest('[data-watchlist]');
  if (button) selectWatchlist(Number(button.dataset.watchlist));
});

watchlistMatches.addEventListener('click', async (event) => {
  const item = watchlistState.items.find((entry) => entry.id === watchlistState.selectedId);
  if (event.target.closest('[data-watchlist-edit]') && item) {
    openWatchlistForm(item);
    return;
  }
  const toggle = event.target.closest('[data-watchlist-toggle]');
  if (toggle && item) {
    toggle.disabled = true;
    try {
      await api(`/watchlists/${item.id}`, { method: 'PATCH', body: JSON.stringify({ is_active: !item.is_active }) });
      await refreshWatchlists();
      selectWatchlist(item.id);
    } catch (error) {
      toggle.disabled = false;
      alert(`Unable to update the watchlist: ${error.message}`);
    }
    return;
  }
  const pageButton = event.target.closest('[data-watchlist-page]');
  if (pageButton && !pageButton.disabled && item) {
    await selectWatchlist(item.id, Number(pageButton.dataset.watchlistPage));
    watchlistMatches.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }
  const story = event.target.closest('[data-open-article]');
  if (story) openArticleDetail(Number(story.dataset.openArticle));
});

watchlistMatches.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  const story = event.target.closest('[data-open-article]');
  if (story) {
    event.preventDefault();
    openArticleDetail(Number(story.dataset.openArticle));
  }
});

setTheme(getTheme());
applyResultView(getResultView());
document.querySelector('.results-header-controls').addEventListener('click', (event) => {
  const button = event.target.closest('[data-results-view]');
  if (button) setResultView(button.dataset.resultsView);
});
startClock();

showView('dashboard');

window.addEventListener('beforeunload', stopHealthRefresh);

if (getToken()) {
  startSession();
} else {
  authCard.classList.remove('hidden');
}

// Refresh helper used by the periodic timer and can be invoked manually
async function refreshSourcesAndHealth() {
  try {
    const sources = await api('/sources');
    state.sources = sources;
    renderSourceTable(sources);
    renderAggregateHealth();

    try {
      const healths = await api('/sources/health/all');
      renderSourceAlerts(healths);
    } catch (e) {
      console.warn('Unable to fetch sources health summary:', e);
    }
  } catch (err) {
    console.warn('Unable to refresh sources for health:', err);
  }
}
