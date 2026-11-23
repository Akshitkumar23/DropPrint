/**
 * DropPrint - Shopkeeper Counter Dashboard
 * Modular reactive architecture decoupled from network polling, utilizing
 * shared utilities, central API client, and reactive store.
 */

// Import shared modules (or resolve via window.DropPrint fallback)
const { formatCurrency, formatSpecs, formatTimeRemaining, escapeHtml, sanitizeFileName } =
  (typeof window !== 'undefined' && window.DropPrint && window.DropPrint.Utils)
    ? window.DropPrint.Utils
    : await import('/shared/utils.js');

const { createStore } = (typeof window !== 'undefined' && window.DropPrint && window.DropPrint.createStore)
  ? window.DropPrint
  : await import('/shared/state.js');

const { api, ApiClient, ApiError } = (typeof window !== 'undefined' && window.DropPrint && window.DropPrint.api)
  ? { api: window.DropPrint.api, ApiClient: window.DropPrint.ApiClient, ApiError: window.DropPrint.ApiError }
  : await import('/shared/api.js');

// ============================================================================
// 1. REACTIVE STATE STORE
// ============================================================================

export const store = createStore({
  jobs: [],
  filter: 'ACTIVE',
  searchQuery: '',
  processingJobIds: [],
  stats: {
    pending_cash: 0,
    pending_count: 0,
    completed_today: 0,
    revenue_today: 0
  },
  printerStatus: 'Spooler Ready',
  publicUrl: '',
  lanUrl: '',
  tunnelUrl: '',
  customerWifiUrl: '',
  customerTunnelUrl: '',
  tunnelActive: false,
  qrMode: 'tunnel' // 'tunnel' | 'wifi' - Default to tunnel for universal 4G/5G mobile data reachability
});

// Configure API toast handler
api.setToastHandler((msg, type) => {
  showToast(msg, type);
});

// ============================================================================
// 2. DOM ELEMENTS & CACHE
// ============================================================================

function getDomElements() {
  return {
    tbody: document.getElementById('jobs-tbody'),
    queueBadge: document.getElementById('queue-badge'),
    btnRefresh: document.getElementById('btn-refresh'),
    btnShowQr: document.getElementById('btn-show-qr'),
    qrModal: document.getElementById('qr-modal'),
    btnCloseModal: document.getElementById('btn-close-modal'),
    btnDismissModal: document.getElementById('btn-dismiss-modal'),
    btnPrintQr: document.getElementById('btn-print-qr'),
    btnDownloadQr: document.getElementById('btn-download-qr'),
    qrCanvas: document.getElementById('qr-canvas'),
    qrPublicLink: document.getElementById('qr-public-link'),
    qrLanLink: document.getElementById('qr-lan-link'),
    networkStatusBadge: document.getElementById('networkStatusBadge'),
    networkStatusText: document.getElementById('networkStatusText'),
    tabWifi: document.getElementById('tab-wifi'),
    tabTunnel: document.getElementById('tab-tunnel'),
    qrModeInstruction: document.getElementById('qr-mode-instruction'),
    qrModeBadge: document.getElementById('qr-mode-badge'),
    activeQrUrl: document.getElementById('active-qr-url'),
    btnCopyUrl: document.getElementById('btn-copy-url'),
    toast: document.getElementById('toast'),
    statusFilter: document.getElementById('status-filter'),
    queueSearch: document.getElementById('queue-search'),
    metricCash: document.getElementById('metric-cash'),
    metricPendingCount: document.getElementById('metric-pending-count'),
    metricActiveCount: document.getElementById('metric-active-count'),
    metricCompletedCount: document.getElementById('metric-completed-count'),
    metricCompletedRev: document.getElementById('metric-completed-rev'),
    printerStatusText: document.getElementById('printer-status-text')
  };
}

let el = {};
let pollIntervalId = null;
let countdownIntervalId = null;

// ============================================================================
// 3. INITIALIZATION & LIFECYCLE
// ============================================================================

function init() {
  el = getDomElements();
  bindEvents();

  // Subscribe view renderer strictly to reactive state changes
  store.subscribe((curr, prev) => {
    if (curr.jobs !== prev.jobs || curr.filter !== prev.filter || curr.searchQuery !== prev.searchQuery || curr.processingJobIds !== prev.processingJobIds) {
      renderTable(curr);
    }
    if (curr.jobs !== prev.jobs || curr.stats !== prev.stats) {
      renderMetrics(curr);
    }
    if (curr.printerStatus !== prev.printerStatus && el.printerStatusText) {
      el.printerStatusText.textContent = curr.printerStatus;
    }
  });

  // Fetch initial data
  fetchSystemUrls();
  fetchJobs();
  fetchPrinterHealth();

  // Network Polling: Decoupled 2-second background refresh to update store
  if (pollIntervalId) clearInterval(pollIntervalId);
  pollIntervalId = setInterval(() => {
    fetchJobs();
  }, 2000);

  // Live countdown ticker: runs every 1 second to update auto-delete badges and auto-purge expired jobs
  if (countdownIntervalId) clearInterval(countdownIntervalId);
  countdownIntervalId = setInterval(tickCountdown, 1000);
}

function bindEvents() {
  if (el.btnRefresh) {
    el.btnRefresh.addEventListener('click', () => fetchJobs(true));
  }

  if (el.btnShowQr) {
    el.btnShowQr.addEventListener('click', openQrModal);
  }

  if (el.btnCloseModal) {
    el.btnCloseModal.addEventListener('click', closeQrModal);
  }

  if (el.btnDismissModal) {
    el.btnDismissModal.addEventListener('click', closeQrModal);
  }

  if (el.qrModal) {
    el.qrModal.addEventListener('click', e => {
      if (e.target === el.qrModal) closeQrModal();
    });
  }

  if (el.btnPrintQr) {
    el.btnPrintQr.addEventListener('click', printQrSign);
  }

  if (el.btnDownloadQr) {
    el.btnDownloadQr.addEventListener('click', downloadQrImage);
  }

  if (el.tabWifi) {
    el.tabWifi.addEventListener('click', () => {
      store.setState({ qrMode: 'wifi' });
      syncQrModalView();
    });
  }

  if (el.tabTunnel) {
    el.tabTunnel.addEventListener('click', () => {
      store.setState({ qrMode: 'tunnel' });
      syncQrModalView();
    });
  }

  if (el.btnCopyUrl) {
    el.btnCopyUrl.addEventListener('click', async () => {
      const urlToCopy = el.activeQrUrl ? el.activeQrUrl.value : '';
      if (!urlToCopy) return;
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(urlToCopy);
        } else if (el.activeQrUrl) {
          el.activeQrUrl.select();
          document.execCommand('copy');
        }
        showToast('📋 Copied QR URL to clipboard!', 'success');
      } catch (err) {
        showToast('Failed to copy URL to clipboard', 'error');
      }
    });
  }

  if (el.statusFilter) {
    el.statusFilter.addEventListener('change', () => {
      store.setState({ filter: el.statusFilter.value });
      fetchJobs();
    });
  }

  if (el.queueSearch) {
    el.queueSearch.addEventListener('input', () => {
      store.setState({ searchQuery: el.queueSearch.value.trim().toLowerCase() });
    });
  }

  // Keyboard shortcut: Escape closes modal
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && el.qrModal && !el.qrModal.classList.contains('hidden')) {
      closeQrModal();
    }
  });
}

// ============================================================================
// 4. DATA FETCHING (Mutates Store Only)
// ============================================================================

async function fetchJobs(manual = false) {
  try {
    const filter = store.getState().filter;
    const url = filter === 'ALL' ? '/api/shop/jobs?all_history=true' : '/api/shop/jobs';

    const data = await api.get(url);
    const jobList = Array.isArray(data) ? data : (data && Array.isArray(data.jobs) ? data.jobs : []);

    // Merge incoming jobs with preserved age_seconds countdown for completed jobs
    const currentJobsMap = new Map(store.getState().jobs.map(j => [j.id, j]));
    const mergedJobs = jobList.map(newJob => {
      const existing = currentJobsMap.get(newJob.id);
      if (existing && existing.age_seconds != null && newJob.age_seconds == null) {
        return { ...newJob, age_seconds: existing.age_seconds };
      }
      return newJob;
    });

    store.setState({
      jobs: mergedJobs,
      stats: data.stats || null
    });

    if (manual) {
      showToast('Queue refreshed', 'success');
    }
  } catch (err) {
    console.warn('[DropPrint Dashboard] Failed to fetch jobs:', err);
    if (manual) {
      showToast('Network error fetching jobs', 'error');
    }
  }
}

async function fetchPrinterHealth() {
  try {
    const res = await api.get('/api/health');
    if (res && res.status === 'ok') {
      store.setState({ printerStatus: 'Spooler Ready' });
    }
  } catch (_) {
    // Non-fatal health ping check
  }
}

async function fetchSystemUrls() {
  try {
    let res = null;
    try {
      res = await api.get('/api/v1/system/status');
    } catch (_) {
      try {
        res = await api.get('/api/system/network-info');
      } catch (__) {
        res = await api.get('/api/system/public-url');
      }
    }

    if (res) {
      const lanBase = (res.lan_url || window.location.origin).replace(/\/$/, '');
      const tunnelBase = (res.tunnel_url || '').replace(/\/$/, '');
      const tunnelActive = Boolean(
        res.tunnel_active ||
        (tunnelBase && !tunnelBase.includes('127.0.0.1') && !tunnelBase.includes('localhost') && tunnelBase.startsWith('https://'))
      );

      const custLan = res.customer_lan_url || `${lanBase}/customer/?shop=default`;
      const custTunnel = res.customer_tunnel_url || (tunnelBase ? `${tunnelBase}/customer/?shop=default` : custLan);

      const defaultMode = tunnelActive ? 'tunnel' : 'wifi';

      store.setState({
        lanUrl: lanBase,
        tunnelUrl: tunnelBase,
        tunnelActive,
        customerWifiUrl: custLan,
        customerTunnelUrl: custTunnel,
        publicUrl: tunnelActive ? custTunnel : custLan,
        qrMode: defaultMode
      });

      updateNetworkBadge(tunnelActive);
      updateModalUrls(custTunnel, custLan);
    }
  } catch (err) {
    console.warn('[DropPrint Dashboard] Failed to fetch system network info:', err);
    const fallback = `${window.location.origin}/customer/?shop=default`;
    store.setState({
      lanUrl: window.location.origin,
      tunnelUrl: '',
      tunnelActive: false,
      customerWifiUrl: fallback,
      customerTunnelUrl: fallback,
      publicUrl: fallback
    });
    updateNetworkBadge(false);
    updateModalUrls(fallback, fallback);
  }
}

function updateNetworkBadge(tunnelActive) {
  if (!el.networkStatusBadge || !el.networkStatusText) return;
  if (tunnelActive) {
    el.networkStatusBadge.className = 'network-badge live';
    el.networkStatusText.textContent = '🟢 Live (4G/5G + Wi-Fi)';
  } else {
    el.networkStatusBadge.className = 'network-badge wifi-only';
    el.networkStatusText.textContent = '📶 Shop Wi-Fi Mode';
  }
}

function updateModalUrls(publicUrl, lanUrl) {
  if (el.qrPublicLink) {
    el.qrPublicLink.href = publicUrl;
    el.qrPublicLink.textContent = publicUrl;
  }
  if (el.qrLanLink) {
    el.qrLanLink.href = lanUrl;
    el.qrLanLink.textContent = lanUrl;
  }
}

// ============================================================================
// 5. LIVE COUNTDOWN & DISMISS ENGINE
// ============================================================================

function tickCountdown() {
  const currentJobs = store.getState().jobs;
  let hasExpired = false;

  const updatedJobs = currentJobs.map(job => {
    const s = (job.status || '').toUpperCase();
    if (s === 'COMPLETED' || s === 'CANCELLED' || s === 'REJECTED') {
      const currentAge = job.age_seconds != null ? job.age_seconds : 0;
      const nextAge = currentAge + 1;
      if (nextAge >= 60) {
        hasExpired = true;
      }
      return { ...job, age_seconds: nextAge };
    }
    return job;
  });

  if (hasExpired && store.getState().filter === 'ACTIVE') {
    // Purge expired jobs (> 60 seconds) from active view
    const unexpired = updatedJobs.filter(job => {
      const s = (job.status || '').toUpperCase();
      if (s === 'COMPLETED' || s === 'CANCELLED' || s === 'REJECTED') {
        return (job.age_seconds || 0) < 60;
      }
      return true;
    });
    store.setState({ jobs: unexpired });
  } else {
    // Direct DOM tick for smoother rendering without reconstructing full table every second
    document.querySelectorAll('[data-purge-job-id]').forEach(badge => {
      const jobId = badge.getAttribute('data-purge-job-id');
      const targetJob = updatedJobs.find(j => j.id === jobId);
      if (targetJob) {
        const remaining = Math.max(0, 60 - (targetJob.age_seconds || 0));
        const secSpan = badge.querySelector('.purge-sec');
        if (secSpan) {
          secSpan.textContent = `${remaining}s`;
        }
      }
    });
  }
}

/**
 * Instantly dismisses a completed row from the active counter queue
 * @param {string} jobId
 */
export function dismissJob(jobId) {
  if (!jobId) return;
  const row = document.querySelector(`tr[data-job-id="${jobId}"]`);
  if (row) {
    row.classList.add('row-fading-out');
    setTimeout(() => {
      const updated = store.getState().jobs.filter(j => j.id !== jobId);
      store.setState({ jobs: updated });
    }, 250);
  } else {
    const updated = store.getState().jobs.filter(j => j.id !== jobId);
    store.setState({ jobs: updated });
  }
}

/**
 * Submits Receive Cash & Print command to backend
 * @param {string} jobId
 */
export async function receiveAndPrint(jobId) {
  if (!jobId) return;
  const processing = new Set(store.getState().processingJobIds);
  if (processing.has(jobId)) return;

  processing.add(jobId);
  store.setState({ processingJobIds: Array.from(processing) });

  try {
    await api.post(`/api/shop/jobs/${encodeURIComponent(jobId)}/receive-and-print`, {});
    showToast('✅ Cash received! Sent directly to printer.', 'success');
    await fetchJobs();
  } catch (err) {
    console.error('[DropPrint] Receive & print failed:', err);
    showToast(`❌ Print failed: ${err.message || 'Error spooling print job'}`, 'error');
  } finally {
    const currentProcessing = new Set(store.getState().processingJobIds);
    currentProcessing.delete(jobId);
    store.setState({ processingJobIds: Array.from(currentProcessing) });
  }
}

// Global browser window bindings for inline HTML table action handlers
if (typeof window !== 'undefined') {
  window.receiveAndPrint = receiveAndPrint;
  window.dismissJobFromUi = dismissJob;
}

// ============================================================================
// 6. VIEW RENDERING (Driven by Reactive Store)
// ============================================================================

function renderMetrics(state) {
  const { jobs, stats } = state;

  if (stats) {
    if (el.metricCash) el.metricCash.textContent = formatCurrency(stats.pending_cash || 0);
    if (el.metricPendingCount) {
      const count = stats.pending_count || 0;
      el.metricPendingCount.textContent = `${count} order${count === 1 ? '' : 's'} waiting for cash`;
    }
    if (el.metricCompletedCount) el.metricCompletedCount.textContent = stats.completed_today || 0;
    if (el.metricCompletedRev) {
      el.metricCompletedRev.textContent = `Revenue: ${formatCurrency(stats.revenue_today || 0)}`;
    }
    if (el.metricActiveCount) el.metricActiveCount.textContent = jobs.length;
    if (el.queueBadge) el.queueBadge.textContent = `${jobs.length} Active`;
    return;
  }

  // Derive metrics if server stats are omitted
  let pendingCash = 0;
  let pendingCount = 0;
  let completedCount = 0;
  let completedRev = 0;

  jobs.forEach(job => {
    const s = (job.status || '').toUpperCase();
    const price = Number(job.total_price || 0);

    if (s === 'PENDING_PAYMENT' || s === 'UPLOADED') {
      pendingCash += price;
      pendingCount++;
    } else if (s === 'COMPLETED') {
      completedCount++;
      completedRev += price;
    }
  });

  if (el.metricCash) el.metricCash.textContent = formatCurrency(pendingCash);
  if (el.metricPendingCount) {
    el.metricPendingCount.textContent = `${pendingCount} order${pendingCount === 1 ? '' : 's'} waiting for cash`;
  }
  if (el.metricActiveCount) el.metricActiveCount.textContent = jobs.length;
  if (el.metricCompletedCount) el.metricCompletedCount.textContent = completedCount;
  if (el.metricCompletedRev) el.metricCompletedRev.textContent = `Revenue: ${formatCurrency(completedRev)}`;
  if (el.queueBadge) el.queueBadge.textContent = `${jobs.length} Order${jobs.length === 1 ? '' : 's'}`;
}

function renderTable(state) {
  if (!el.tbody) return;

  const { jobs, filter, searchQuery, processingJobIds } = state;
  const processingSet = new Set(processingJobIds);

  const filtered = jobs.filter(job => {
    const s = (job.status || '').toUpperCase();
    const code = (job.short_code || '').toLowerCase();
    const fname = (job.filename || '').toLowerCase();

    // 1. Status Filter
    if (filter === 'ACTIVE') {
      if (s === 'COMPLETED' || s === 'CANCELLED' || s === 'REJECTED') {
        const age = job.age_seconds != null ? job.age_seconds : 999;
        if (age >= 60) return false;
      }
    } else if (filter === 'PENDING_PAYMENT') {
      if (s !== 'PENDING_PAYMENT' && s !== 'UPLOADED') {
        return false;
      }
    }

    // 2. Search Query Filter
    if (searchQuery && !code.includes(searchQuery) && !fname.includes(searchQuery)) {
      return false;
    }

    return true;
  });

  if (filtered.length === 0) {
    el.tbody.innerHTML = `
      <tr>
        <td colspan="6" class="table-empty">
          <div class="empty-state">
            <span class="empty-icon" aria-hidden="true">📭</span>
            <p class="empty-title">Queue is Clean — All Caught Up!</p>
            <p class="empty-desc">Completed orders automatically delete after 1 minute. New customer uploads appear here instantly.</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  const rowsHtml = filtered.map(job => {
    const isProcessing = processingSet.has(job.id);
    const code = escapeHtml(job.short_code || (`PRN-${(job.tracking_token || job.id || '').substring(0, 4).toUpperCase()}`));
    const filename = escapeHtml(sanitizeFileName(job.filename || 'document.pdf'));
    const details = formatSpecs(job.page_count, job.copies, job.color_mode, job.duplex_mode);
    const price = formatCurrency(job.total_price);
    const statusBadge = renderStatusBadge(job.status);
    const actionBtn = renderActionCell(job, isProcessing);
    const s = (job.status || '').toUpperCase();
    const isCompleted = s === 'COMPLETED';
    const fileSizeText = isCompleted
      ? '🔒 Auto-purging (1m)'
      : (job.file_size ? `${Math.round(job.file_size / 1024)} KB` : 'PDF');

    return `
      <tr data-job-id="${escapeHtml(job.id)}" class="${isCompleted ? 'row-completed' : ''}">
        <td class="td-code"><span class="job-code-pill">${code}</span></td>
        <td class="td-file" title="${filename}">
          <div class="filename-box">
            <span class="file-icon" aria-hidden="true">📄</span>
            <div>
              <span class="file-title">${filename}</span>
              <span class="file-meta">${fileSizeText}</span>
            </div>
          </div>
        </td>
        <td class="td-specs"><span class="specs-tag">${details}</span></td>
        <td class="td-cash"><span class="cash-tag">${price}</span></td>
        <td class="td-status">${statusBadge}</td>
        <td class="td-action">${actionBtn}</td>
      </tr>
    `;
  }).join('');

  el.tbody.innerHTML = rowsHtml;
}

function renderStatusBadge(status) {
  const s = (status || '').toUpperCase();
  if (s === 'PENDING_PAYMENT' || s === 'UPLOADED') {
    return '<span class="status-badge badge-pending">🟡 Pending Cash</span>';
  } else if (s === 'PAID') {
    return '<span class="status-badge badge-paid">🔵 Cash Paid</span>';
  } else if (s === 'PRINTING' || s === 'APPROVED') {
    return '<span class="status-badge badge-printing">🖨️ Printing...</span>';
  } else if (s === 'COMPLETED') {
    return '<span class="status-badge badge-completed">🟢 Completed</span>';
  }
  return `<span class="status-badge">${escapeHtml(s || 'UNKNOWN')}</span>`;
}

function renderActionCell(job, isProcessing) {
  const s = (job.status || '').toUpperCase();
  if (s === 'COMPLETED') {
    const age = job.age_seconds != null ? job.age_seconds : 0;
    const remaining = Math.max(0, 60 - age);
    const fileStem = (job.file_r2_key || '').replace('uploads/', '').replace('.pdf', '');

    return `
      <div class="action-completed-box">
        <span class="badge-printed">✅ Printed &amp; Handed Over</span>
        <div class="countdown-group">
          <span class="auto-delete-hint" data-purge-job-id="${escapeHtml(job.id)}" data-remaining="${remaining}">
            ⏱️ Auto-deleting in <strong class="purge-sec">${remaining}s</strong>
          </span>
          <button type="button" class="btn-dismiss-row" onclick="window.dismissJobFromUi('${escapeHtml(job.id)}')" title="Dismiss now" aria-label="Dismiss order immediately">✕</button>
        </div>
      </div>
    `;
  }

  if (s === 'PRINTING' || s === 'APPROVED') {
    return '<span class="badge-printed">🖨️ Printing Now...</span>';
  }

  if (isProcessing) {
    return '<button type="button" class="btn-receive-print" disabled>⏳ Spooling to Printer...</button>';
  }

  return `<button type="button" class="btn-receive-print" onclick="window.receiveAndPrint('${escapeHtml(job.id)}')">💵 Receive Cash &amp; Print</button>`;
}

// ============================================================================
// 7. TOAST NOTIFICATIONS
// ============================================================================

export function showToast(message, type = 'info') {
  if (!el.toast) return;
  el.toast.textContent = message;
  el.toast.className = `toast toast-${type}`;
  el.toast.classList.remove('hidden');

  clearTimeout(el.toast._timer);
  el.toast._timer = setTimeout(() => {
    if (el.toast) el.toast.classList.add('hidden');
  }, 3500);
}

// ============================================================================
// 8. QR CODE STANDEE MODAL (Zero-CDN Canvas Renderer)
// ============================================================================

function openQrModal() {
  syncQrModalView();
  if (el.qrModal) el.qrModal.classList.remove('hidden');
}

function closeQrModal() {
  if (el.qrModal) el.qrModal.classList.add('hidden');
}

function syncQrModalView() {
  const { qrMode, customerWifiUrl, customerTunnelUrl, tunnelActive } = store.getState();
  const isWifi = qrMode === 'wifi';
  const targetUrl = isWifi
    ? (customerWifiUrl || `${window.location.origin}/customer/?shop=default`)
    : (tunnelActive ? customerTunnelUrl : (customerWifiUrl || `${window.location.origin}/customer/?shop=default`));

  if (el.tabWifi) {
    el.tabWifi.className = `qr-mode-btn ${isWifi ? 'active' : ''}`;
    el.tabWifi.setAttribute('aria-selected', isWifi ? 'true' : 'false');
  }
  if (el.tabTunnel) {
    el.tabTunnel.className = `qr-mode-btn ${!isWifi ? 'active' : ''}`;
    el.tabTunnel.setAttribute('aria-selected', !isWifi ? 'true' : 'false');
  }

  if (el.qrModeInstruction) {
    el.qrModeInstruction.textContent = isWifi
      ? 'For local customers connected to shop Wi-Fi. (Permanent address that never changes as long as shop router is active).'
      : (tunnelActive
          ? 'For customers using their own mobile SIM data (4G/5G) without connecting to shop Wi-Fi.'
          : 'Cloudflare tunnel is not active right now. Connect customers to shop Wi-Fi or launch tunnel.');
  }

  if (el.qrModeBadge) {
    el.qrModeBadge.textContent = isWifi ? '📶 Shop Wi-Fi Mode' : '🌐 Mobile 4G/5G Mode';
  }

  if (el.activeQrUrl) {
    el.activeQrUrl.value = targetUrl;
  }

  renderQrCanvas(targetUrl);
}

function renderQrCanvas(url) {
  const canvas = el.qrCanvas;
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const width = canvas.width;
  const height = canvas.height;

  // Clear canvas with white background while loading
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, width, height);

  ctx.fillStyle = '#64748b';
  ctx.font = '13px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('⏳ Generating Official QR...', width / 2, height / 2);

  const qrImg = new Image();
  qrImg.crossOrigin = 'anonymous';
  qrImg.onload = function() {
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, width, height);
    // Draw real ISO-compliant QR code centered with crisp sharp pixels
    ctx.imageSmoothingEnabled = false;
    const margin = 8;
    ctx.drawImage(qrImg, margin, margin, width - margin * 2, height - margin * 2);
  };
  qrImg.onerror = function(err) {
    console.error('Failed to load official QR from /api/qrcode.png:', err);
    ctx.fillStyle = '#fee2e2';
    ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = '#b91c1c';
    ctx.font = '12px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('❌ Failed to load QR image', width / 2, height / 2);
  };
  qrImg.src = `/api/qrcode.png?url=${encodeURIComponent(url)}&_t=${Date.now()}`;
}

function printQrSign() {
  if (!el.qrCanvas) return;
  const { qrMode, customerWifiUrl, customerTunnelUrl, tunnelActive } = store.getState();
  const isWifi = qrMode === 'wifi';
  const targetUrl = isWifi
    ? (customerWifiUrl || `${window.location.origin}/customer/?shop=default`)
    : (tunnelActive ? customerTunnelUrl : (customerWifiUrl || `${window.location.origin}/customer/?shop=default`));
  const modeTitle = isWifi ? '📶 Shop Wi-Fi Counter Standee' : '🌐 Mobile 4G/5G DropPrint Standee';
  const modeDesc = isWifi
    ? 'Connect to Shop Wi-Fi and scan this QR code to drop documents and print instantly'
    : 'Scan with your mobile phone camera (4G/5G) to drop documents and print instantly';

  const qrImgSrc = `/api/qrcode.png?url=${encodeURIComponent(targetUrl)}`;
  const win = window.open('', '_blank');
  if (!win) return;
  win.document.write(`
    <html>
      <head>
        <title>${modeTitle}</title>
        <style>
          body { margin: 0; display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 100vh; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #fff; }
          .card { border: 2px solid #e2e8f0; border-radius: 20px; padding: 32px; display: flex; flex-direction: column; align-items: center; max-width: 440px; box-shadow: 0 4px 16px rgba(0,0,0,0.06); text-align: center; }
          h1 { font-size: 30px; margin: 0 0 6px 0; color: #0f172a; }
          .tag { font-size: 14px; font-weight: 700; color: #2563eb; background: #eff6ff; padding: 4px 12px; border-radius: 20px; border: 1px solid #bfdbfe; margin-bottom: 14px; }
          p { font-size: 15px; color: #64748b; margin: 0 0 20px 0; line-height: 1.4; }
          img { width: 280px; height: 280px; border: 1px solid #cbd5e1; padding: 10px; border-radius: 12px; background: #fff; }
          .url { margin-top: 18px; font-size: 14px; font-weight: bold; color: #2563eb; word-break: break-all; }
          .footer { margin-top: 14px; font-size: 12px; color: #94a3b8; }
        </style>
      </head>
      <body onload="window.print(); window.close();">
        <div class="card">
          <h1>🖨️ DropPrint</h1>
          <div class="tag">${modeTitle}</div>
          <p>${modeDesc}</p>
          <img src="${qrImgSrc}">
          <div class="url">${escapeHtml(targetUrl)}</div>
          <div class="footer">Drop document • Get 4-digit code • Pay cash at counter</div>
        </div>
      </body>
    </html>
  `);
  win.document.close();
}

function downloadQrImage() {
  const { qrMode, customerWifiUrl, customerTunnelUrl, tunnelActive } = store.getState();
  const isWifi = qrMode === 'wifi';
  const targetUrl = isWifi
    ? (customerWifiUrl || `${window.location.origin}/customer/?shop=default`)
    : (tunnelActive ? customerTunnelUrl : (customerWifiUrl || `${window.location.origin}/customer/?shop=default`));
  const mode = qrMode || 'wifi';
  const a = document.createElement('a');
  a.download = `DropPrint_Standee_${mode.toUpperCase()}.png`;
  a.href = `/api/qrcode.png?url=${encodeURIComponent(targetUrl)}`;
  a.click();
  showToast(`💾 Saved standee (${mode === 'wifi' ? 'Wi-Fi' : 'Mobile 4G/5G'}) image!`, 'success');
}

// Bootstrap on DOM ready
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
}
