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
const categoryFilter = document.getElementById('categoryFilter');
const countryFilter = document.getElementById('countryFilter');
const regionFilter = document.getElementById('regionFilter');
const sourceFilter = document.getElementById('sourceFilter');
const resetFiltersBtn = document.getElementById('resetFiltersBtn');
const articleCountLabel = document.getElementById('articleCountLabel');
const articleResults = document.getElementById('articleResults');
const sourceForm = document.getElementById('sourceForm');
const sourceTable = document.getElementById('sourceTable');
const triggerHealthBtn = document.getElementById('triggerHealthBtn');
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

const categoryImages = {
  Air: 'https://images.unsplash.com/photo-1517479149777-5f3b1511d5ad?auto=format&fit=crop&w=900&q=80',
  Naval: 'https://images.unsplash.com/photo-1578575437130-527eed3abbec?auto=format&fit=crop&w=900&q=80',
  Land: 'https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?auto=format&fit=crop&w=900&q=80',
  Cyber: 'https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=900&q=80',
  Space: 'https://images.unsplash.com/photo-1446776811953-b23d57bd21aa?auto=format&fit=crop&w=900&q=80',
  Drones: 'https://images.unsplash.com/photo-1527977966376-1c8408f9f108?auto=format&fit=crop&w=900&q=80',
  'Defense Technology': 'https://images.unsplash.com/photo-1550751827-4bd374c3f58b?auto=format&fit=crop&w=900&q=80',
  'Military Exercises': 'https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?auto=format&fit=crop&w=900&q=80',
  Procurement: 'https://images.unsplash.com/photo-1552664730-d307ca884978?auto=format&fit=crop&w=900&q=80',
  Geopolitics: 'https://images.unsplash.com/photo-1521295121783-8a321d551ad2?auto=format&fit=crop&w=900&q=80',
  Default: 'https://images.unsplash.com/photo-1534796636912-3b95b3ab5986?auto=format&fit=crop&w=900&q=80',
};

const HEALTH_REFRESH_INTERVAL_MS = 60000; // 60s
let healthRefreshTimer = null;

const PAGE_SIZE = 12;
const state = {
  user: null,
  countries: [],
  regions: [],
  categories: [],
  sources: [],
  articles: [],
  currentPage: 1,
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

function getCategoryImage(categories) {
  const category = Array.isArray(categories) && categories.length ? categories[0] : 'Default';
  return categoryImages[category] || categoryImages.Default;
}

function imageHtml(url, categories, className = '') {
  const fallback = getCategoryImage(categories);
  const src = url || fallback;
  return `<img class="${className}" src="${escapeHtml(src)}" data-fallback="${escapeHtml(fallback)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">`;
}

// Swap a broken picture for its category photo once, then fall back to the placeholder tint.
document.addEventListener('error', (event) => {
  const img = event.target;
  if (!(img instanceof HTMLImageElement)) return;
  if (img.dataset.fallback && img.getAttribute('src') !== img.dataset.fallback) {
    img.src = img.dataset.fallback;
    img.dataset.fallback = '';
  } else {
    img.classList.add('img-failed');
  }
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
    throw new Error(errorText || 'Request failed');
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

  const preferred = items.findIndex((item) => item.image_url);
  const leadIndex = preferred >= 0 ? preferred : 0;
  const lead = items[leadIndex];
  const rest = items.filter((_, index) => index !== leadIndex).slice(0, 3);

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

function renderArticleResults(items) {
  const cleanItems = Array.isArray(items) ? items : [];
  const total = cleanItems.length;
  const page = state.currentPage;
  const start = (page - 1) * PAGE_SIZE;
  const pageItems = cleanItems.slice(start, start + PAGE_SIZE);
  articleCountLabel.textContent = `${total} item${total === 1 ? '' : 's'}`;

  if (!cleanItems.length) {
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

    return `
      <article class="article-card" data-article-id="${article.id}">
        <div class="article-card-image">
          ${imageHtml(article.image_url, categories)}
          ${getSourceName(article.source_id) ? `<span class="card-source">${escapeHtml(getSourceName(article.source_id))}</span>` : ''}
        </div>
        <div class="article-card-body">
          <div class="chip-row">
            ${categories.slice(0, 3).map((category) => `<span class="story-tag">${escapeHtml(category)}</span>`).join('')}
          </div>
          <h4>${escapeHtml(article.title)}</h4>
          <p>${escapeHtml(summarizeText(summary))}</p>
          <div class="article-card-footer">
            <span>${escapeHtml(published)}</span>
            <button type="button" class="secondary small-btn" data-open-article="${article.id}">View brief</button>
          </div>
        </div>
      </article>
    `;
  }).join('');
  renderPagination(total, page);
}

function parseKeyPoints(value) {
  if (!value) return [];
  return String(value)
    .split(/\n|\.|\;\s*/)
    .map((part) => part.trim())
    .filter(Boolean)
    .slice(0, 6);
}

// Feed descriptions are often just the opening of the body cut off with "...", so when the
// full text is present its first paragraph becomes the standfirst instead of the truncated teaser.
function articleText(article) {
  const paragraphs = String(article.content_excerpt || '')
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean);
  const summary = String(article.summary || article.description || '').trim();
  const teaser = summary.replace(/\s*(\[?(\.\.\.|…)\]?)\s*$/, '').slice(0, 100);
  if (paragraphs.length && (!summary || paragraphs.join(' ').startsWith(teaser))) {
    return { standfirst: paragraphs[0], paragraphs: paragraphs.slice(1) };
  }
  return { standfirst: summary, paragraphs };
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
          ${summary ? `<p class="article-standfirst">${escapeHtml(summary)}</p>` : ''}
          ${paragraphs.length
            ? `<div class="article-body-text">${paragraphs.map((p) => `<p>${escapeHtml(p)}</p>`).join('')}</div>`
            : `<div class="article-detail-section">
                <h4>Full report</h4>
                <p>${escapeHtml(sourceName)} shares only a summary of this story in its feed. The complete report is available on ${escapeHtml(hostOf(article.original_url) || 'the publisher\'s site')}.</p>
              </div>`}
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

async function loadArticles() {
  try {
    const response = await api('/articles?page_size=100');
    const searchValue = searchInput.value.trim().toLowerCase();
    const hasCategory = categoryFilter.value;
    const hasCountry = countryFilter.value;
    const hasRegion = regionFilter.value;
    const hasSource = sourceFilter.value;

    const filtered = (Array.isArray(response) ? response : []).filter((article) => {
      const articleText = [article.title, article.summary, article.description, (article.categories || []).join(' ')]
        .join(' ')
        .toLowerCase();
      const matchesSearch = !searchValue || articleText.includes(searchValue);
      const matchesCategory = !hasCategory || (article.categories || []).includes(state.categories.find((item) => Number(item.id) === Number(hasCategory))?.name || '');
      const matchesCountry = !hasCountry || Number(article.country_id) === Number(hasCountry);
      const matchesRegion = !hasRegion || Number(article.region_id) === Number(hasRegion);
      const matchesSource = !hasSource || Number(article.source_id) === Number(hasSource);

      return matchesSearch && matchesCategory && matchesCountry && matchesRegion && matchesSource;
    });

    state.articles = filtered;
    state.currentPage = 1;
    renderArticleResults(filtered);
  } catch (error) {
    articleResults.innerHTML = `<div class="empty-state">Unable to load articles: ${error.message}</div>`;
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
  try {
    setCurrentUser(await api('/auth/me'));
  } catch (error) {
    // api() already logged out on 401. For other failures keep the session
    // but leave the role unset, so admin controls stay hidden.
    if (!getToken()) return;
    console.warn('Unable to load current user:', error);
  }

  authCard.classList.add('hidden');
  dashboardEl.classList.remove('hidden');
  logoutBtn.classList.remove('hidden');
  showView('dashboard');
  await Promise.all([loadDashboard(), loadReferenceData(), loadArticles()]);

  if (isAdmin()) {
    startHealthRefresh();
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
    country_id: null,
    region_id: null,
    language: 'en',
  };

  try {
    const sourceId = sourceForm.dataset.editingSourceId;
    if (sourceId) {
      await api(`/sources/${sourceId}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });
    } else {
      await api('/sources', {
        method: 'POST',
        body: JSON.stringify(payload),
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

async function collectSource(sourceId) {
  try {
    await api(`/sources/${sourceId}/collect`, {
      method: 'POST',
    });
    await loadDashboard();
    await loadArticles();
  } catch (error) {
    alert(`Unable to collect source: ${error.message}`);
  }
}

function resetFilters() {
  searchInput.value = '';
  categoryFilter.value = '';
  countryFilter.value = '';
  regionFilter.value = '';
  sourceFilter.value = '';
  loadArticles();
}

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
  const isDashboard = viewName === 'dashboard' || !isAdmin();
  viewSwitcher.classList.toggle('hidden', !getToken());
  dashboardView.classList.toggle('hidden', !isDashboard);
  sourceView.classList.toggle('hidden', isDashboard);

  navTabs.forEach((tab) => {
    const active = tab.dataset.view === (isDashboard ? 'dashboard' : viewName);
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-pressed', String(active));
  });
}

function logout() {
  setToken(null);
  setCurrentUser(null);
  stopHealthRefresh();
  authCard.classList.remove('hidden');
  dashboardEl.classList.add('hidden');
  logoutBtn.classList.add('hidden');
  showView('dashboard');
  emailInput.focus();
}

document.addEventListener('click', (e) => {
  const btn = e.target.closest('.pg-btn');
  if (!btn || btn.disabled) return;
  state.currentPage = parseInt(btn.dataset.pg, 10);
  renderArticleResults(state.articles);
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
resetFiltersBtn.addEventListener('click', resetFilters);
searchInput.addEventListener('input', loadArticles);
categoryFilter.addEventListener('change', loadArticles);
countryFilter.addEventListener('change', loadArticles);
regionFilter.addEventListener('change', loadArticles);
sourceFilter.addEventListener('change', loadArticles);
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

// Manual trigger for health alerts
if (triggerHealthBtn) {
  triggerHealthBtn.addEventListener('click', async () => {
    try {
      triggerHealthBtn.disabled = true;
      const orig = triggerHealthBtn.textContent;
      triggerHealthBtn.textContent = 'Checking...';
      const result = await api('/sources/health/trigger', { method: 'POST' });

      // Show in-app modal summary instead of alert()
      const modal = document.getElementById('sourceHealthModal');
      const content = document.getElementById('sourceHealthContent');
      content.innerHTML = `
        <div class="article-detail-hero plain">
          <div class="article-detail-overlay">
            <p class="eyebrow">Health check</p>
            <h3 id="sourceHealthTitle">Manual health alert results</h3>
          </div>
        </div>
        <div class="article-detail-body">
          <div class="article-detail-section">
            <h4>Summary</h4>
            <p>Total sources: <strong>${escapeHtml(String(result.total_sources ?? 0))}</strong></p>
            <p>Critical: <strong>${escapeHtml(String(result.critical_count ?? 0))}</strong> (threshold ${escapeHtml(String(result.threshold ?? '-'))})</p>
            <p>Email sent: <strong>${escapeHtml(String(result.sent ?? false))}</strong></p>
          </div>
          <div class="article-detail-section">
            <h4>Actions</h4>
            <div class="article-detail-actions">
              <button id="viewAffectedBtn" type="button" class="secondary">View affected sources</button>
            </div>
          </div>
        </div>
      `;

      // attach handler for viewing detailed affected sources
      const attachView = () => {
        const viewBtn = document.getElementById('viewAffectedBtn');
        if (!viewBtn) return;
        viewBtn.addEventListener('click', async () => {
          try {
            viewBtn.disabled = true;
            viewBtn.textContent = 'Loading...';
            const healths = await api('/sources/health/all');
            // group by status
            const groups = { critical: [], warning: [], paused: [], ok: [] };
            (Array.isArray(healths) ? healths : []).forEach((h) => {
              const s = h.status || 'ok';
              if (!groups[s]) groups[s] = [];
              groups[s].push(h);
            });

            const listHtml = Object.entries(groups).map(([status, items]) => {
              if (!items.length) return '';
              const title = status.charAt(0).toUpperCase() + status.slice(1);
              const rows = items.map((it) => `
                <div class="alert-source-row">
                  <strong>${escapeHtml(it.name || 'Unknown')}</strong>
                  <div class="alert-pill alert-${escapeHtml(status)}">${escapeHtml(status)}</div>
                  <div class="alert-meta">Last success: ${it.last_success_at ? escapeHtml(new Date(it.last_success_at).toLocaleString()) : 'Never'}</div>
                </div>
              `).join('');
              return `<div class="alerts-group"><h4>${escapeHtml(title)} (${items.length})</h4>${rows}</div>`;
            }).join('');

            content.innerHTML = `
              <div class="article-detail-hero plain">
                <div class="article-detail-overlay">
                  <p class="eyebrow">Affected sources</p>
                  <h3 id="sourceHealthTitle">Health details</h3>
                </div>
              </div>
              <div class="article-detail-body">
                ${listHtml || '<p>No affected sources found.</p>'}
                <div style="margin-top:12px;" class="article-detail-actions"><button id="closeHealthFromSummary" type="button" class="secondary">Close</button></div>
              </div>
            `;

            const closeBtn = document.getElementById('closeHealthFromSummary');
            if (closeBtn) closeBtn.addEventListener('click', () => closeSourceHealthModal());
          } catch (err) {
            alert(`Unable to load affected sources: ${err.message || err}`);
          } finally {
            try { viewBtn.disabled = false; viewBtn.textContent = 'View affected sources'; } catch (e) {}
          }
        });
      };

      modal.classList.remove('hidden');
      modal.setAttribute('aria-hidden', 'false');
      // attach after showing so the element exists
      attachView();

      // refresh UI health state in background
      await refreshSourcesAndHealth();

      triggerHealthBtn.textContent = orig;
    } catch (e) {
      alert(`Failed to trigger health alert: ${e.message || e}`);
    } finally {
      try { triggerHealthBtn.disabled = false; } catch (e) {}
    }
  });
}

const clearNewsBtn = document.getElementById('clearNewsBtn');
if (clearNewsBtn) {
  clearNewsBtn.addEventListener('click', async () => {
    if (!confirm('Delete ALL articles and newsletters? This cannot be undone.')) return;
    clearNewsBtn.disabled = true;
    const orig = clearNewsBtn.textContent;
    clearNewsBtn.textContent = 'Clearing...';
    try {
      const res = await apiFetch('/articles', { method: 'DELETE' });
      const data = await res.json();
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
  const button = event.target.closest('[data-open-article]');
  if (button) {
    openArticleDetail(Number(button.dataset.openArticle));
  }
});

themeToggleBtn.addEventListener('click', () => {
  const nextTheme = document.body.dataset.theme === 'light' ? 'dark' : 'light';
  setTheme(nextTheme);
});

setTheme(getTheme());
startClock();

showView('dashboard');

window.addEventListener('beforeunload', stopHealthRefresh);

if (getToken()) {
  startSession();
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
