// LeadHunter B2B — Telegram Mini App Frontend Logic (Production Edition)
'use strict';

const tg = window.Telegram?.WebApp;
if (tg) {
  try {
    tg.ready();
    tg.expand();
    tg.setHeaderColor('#030303');
    tg.setBackgroundColor('#030303');
  } catch (e) {
    console.warn('Telegram WebApp init error', e);
  }
}

// Global App State
const state = {
  user: {
    id: tg?.initDataUnsafe?.user?.id || 1795524760,
    first_name: tg?.initDataUnsafe?.user?.first_name || 'Александр',
    username: tg?.initDataUnsafe?.user?.username || '',
  },
  spheres: [],
  selectedSphereId: 'food',
  selectedCategoryName: 'Кафе и кофейни',
  searchResults: [],
  filteredResults: [],
  resultsFilter: 'all',
  resultsSearchText: '',
  resultsSort: 'default',
  currentCity: 'Москва',
  crmLeads: [],
  crmFilter: 'all',
  freelancerName: '',
  googleApiKey: '',
  activeLead: null,
  activePitches: { hook: '', expert: '', short: '' },
  activePitchStyle: 'hook',
  activeRoi: null,
  roiAppended: false,
};

// UI Helpers
const $ = id => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const icon = (n, cls) => `<svg class="ic${cls ? ' ' + cls : ''}" aria-hidden="true"><use href="#i-${n}"/></svg>`;

// Safe link opener for Telegram WebApp and external browsers
function safeOpenLink(url, ev) {
  if (ev) {
    try {
      ev.preventDefault();
      ev.stopPropagation();
    } catch (e) {}
  }
  if (!url) return false;

  console.log('[SafeOpenLink] Opening:', url);

  // Phone number
  if (url.startsWith('tel:')) {
    window.location.href = url;
    return false;
  }

  // Telegram deep links
  if (url.startsWith('https://t.me/') || url.startsWith('tg://')) {
    if (window.Telegram && window.Telegram.WebApp && typeof window.Telegram.WebApp.openTelegramLink === 'function') {
      try {
        window.Telegram.WebApp.openTelegramLink(url);
        return false;
      } catch (err) {
        console.warn('openTelegramLink error:', err);
      }
    }
  }

  // Telegram WebApp external link opener
  if (window.Telegram && window.Telegram.WebApp && typeof window.Telegram.WebApp.openLink === 'function') {
    try {
      window.Telegram.WebApp.openLink(url, { try_instant_view: false });
      return false;
    } catch (err) {
      console.warn('Telegram.WebApp.openLink error:', err);
    }
  }

  // Standard fallback
  window.open(url, '_blank', 'noopener,noreferrer');
  return false;
}
window.safeOpenLink = safeOpenLink;

function getMapUrls(item) {
  const name = item.name || '';
  const addr = item.address || state.currentCity || '';
  const query = [name, addr].filter(Boolean).join(' ').trim();
  const encodedQuery = encodeURIComponent(query || 'организация');

  // Yandex Maps (Native & 100% reliable in Russia/CIS, opens Yandex Maps app or web)
  const yandexUrl = item.yandex_maps_url || `https://yandex.ru/maps/?text=${encodedQuery}`;

  // 2GIS
  const dgisUrl = item.dgis_url || `https://2gis.ru/search/${encodedQuery}`;

  // Google Maps
  let googleUrl = item.google_maps_url || item.maps_url;
  if (!googleUrl || !googleUrl.startsWith('http')) {
    googleUrl = `https://maps.google.com/?q=${encodedQuery}`;
  }

  return { yandexUrl, googleUrl, dgisUrl };
}

const STAGE_COLORS = {
  new: '#8E8FA0',
  contacted: '#F2C94C',
  negotiation: '#38A0F0',
  won: '#6FD39A',
  lost: '#FF6B6B'
};

const STAGE_LABELS = {
  new: 'Новый лид',
  contacted: 'Написал',
  negotiation: 'В диалоге',
  won: 'Клиент',
  lost: 'Отказ'
};

// Haptic Feedback
function haptic(type = 'light') {
  try {
    if (!tg?.HapticFeedback) return;
    if (type === 'ok') tg.HapticFeedback.notificationOccurred('success');
    else if (type === 'err') tg.HapticFeedback.notificationOccurred('error');
    else if (type === 'sel') tg.HapticFeedback.selectionChanged();
    else tg.HapticFeedback.impactOccurred('light');
  } catch {}
}

// Toast Notification
function showToast(text, duration = 2400) {
  const t = $('toast');
  if (!t) return;
  t.textContent = text;
  t.classList.add('show');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => {
    t.classList.remove('show');
  }, duration);
}

// Clipboard Helper
function copyToClipboard(text, msg = 'Скопировано в буфер') {
  if (!text) return;
  let ok = false;
  try {
    const el = document.createElement('textarea');
    el.value = text;
    el.setAttribute('readonly', '');
    el.style.cssText = 'position:fixed;top:0;left:0;opacity:0;font-size:16px;';
    document.body.appendChild(el);
    el.focus();
    el.select();
    ok = document.execCommand('copy');
    document.body.removeChild(el);
  } catch {}

  if (!ok && navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => {
      haptic('ok');
      showToast(msg);
    }).catch(() => {
      showToast('Выделите текст пальцем для копирования');
    });
    return;
  }
  haptic(ok ? 'ok' : 'err');
  showToast(ok ? msg : 'Ошибка копирования');
}

// Channel Buttons Generator (Action Grid)
function makeChannelButtons(item) {
  let h = '';
  const { yandexUrl } = getMapUrls(item);

  if (item.whatsapp_url) {
    h += `<a href="${esc(item.whatsapp_url)}" target="_blank" rel="noopener noreferrer" class="cbtn ch-wa" aria-label="WhatsApp" onclick="return safeOpenLink(this.href, event);">${icon('wa')}</a>`;
  }
  if (item.telegram_url) {
    h += `<a href="${esc(item.telegram_url)}" target="_blank" rel="noopener noreferrer" class="cbtn ch-tg" aria-label="Telegram" onclick="return safeOpenLink(this.href, event);">${icon('tg')}</a>`;
  }
  if (item.instagram_url) {
    h += `<a href="${esc(item.instagram_url)}" target="_blank" rel="noopener noreferrer" class="cbtn ch-ig" aria-label="Instagram" onclick="return safeOpenLink(this.href, event);">${icon('ig')}</a>`;
  }
  if (item.phone) {
    h += `<a href="tel:${esc(item.phone_clean ? "+" + item.phone_clean : item.phone)}" class="cbtn ch-phone" aria-label="Позвонить" onclick="return safeOpenLink(this.href, event);">${icon('phone')}</a>`;
  }
  h += `<a href="${esc(yandexUrl)}" target="_blank" rel="noopener noreferrer" class="cbtn ch-globe" aria-label="Карты" onclick="return safeOpenLink(this.href, event);">${icon('pin')}</a>`;
  return h;
}

// Tab Switching
function switchTab(tabId) {
  haptic('sel');
  $$('.tab-pane').forEach(el => el.classList.remove('active'));
  $$('.rail-btn').forEach(el => {
    el.classList.remove('active');
    el.setAttribute('aria-selected', 'false');
  });

  const targetPane = $(tabId);
  if (targetPane) targetPane.classList.add('active');

  const navBtn = document.querySelector(`.rail-btn[data-tab="${tabId}"]`);
  if (navBtn) {
    navBtn.classList.add('active');
    navBtn.setAttribute('aria-selected', 'true');
  }

  // Reactive canvas page tone if bg.js exists
  if (window.RZGfx) {
    try {
      window.RZGfx.page(tabId === 'tab-crm' ? 'base' : tabId === 'tab-pitches' ? 'msg' : 'lead');
    } catch {}
  }

  if (tabId === 'tab-today') loadKpi();
  if (tabId === 'tab-crm') loadCrmLeads();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Application Initialization
async function initApp() {
  bindEvents();
  await loadSpheres();
  await loadProfile();
  await loadKpi();
  populateQuickCities();

  // Boot WebGL Canvas if available
  if (window.RZGfx) {
    try { window.RZGfx.page('lead'); } catch {}
  }
}

// Bind Global UI Events
function bindEvents() {
  // Navigation tabs
  $$('.rail-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Today tab quick jump
  $('btnGoToSearch')?.addEventListener('click', () => switchTab('tab-search'));

  // Back to search params
  $('btnBackToSearch')?.addEventListener('click', () => {
    haptic('light');
    $('searchParamsBox').style.display = 'block';
    $('resultsWrapper').style.display = 'none';
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  // Global search input in header
  $('globalSearchInput')?.addEventListener('input', e => {
    const q = e.target.value.toLowerCase().trim();
    state.resultsSearchText = q;
    if ($('tab-search').classList.contains('active') && state.searchResults.length > 0) {
      applyResultsFiltering();
    }
  });

  // Quick city chips
  $$('#quickCities .chip').forEach(chip => {
    chip.addEventListener('click', () => {
      haptic('sel');
      $$('#quickCities .chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      $('inputCity').value = chip.dataset.city;
    });
  });

  // Sphere select change
  $('selectSphere')?.addEventListener('change', e => {
    state.selectedSphereId = e.target.value;
    renderCategoryChips(state.selectedSphereId);
  });

  // Run Search Button
  $('btnRunSearch')?.addEventListener('click', runSearch);

  // Results Filter Chips
  $$('#tab-search .filters .fchip').forEach(chip => {
    chip.addEventListener('click', () => {
      haptic('sel');
      $$('#tab-search .filters .fchip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.resultsFilter = chip.dataset.filter;
      applyResultsFiltering();
    });
  });

  // CRM Status Tiles
  $$('#crmStageFilters .bltile').forEach(tile => {
    tile.addEventListener('click', () => {
      haptic('sel');
      $$('#crmStageFilters .bltile').forEach(t => t.classList.remove('on'));
      tile.classList.add('on');
      state.crmFilter = tile.dataset.stage;
      renderCrmLeads();
    });
  });

  // Pitch Style Selector Chips
  $$('#tab-pitches .filters .fchip[data-style]').forEach(chip => {
    chip.addEventListener('click', () => {
      haptic('sel');
      $$('#tab-pitches .filters .fchip[data-style]').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.activePitchStyle = chip.dataset.style;
      if (state.activePitches && state.activePitches[state.activePitchStyle]) {
        $('standalonePitchText').value = state.activePitches[state.activePitchStyle];
      }
    });
  });

  // Standalone Pitch Generator
  $('btnGeneratePitchStandalone')?.addEventListener('click', generateStandalonePitch);
  $('btnCopyPitchStandalone')?.addEventListener('click', () => {
    const text = $('standalonePitchText').value;
    copyToClipboard(text);
  });

  // Standalone Mockup Button
  $('btnShowMockup')?.addEventListener('click', () => {
    const name = $('inputStandaloneName').value || 'Заведение';
    const pitch = $('standalonePitchText').value;
    openMockupModal(name, pitch);
  });

  // Close Mockup Modal
  $('btnCloseMockup')?.addEventListener('click', () => {
    $('mockupModal').style.display = 'none';
  });

  // Drawer Close Button & Scrim Click
  $('btnDrawerClose')?.addEventListener('click', closeLeadDrawer);
  $('scrim')?.addEventListener('click', () => {
    closeLeadDrawer();
    closePickModal();
  });

  // Drawer Copy Pitch
  $('btnDrawerCopyDraft')?.addEventListener('click', () => {
    const text = $('drawerDraftText').value;
    copyToClipboard(text);
  });

  // Drawer Append ROI
  $('btnDrawerAppendRoi')?.addEventListener('click', () => {
    if (state.roiAppended || !state.activeRoi) return;
    const current = $('drawerDraftText').value;
    const roiLoss = `\n\nРасчет упущенной выгоды:\n• Потенциал заказов с сайта: ~${state.activeRoi.orders_per_month} заказов/мес\n• Упущенный оборот без сайта: ~${Number(state.activeRoi.lost_revenue_rub).toLocaleString('ru-RU')} ₽/мес`;
    $('drawerDraftText').value = current + roiLoss;
    state.roiAppended = true;
    $('btnDrawerAppendRoi').disabled = true;
    showToast('Расчет добавлен в черновик');
    haptic('ok');
  });

  // Drawer Open Mockup
  $('btnDrawerOpenMockup')?.addEventListener('click', () => {
    if (!state.activeLead) return;
    const pitch = $('drawerDraftText').value;
    openMockupModal(state.activeLead.name, pitch);
  });

  // Drawer Stage Switcher
  $('btnDrawerStagePick')?.addEventListener('click', () => {
    if (!state.activeLead) return;
    openStagePick(state.activeLead.id || state.activeLead.crm_id || null);
  });

  // Drawer Save to CRM
  $('btnDrawerSaveCrm')?.addEventListener('click', async () => {
    if (!state.activeLead) return;
    await saveLeadObjectToCrm(state.activeLead);
  });

  // Verify Google API Key
  $('btnVerifyKey')?.addEventListener('click', verifyGoogleKey);

  // Save Profile
  $('btnSaveProfile')?.addEventListener('click', saveProfile);

  // Sync button tap
  $('syncStatusBtn')?.addEventListener('click', async () => {
    haptic('light');
    $('syncStatusBtn').classList.add('busy');
    await loadKpi();
    if ($('tab-crm').classList.contains('active')) await loadCrmLeads();
    setTimeout(() => {
      $('syncStatusBtn').classList.remove('busy');
      showToast('Данные актуальны');
    }, 600);
  });
}

// Populate Quick Cities
function populateQuickCities() {
  const container = $('quickCities');
  if (!container) return;
  const cities = ['Москва', 'Санкт-Петербург', 'Казань', 'Краснодар', 'Алматы', 'Минск', 'Ташкент', 'Дубай'];
  container.innerHTML = cities.map((c, i) =>
    `<button type="button" class="chip${i === 0 ? ' active' : ''}" data-city="${esc(c)}">${esc(c)}</button>`
  ).join('');

  $$('#quickCities .chip').forEach(chip => {
    chip.addEventListener('click', () => {
      haptic('sel');
      $$('#quickCities .chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      $('inputCity').value = chip.dataset.city;
    });
  });
}

// Load Spheres
async function loadSpheres() {
  try {
    const res = await fetch('/api/spheres');
    const data = await res.json();
    if (data.ok && data.spheres) {
      state.spheres = data.spheres;
      populateSphereDropdowns();
      renderCategoryChips(state.selectedSphereId);
    }
  } catch (err) {
    console.error('Error loading spheres', err);
  }
}

// Populate Sphere Selects
function populateSphereDropdowns() {
  const opts = state.spheres.map(s => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join('');
  if ($('selectSphere')) $('selectSphere').innerHTML = opts;
  if ($('selectStandaloneSphere')) $('selectStandaloneSphere').innerHTML = opts;
}

// Render Horizontal Category Chips
function renderCategoryChips(sphereId) {
  const container = $('categoriesChips');
  if (!container) return;
  const currentSphere = state.spheres.find(s => s.id === sphereId);
  if (!currentSphere || !currentSphere.categories) {
    container.innerHTML = '';
    return;
  }

  let html = `<button type="button" class="fchip active" data-cat="__ALL__">Все категории</button>`;
  currentSphere.categories.forEach(cat => {
    html += `<button type="button" class="fchip" data-cat="${esc(cat)}">${esc(cat)}</button>`;
  });
  container.innerHTML = html;

  state.selectedCategoryName = '__ALL__';

  $$('#categoriesChips .fchip').forEach(chip => {
    chip.addEventListener('click', () => {
      haptic('sel');
      $$('#categoriesChips .fchip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.selectedCategoryName = chip.dataset.cat;
    });
  });
}

// Load KPI Data
async function loadKpi() {
  try {
    const res = await fetch(`/api/kpi?user_id=${state.user.id}`);
    const data = await res.json();
    if (data.ok) {
      if ($('kpiTotal')) $('kpiTotal').innerText = data.total || '0';
      if ($('kpiContacted')) $('kpiContacted').innerText = data.contacted || '0';
      if ($('kpiWon')) $('kpiWon').innerText = data.won || '0';

      const contacted = parseInt(data.contacted) || 0;
      const target = 20;
      const percent = Math.min(100, Math.round((contacted / target) * 100));

      if ($('goalBar')) $('goalBar').style.width = `${percent}%`;
      if ($('goalPercent')) {
        $('goalPercent').innerText = contacted >= target ? 'цель дня достигнута' : `до цели ${target - contacted}`;
      }
    }
  } catch (err) {
    console.error('Error loading KPI', err);
  }
}

// Execute Parallel High-Volume Search
async function runSearch() {
  const city = $('inputCity').value.trim();
  if (!city) {
    showToast('Укажите город для поиска');
    haptic('err');
    return;
  }

  state.currentCity = city;
  const depth = $('selectSearchDepth')?.value || 'deep';
  const onlyHot = $('toggleOnlyHot')?.checked || false;

  let query = state.selectedCategoryName === '__ALL__' ? '' : state.selectedCategoryName;

  haptic('light');
  $('btnRunSearch').setAttribute('aria-busy', 'true');
  $('btnRunSearch').disabled = true;
  $('btnRunSearch').innerHTML = `<span class="spin"></span><span>Сканирую город...</span>`;

  try {
    const res = await fetch('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: query,
        sphere_id: state.selectedSphereId,
        city: city,
        depth: depth,
        only_hot: onlyHot,
        user_id: state.user.id
      })
    });
    const data = await res.json();

    if (data.ok && data.places) {
      state.searchResults = data.places;
      $('searchParamsBox').style.display = 'none';
      $('resultsWrapper').style.display = 'block';

      applyResultsFiltering();
      haptic('ok');
      showToast(`Найдено ${data.places.length} заведений`);
    } else {
      showToast(data.error || 'Ничего не найдено');
      haptic('err');
    }
  } catch (err) {
    console.error(err);
    showToast('Ошибка при поиске');
    haptic('err');
  } finally {
    $('btnRunSearch').removeAttribute('aria-busy');
    $('btnRunSearch').disabled = false;
    $('btnRunSearch').innerHTML = `<svg class="ic"><use href="#i-search"/></svg><span>Найти заведения</span>`;
  }
}

// Apply Results Filtering
function applyResultsFiltering() {
  let list = [...state.searchResults];

  // 1. Text Search Filter
  if (state.resultsSearchText) {
    list = list.filter(p =>
      (p.name && p.name.toLowerCase().includes(state.resultsSearchText)) ||
      (p.address && p.address.toLowerCase().includes(state.resultsSearchText)) ||
      (p.phone && p.phone.includes(state.resultsSearchText))
    );
  }

  // 2. Chip Filter
  if (state.resultsFilter === 'hot') {
    list = list.filter(p => p.status_lead === 'hot');
  } else if (state.resultsFilter === 'wa') {
    list = list.filter(p => !!p.whatsapp_url);
  } else if (state.resultsFilter === 'ig') {
    list = list.filter(p => !!p.instagram_url);
  } else if (state.resultsFilter === 'high_rating') {
    list = list.filter(p => (parseFloat(p.rating) || 0) >= 4.5);
  }

  state.filteredResults = list;
  renderFilteredCards();
}

// Render Filtered Cards (Production .card)
function renderFilteredCards() {
  const container = $('resultsList');
  const countEl = $('resultsCount');
  if (!container) return;

  const hotTotal = state.searchResults.filter(p => p.status_lead === 'hot').length;
  countEl.innerHTML = `Показано <b class="num">${state.filteredResults.length}</b> из ${state.searchResults.length} · <span style="color:#FFB39E">${hotTotal} без сайта</span>`;

  if (state.filteredResults.length === 0) {
    container.innerHTML = `
      <div class="empty">
        <b>Никого под фильтр</b>
        <p class="hint">Попробуйте выбрать фильтр «Все» или измените поисковый запрос.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = state.filteredResults.map((p, idx) => {
    const isHot = p.status_lead === 'hot';
    return `
      <article class="card" onclick="openLeadDrawerFromResults(${idx})" aria-label="${esc(p.name)} — открыть">
        <div class="card-top">
          <span class="lead ${isHot ? 'hot' : 'warm'}">
            <span class="dot ${isHot ? 'hot' : 'warm'}"></span>
            ${isHot ? 'Без сайта' : 'Шаблон'}
          </span>
          <span class="card-rating">
            ${icon('star', 'star')}<b>${p.rating || '4.5'}</b><span class="muted2">${p.user_ratings_total || '15+'}</span>
          </span>
        </div>
        <h3 class="card-name">${esc(p.name)}</h3>
        <p class="card-city">
          ${icon('pin', 'sm')}<span>${esc(p.address || state.currentCity)}</span>
          ${p.sphere ? `<span class="dotsep"></span><span>${esc(p.sphere)}</span>` : ''}
        </p>
        <div class="card-foot">
          <div class="cwrap">${makeChannelButtons(p)}</div>
          <button type="button" class="btn sm" onclick="event.stopPropagation(); saveLeadToCrm(${idx})">
            ${icon('plus')}<span>В Базу</span>
          </button>
        </div>
      </article>
    `;
  }).join('');
}

// Open Lead Drawer from Search Results
window.openLeadDrawerFromResults = async function(idx) {
  const lead = state.filteredResults[idx];
  if (!lead) return;
  openLeadDrawer(lead);
};

// Open Lead Drawer from CRM
window.openLeadDrawerFromCrm = async function(leadId) {
  const lead = state.crmLeads.find(l => l.id === leadId);
  if (!lead) return;
  openLeadDrawer(lead);
};

// Open Slide-in Lead Drawer
async function openLeadDrawer(lead) {
  state.activeLead = lead;
  state.roiAppended = false;

  haptic('sel');

  // Fill Header & Info
  const isHot = lead.status_lead === 'hot';
  $('drawerBadges').innerHTML = `
    <span class="lead ${isHot ? 'hot' : 'warm'}">
      <span class="dot ${isHot ? 'hot' : 'warm'}"></span>
      ${isHot ? 'Без сайта' : 'Шаблон'}
    </span>
    <span class="card-rating">
      ${icon('star', 'star')}<b>${lead.rating || '4.5'}</b><span class="muted2">${lead.user_ratings_total || '15+'}</span>
    </span>
  `;

  $('drawerName').innerText = lead.name;
  $('drawerSub').innerHTML = `${icon('pin', 'sm')}<span>${esc(lead.address || state.currentCity)}</span>`;

  // Channels
  $('drawerChannels').innerHTML = makeDrawerChannelButtons(lead);

  // Draft box
  $('drawerDraftText').value = 'Генерирую персонализированный оффер...';
  $('btnDrawerAppendRoi').disabled = false;
  $('drawerRoiLossBox').style.display = 'none';

  // Stage indicator
  const currentStage = lead.stage || 'new';
  $('drawerStageLabel').innerText = STAGE_LABELS[currentStage] || 'Новый лид';

  // Slide Open
  $('drawer').classList.add('open');
  $('scrim').classList.add('on');
  if (tg) try { tg.BackButton.show(); tg.BackButton.onClick(closeLeadDrawer); } catch {}

  // Fetch AI Pitch
  try {
    const res = await fetch('/api/pitch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: lead.name,
        sphere_id: state.selectedSphereId,
        status_lead: lead.status_lead,
        freelancer_name: state.freelancerName || state.user.first_name,
        city: state.currentCity,
        user_ratings_total: lead.user_ratings_total,
      })
    });
    const data = await res.json();
    if (data.ok) {
      state.activePitches = data.pitches || { hook: data.pitch, expert: data.pitch, short: data.pitch };
      state.activeRoi = data.roi;
      $('drawerDraftText').value = state.activePitches[state.activePitchStyle] || data.pitch;

      if (data.roi) {
        $('drawerRoiLossBox').style.display = 'block';
        $('drawerRoiText').innerHTML = `<b>Упущенная выгода:</b> ~${Number(data.roi.lost_revenue_rub).toLocaleString('ru-RU')} ₽/мес из-за отсутствия прямого сайта`;
      }
    }
  } catch (err) {
    console.error(err);
    $('drawerDraftText').value = 'Ошибка генерации текста.';
  }
}

// Close Slide-in Lead Drawer
function closeLeadDrawer() {
  haptic('light');
  $('drawer').classList.remove('open');
  $('scrim').classList.remove('on');
  if (tg) try { tg.BackButton.hide(); } catch {}
}

// Drawer Large Channels Generator
function makeDrawerChannelButtons(item) {
  let c = '';
  const { yandexUrl, googleUrl, dgisUrl } = getMapUrls(item);

  if (item.whatsapp_url) {
    c += `<a href="${esc(item.whatsapp_url)}" target="_blank" rel="noopener noreferrer" class="chbtn ch-wa" onclick="return safeOpenLink(this.href, event);">${icon('wa')}<span><b>WhatsApp</b><small>открыть чат</small></span></a>`;
  }
  if (item.telegram_url) {
    c += `<a href="${esc(item.telegram_url)}" target="_blank" rel="noopener noreferrer" class="chbtn ch-tg" onclick="return safeOpenLink(this.href, event);">${icon('tg')}<span><b>Telegram</b><small>написать</small></span></a>`;
  }
  if (item.instagram_url) {
    c += `<a href="${esc(item.instagram_url)}" target="_blank" rel="noopener noreferrer" class="chbtn ch-ig" onclick="return safeOpenLink(this.href, event);">${icon('ig')}<span><b>Instagram</b><small>открыть профиль</small></span></a>`;
  }
  if (item.phone) {
    c += `<a href="tel:${esc(item.phone_clean ? "+" + item.phone_clean : item.phone)}" class="chbtn ch-phone" onclick="return safeOpenLink(this.href, event);">${icon('phone')}<span><b>Позвонить</b><small>${esc(item.phone)}</small></span></a>`;
  }

  // Яндекс Карты — моментально открываются на любом телефоне/браузере без VPN
  c += `<a href="${esc(yandexUrl)}" target="_blank" rel="noopener noreferrer" class="chbtn ch-globe" onclick="return safeOpenLink(this.href, event);">${icon('pin')}<span><b>Яндекс Карты</b><small>посмотреть на карте</small></span></a>`;

  // 2ГИС Карты
  c += `<a href="${esc(dgisUrl)}" target="_blank" rel="noopener noreferrer" class="chbtn ch-globe" onclick="return safeOpenLink(this.href, event);">${icon('pin')}<span><b>2ГИС Карты</b><small>найти компанию в 2GIS</small></span></a>`;

  return c;
}

// Save Lead Object to CRM
async function saveLeadObjectToCrm(lead) {
  try {
    const res = await fetch('/api/crm/lead', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: state.user.id,
        place_id: lead.place_id,
        name: lead.name,
        address: lead.address,
        phone: lead.phone,
        website: lead.website,
        status_lead: lead.status_lead,
        rating: lead.rating,
        user_ratings_total: lead.user_ratings_total,
        stage: 'new',
      })
    });
    const data = await res.json();
    if (data.ok) {
      showToast('Сохранено в Базу');
      haptic('ok');
      loadKpi();
    } else {
      showToast('Ошибка сохранения');
      haptic('err');
    }
  } catch (err) {
    console.error(err);
    showToast('Ошибка сохранения');
    haptic('err');
  }
}

// Save Lead from Results list by Index
window.saveLeadToCrm = async function(idx) {
  const lead = state.filteredResults[idx];
  if (!lead) return;
  await saveLeadObjectToCrm(lead);
};

// Open Stage Bottom Sheet Picker (.pick)
window.openStagePick = function(leadId) {
  haptic('sel');
  const targetLead = state.crmLeads.find(l => l.id === leadId) || state.activeLead;
  const currentStage = targetLead?.stage || 'new';

  const stages = [
    { id: 'new', label: 'Новый лид', col: '#8E8FA0' },
    { id: 'contacted', label: 'Написал', col: '#F2C94C' },
    { id: 'negotiation', label: 'В диалоге', col: '#38A0F0' },
    { id: 'won', label: 'Клиент', col: '#6FD39A' },
    { id: 'lost', label: 'Отказ', col: '#FF6B6B' },
  ];

  let html = stages.map(s => `
    <button type="button" class="opt" data-stage="${s.id}" ${s.id === currentStage ? 'aria-current="true"' : ''}>
      <i style="background:${s.col}"></i>
      <span>${s.label}</span>
    </button>
  `).join('');

  if (targetLead?.id) {
    html += `
      <button type="button" class="opt cancel" style="color:var(--err);" id="btnPickDeleteLead">
        ${icon('trash')}
        <span>Удалить из базы</span>
      </button>
    `;
  }
  html += `<button type="button" class="opt cancel" id="btnPickCancel">Отмена</button>`;

  $('pickO').innerHTML = html;
  $('pick').classList.add('open');

  // Stage Click Event
  $$('#pickO .opt[data-stage]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const newStage = btn.dataset.stage;
      closePickModal();
      if (targetLead?.id) {
        await updateLeadStage(targetLead.id, newStage);
      }
      $('drawerStageLabel').innerText = STAGE_LABELS[newStage] || 'Новый лид';
    });
  });

  // Delete Click Event
  $('btnPickDeleteLead')?.addEventListener('click', async () => {
    closePickModal();
    if (targetLead?.id) {
      await deleteCrmLead(targetLead.id);
      closeLeadDrawer();
    }
  });

  // Cancel Click Event
  $('btnPickCancel')?.addEventListener('click', closePickModal);
};

// Close Bottom Sheet Pick Modal
function closePickModal() {
  $('pick').classList.remove('open');
}

// Load CRM Leads
async function loadCrmLeads() {
  try {
    const res = await fetch(`/api/crm/leads?user_id=${state.user.id}&stage=all`);
    const data = await res.json();
    if (data.ok && data.leads) {
      state.crmLeads = data.leads;
      renderCrmLeads();
    }
  } catch (err) {
    console.error('Error loading CRM leads', err);
  }
}

// Render CRM Leads with Status Tiles (.brow)
function renderCrmLeads() {
  const container = $('crmList');
  if (!container) return;

  const counts = { all: state.crmLeads.length, new: 0, contacted: 0, negotiation: 0, won: 0, lost: 0 };
  state.crmLeads.forEach(l => {
    if (counts[l.stage] !== undefined) counts[l.stage]++;
  });

  if ($('crmCountAll')) $('crmCountAll').innerText = counts.all;
  if ($('crmCountNew')) $('crmCountNew').innerText = counts.new;
  if ($('crmCountContacted')) $('crmCountContacted').innerText = counts.contacted;
  if ($('crmCountNegotiation')) $('crmCountNegotiation').innerText = counts.negotiation;
  if ($('crmCountWon')) $('crmCountWon').innerText = counts.won;
  if ($('crmCountLost')) $('crmCountLost').innerText = counts.lost;

  const filtered = state.crmFilter === 'all'
    ? state.crmLeads
    : state.crmLeads.filter(l => l.stage === state.crmFilter);

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="empty">
        <b>В этом разделе пока никого</b>
        <p class="hint">Найдите заведения во вкладке «Парсер» и добавьте их кнопкой «В Базу».</p>
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map(lead => {
    const col = STAGE_COLORS[lead.stage] || '#8E8FA0';
    const stageLbl = STAGE_LABELS[lead.stage] || 'Новый лид';
    return `
      <article class="brow" data-id="${lead.id}" style="--c:${col}" onclick="openLeadDrawerFromCrm(${lead.id})" aria-label="${esc(lead.name)} — открыть">
        <div class="bhead">
          <b>${esc(lead.name)}</b>
          <span class="card-rating">
            ${icon('star', 'star')}<b>${lead.rating || '4.5'}</b><span class="muted2">${lead.user_ratings_total || '10+'}</span>
          </span>
        </div>
        <div class="bmeta">
          <span>${esc(lead.address || 'Адрес не указан')}</span>
        </div>
        <div class="bfoot">
          <button type="button" class="bstage" style="--c:${col}" onclick="event.stopPropagation(); openStagePick(${lead.id})">
            <i></i><span>${esc(stageLbl)}</span>
          </button>
          <span class="sp"></span>
          <div class="cwrap">${makeChannelButtons(lead)}</div>
        </div>
      </article>
    `;
  }).join('');
}

// Update Lead Stage API
window.updateLeadStage = async function(leadId, newStage) {
  try {
    const res = await fetch('/api/crm/stage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: state.user.id,
        lead_id: leadId,
        stage: newStage
      })
    });
    const data = await res.json();
    if (data.ok) {
      showToast('Статус обновлен');
      haptic('ok');
      await loadCrmLeads();
      await loadKpi();
    }
  } catch (err) {
    console.error(err);
    showToast('Ошибка смены статуса');
  }
};

// Delete CRM Lead API
window.deleteCrmLead = async function(leadId) {
  try {
    const res = await fetch('/api/crm/lead', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: state.user.id,
        lead_id: leadId
      })
    });
    const data = await res.json();
    if (data.ok) {
      showToast('Лид удален из базы');
      haptic('ok');
      await loadCrmLeads();
      await loadKpi();
    }
  } catch (err) {
    console.error(err);
    showToast('Ошибка удаления');
  }
};

// Open Interactive Smartphone Mockup Modal
function openMockupModal(businessName, pitchText) {
  haptic('light');
  $('mockupBusinessName').innerText = businessName;
  $('mockupSphereName').innerText = state.spheres.find(s => s.id === state.selectedSphereId)?.name || 'Бизнес';
  $('mockupPitchMessage').innerText = pitchText || 'Здравствуйте! Обратил внимание на ваше заведение...';
  $('mockupModal').style.display = 'flex';
}

// Standalone Pitch Generation
async function generateStandalonePitch() {
  const name = $('inputStandaloneName').value.trim();
  if (!name) {
    showToast('Укажите название заведения');
    haptic('err');
    return;
  }

  const sphereId = $('selectStandaloneSphere').value;
  haptic('light');
  $('btnGeneratePitchStandalone').setAttribute('aria-busy', 'true');
  $('btnGeneratePitchStandalone').disabled = true;

  try {
    const res = await fetch('/api/pitch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name,
        sphere_id: sphereId,
        status_lead: 'hot',
        freelancer_name: state.freelancerName || state.user.first_name,
        city: state.currentCity,
        user_ratings_total: 25,
      })
    });
    const data = await res.json();
    if (data.ok) {
      state.activePitches = data.pitches || { hook: data.pitch, expert: data.pitch, short: data.pitch };
      $('standalonePitchText').value = state.activePitches[state.activePitchStyle] || data.pitch;
      $('standaloneResultBox').style.display = 'block';
      haptic('ok');
    }
  } catch (err) {
    console.error(err);
    showToast('Ошибка генерации');
  } finally {
    $('btnGeneratePitchStandalone').removeAttribute('aria-busy');
    $('btnGeneratePitchStandalone').disabled = false;
  }
}

// Verify Google Places API Key
async function verifyGoogleKey() {
  const key = $('inputGoogleApiKey').value.trim();
  const statusEl = $('keyVerifyStatus');
  if (!key) {
    showToast('Введите ключ API');
    return;
  }

  haptic('light');
  statusEl.style.display = 'block';
  statusEl.innerHTML = `<span class="spin"></span> Проверяю ключ в Google Cloud...`;

  try {
    const res = await fetch('/api/verify_key', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: key })
    });
    const data = await res.json();

    if (data.ok) {
      statusEl.innerHTML = `<span style="color:var(--ok)">Ключ валиден и сохранен</span>`;
      showToast('Google API ключ подтвержден');
      haptic('ok');
      await saveProfile();
    } else {
      statusEl.innerHTML = `<span style="color:var(--err)">Ошибка: ${esc(data.error || 'Ключ не принят Google')}</span>`;
      haptic('err');
    }
  } catch (err) {
    statusEl.innerHTML = `<span style="color:var(--err)">Сетевая ошибка при проверке</span>`;
    haptic('err');
  }
}

// Load Profile
async function loadProfile() {
  try {
    const res = await fetch(`/api/profile?user_id=${state.user.id}`);
    const data = await res.json();
    if (data.ok && data.profile) {
      state.freelancerName = data.profile.freelancer_name || '';
      state.googleApiKey = data.profile.google_api_key || '';
      if ($('inputFreelancerName')) $('inputFreelancerName').value = state.freelancerName;
      if ($('inputFreelancerNiche')) $('inputFreelancerNiche').value = data.profile.freelancer_niche || '';
      if ($('inputAverageCheck')) $('inputAverageCheck').value = data.profile.average_check || '';
      if ($('inputGoogleApiKey')) $('inputGoogleApiKey').value = state.googleApiKey;
    }
  } catch (err) {
    console.error('Error loading profile', err);
  }
}

// Save Profile
async function saveProfile() {
  try {
    const res = await fetch('/api/profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: state.user.id,
        freelancer_name: $('inputFreelancerName').value.trim(),
        freelancer_niche: $('inputFreelancerNiche').value.trim(),
        average_check: parseInt($('inputAverageCheck').value) || 0,
        google_api_key: $('inputGoogleApiKey').value.trim(),
      })
    });
    const data = await res.json();
    if (data.ok) {
      showToast('Профиль сохранен');
      haptic('ok');
    }
  } catch (err) {
    console.error(err);
    showToast('Ошибка сохранения профиля');
  }
}

// Launch on DOM ready
document.addEventListener('DOMContentLoaded', initApp);
