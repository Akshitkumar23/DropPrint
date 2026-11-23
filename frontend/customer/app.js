/**
 * DropPrint - Customer Mobile Web App
 * Modular architecture with separated business logic, reactive store, and unified API.
 */

// Import shared modules (or resolve via window.DropPrint fallback)
const { formatCurrency, formatSpecs, escapeHtml, sanitizeFileName } = (typeof window !== 'undefined' && window.DropPrint && window.DropPrint.Utils)
  ? window.DropPrint.Utils
  : await import('/shared/utils.js');

const { createStore } = (typeof window !== 'undefined' && window.DropPrint && window.DropPrint.createStore)
  ? window.DropPrint
  : await import('/shared/state.js');

const { api, ApiClient, ApiError } = (typeof window !== 'undefined' && window.DropPrint && window.DropPrint.api)
  ? { api: window.DropPrint.api, ApiClient: window.DropPrint.ApiClient, ApiError: window.DropPrint.ApiError }
  : await import('/shared/api.js');

// ============================================================================
// 1. PURE BUSINESS LOGIC (Decoupled from DOM)
// ============================================================================

export const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024; // 50MB

/**
 * Determines file category, badge label, icon, and css class
 * @param {File} file
 * @returns {{ category: string, badge: string, icon: string, cssClass: string }}
 */
export function getFileTypeInfo(file) {
  if (!file) return { category: 'unknown', badge: '📄 Document', icon: '📄', cssClass: 'badge-other' };
  const name = (file.name || '').toLowerCase();
  const type = (file.type || '').toLowerCase();

  if (type === 'application/pdf' || name.endsWith('.pdf')) {
    return { category: 'pdf', badge: '📄 PDF', icon: '📄', cssClass: 'badge-pdf' };
  }
  if (type.startsWith('image/') || /\.(png|jpe?g|webp|bmp|gif|svg)$/i.test(name)) {
    return { category: 'image', badge: '🖼️ Image', icon: '🖼️', cssClass: 'badge-image' };
  }
  if (/\.(docx?|doc)$/i.test(name) || type.includes('word') || type.includes('msword')) {
    return { category: 'word', badge: '📝 Word Document', icon: '📝', cssClass: 'badge-word' };
  }
  if (/\.(xlsx?|xls)$/i.test(name) || type.includes('spreadsheet') || type.includes('excel')) {
    return { category: 'excel', badge: '📊 Spreadsheet', icon: '📊', cssClass: 'badge-excel' };
  }
  if (/\.(pptx?|ppt)$/i.test(name) || type.includes('presentation') || type.includes('powerpoint')) {
    return { category: 'ppt', badge: '📑 Presentation', icon: '📑', cssClass: 'badge-ppt' };
  }
  return { category: 'other', badge: '📄 Document', icon: '📄', cssClass: 'badge-other' };
}

/**
 * Validates selected file for type, extension, and size limits
 * @param {File} file
 * @returns {{ valid: boolean, error?: string, isImage: boolean, isPdf: boolean, isOffice: boolean, fileInfo?: object }}
 */
export function validateFile(file) {
  if (!file) {
    return { valid: false, error: 'Please choose a document to print.', isImage: false, isPdf: false, isOffice: false };
  }

  // Client-side MAX FILE SIZE check: 50MB limit
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return {
      valid: false,
      error: 'File size exceeds 50MB limit. Please upload a smaller file.',
      isImage: false,
      isPdf: false,
      isOffice: false
    };
  }

  const fileInfo = getFileTypeInfo(file);
  const isPdf = fileInfo.category === 'pdf';
  const isImage = fileInfo.category === 'image';
  const isOffice = ['word', 'excel', 'ppt'].includes(fileInfo.category);

  if (!isPdf && !isImage && !isOffice) {
    return {
      valid: false,
      error: 'Unsupported file format. Please upload PDF, Word (.docx), Excel (.xlsx), PPT, or Image.',
      isImage: false,
      isPdf: false,
      isOffice: false
    };
  }

  return { valid: true, isImage, isPdf, isOffice, fileInfo };
}

/**
 * Accurately extracts page count from PDF binary headers using TextDecoder('latin1')
 * Safe on mobile web browsers without call-stack recursion overflow.
 * @param {File|Blob} file
 * @returns {Promise<number>}
 */
export async function detectPdfPages(file) {
  try {
    const buffer = await file.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    const text = new TextDecoder('latin1').decode(bytes);

    // Primary: Match /Type /Pages /Count N
    const countMatch = text.match(/\/Type\s*\/Pages[\s\S]{1,300}?\/Count\s+(\d+)/);
    if (countMatch && countMatch[1]) {
      const c = parseInt(countMatch[1], 10);
      if (c > 0) return c;
    }

    // Fallback: Count /Type /Page instances (excluding /Pages)
    const pageMatches = text.match(/\/Type\s*\/Page\b(?!\s*s)/g);
    if (pageMatches && pageMatches.length > 0) {
      return pageMatches.length;
    }
  } catch (err) {
    console.warn('[DropPrint PDF Parser] Fallback to 1 page:', err);
  }
  return 1;
}

/**
 * Calculates honest print job price with linear copy scaling and duplex sheet discount
 * Rates: B&W = ₹2.00/page, Color = ₹10.00/page, Duplex discount = ₹0.50 per sheet saved
 * @param {number} pages
 * @param {number} copies
 * @param {string} colorMode - 'bw' | 'color'
 * @param {string} duplexMode - 'simplex' | 'duplex'
 * @returns {number} Calculated total price
 */
export function calculatePrice(pages, copies, colorMode, duplexMode) {
  const rate = colorMode === 'color' ? 10.0 : 2.0;
  const p = Math.max(1, parseInt(pages, 10) || 1);
  const c = Math.max(1, parseInt(copies, 10) || 1);

  let discount = 0;
  if (duplexMode === 'duplex' && p > 1) {
    const sheetsSaved = Math.floor(p / 2);
    discount = sheetsSaved * 0.50;
  }

  const singleCopyTotal = Math.max(0, (p * rate) - discount);
  const total = Math.max(0, singleCopyTotal * c);
  return Number(total.toFixed(2));
}

/**
 * Parses a 1-based page range string (e.g. "1-3, 5, 7") and returns the count of selected pages.
 * Fully compatible with backend parse_page_range logic.
 * @param {string} rangeStr
 * @param {number} totalPages
 * @returns {number}
 */
export function parsePageRangeCount(rangeStr, totalPages) {
  const maxPages = Math.max(1, parseInt(totalPages, 10) || 1);
  if (!rangeStr || !rangeStr.trim() || rangeStr.trim().toLowerCase() === 'all' || rangeStr.trim() === '*') {
    return maxPages;
  }

  const selected = new Set();
  const parts = rangeStr.split(',');
  for (const part of parts) {
    const token = part.trim();
    if (!token) continue;
    if (token.includes('-')) {
      const bounds = token.split('-', 2);
      const sStr = bounds[0].trim();
      const eStr = bounds[1].trim();
      const start = sStr ? parseInt(sStr, 10) : 1;
      const end = eStr ? parseInt(eStr, 10) : maxPages;
      if (!isNaN(start) && !isNaN(end)) {
        const s = Math.max(1, Math.min(start, end));
        const e = Math.min(maxPages, Math.max(start, end));
        for (let p = s; p <= e; p++) {
          selected.add(p);
        }
      } else if (!isNaN(start) && start >= 1 && start <= maxPages) {
        selected.add(start);
      }
    } else {
      const p = parseInt(token, 10);
      if (!isNaN(p) && p >= 1 && p <= maxPages) {
        selected.add(p);
      }
    }
  }

  return selected.size > 0 ? selected.size : maxPages;
}

// ============================================================================
// 2. REACTIVE STATE STORE
// ============================================================================

export const store = createStore({
  file: null,
  fileName: '',
  fileSize: 0,
  pageCount: 1,
  pageRange: '',
  copies: 1,
  colorMode: 'bw',
  duplexMode: 'simplex',
  totalPrice: 2.0,
  jobId: null,
  trackingToken: null,
  shortCode: '',
  status: 'IDLE', // IDLE, UPLOADING, TRACKING
  jobStatus: '', // PENDING_PAYMENT, PAID, PRINTING, COMPLETED
  uploadProgress: 0,
  errorMessage: '',
  fileCategory: 'pdf',
  fileBadge: '📄 PDF',
  fileIcon: '📄',
  fileBadgeClass: 'badge-pdf',
  isOffice: false
});

// ============================================================================
// 3. DOM & UI CONTROLLER
// ============================================================================

let pollIntervalId = null;

function getDomElements() {
  return {
    fileInput: document.getElementById('file-input'),
    dropZone: document.getElementById('drop-zone'),
    dropzoneIdle: document.getElementById('dropzone-idle'),
    dropzoneSelected: document.getElementById('dropzone-selected'),
    fileName: document.getElementById('file-name'),
    fileTypeBadge: document.getElementById('file-type-badge'),
    fileIcon: document.getElementById('file-icon'),
    pageCountBadge: document.getElementById('page-count-badge'),
    pageRangeInput: document.getElementById('page-range-input'),
    pageRangeHelper: document.getElementById('page-range-helper'),
    btnChangeFile: document.getElementById('btn-change-file'),
    optionsSection: document.getElementById('options-section'),
    colorBw: document.getElementById('color-bw'),
    colorCol: document.getElementById('color-col'),
    duplexSingle: document.getElementById('duplex-single'),
    duplexDouble: document.getElementById('duplex-double'),
    copiesInput: document.getElementById('copies-input'),
    btnCopiesMinus: document.getElementById('btn-copies-minus'),
    btnCopiesPlus: document.getElementById('btn-copies-plus'),
    totalPrice: document.getElementById('total-price'),
    btnSubmit: document.getElementById('btn-submit'),
    progressBox: document.getElementById('progress-box'),
    progressFill: document.getElementById('progress-fill'),
    progressText: document.getElementById('progress-text'),
    printForm: document.getElementById('print-form'),
    trackingSection: document.getElementById('tracking-section'),
    pickupCode: document.getElementById('pickup-code'),
    pickupAmount: document.getElementById('pickup-amount'),
    statusCard: document.getElementById('status-card'),
    statusIcon: document.getElementById('status-icon'),
    statusTitle: document.getElementById('status-title'),
    statusDesc: document.getElementById('status-desc'),
    btnNewPrint: document.getElementById('btn-new-print'),
    errorBanner: document.getElementById('error-banner'),
    stepInd1: document.getElementById('step-ind-1'),
    stepInd2: document.getElementById('step-ind-2'),
    stepInd3: document.getElementById('step-ind-3')
  };
}

let el = {};

function init() {
  el = getDomElements();
  bindEvents();
  store.subscribe(render);

  // Resume tracking if URL query param ?track=... exists
  const params = new URLSearchParams(window.location.search);
  const trackId = params.get('track');
  if (trackId) {
    store.setState({
      jobId: trackId,
      trackingToken: trackId,
      status: 'TRACKING'
    });
    startPolling(trackId);
  } else {
    // Initial calculation
    syncPrice();
  }
}

function bindEvents() {
  // File input change
  if (el.fileInput) {
    el.fileInput.addEventListener('change', async e => {
      if (e.target.files && e.target.files[0]) {
        await handleFileSelected(e.target.files[0]);
      }
    });
  }

  // Drag and Drop
  if (el.dropZone) {
    ['dragover', 'dragenter'].forEach(evt => {
      el.dropZone.addEventListener(evt, e => {
        e.preventDefault();
        el.dropZone.classList.add('dragover');
      });
    });
    ['dragleave', 'drop'].forEach(evt => {
      el.dropZone.addEventListener(evt, e => {
        e.preventDefault();
        el.dropZone.classList.remove('dragover');
      });
    });
    el.dropZone.addEventListener('drop', async e => {
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
        await handleFileSelected(e.dataTransfer.files[0]);
      }
    });
  }

  // Change file button
  if (el.btnChangeFile) {
    el.btnChangeFile.addEventListener('click', e => {
      e.preventDefault();
      e.stopPropagation();
      resetSelection();
      if (el.fileInput) el.fileInput.click();
    });
  }

  // Color selection
  if (el.colorBw) {
    el.colorBw.addEventListener('change', () => {
      store.setState({ colorMode: 'bw' });
      syncPrice();
    });
  }
  if (el.colorCol) {
    el.colorCol.addEventListener('change', () => {
      store.setState({ colorMode: 'color' });
      syncPrice();
    });
  }

  // Duplex selection
  if (el.duplexSingle) {
    el.duplexSingle.addEventListener('change', () => {
      store.setState({ duplexMode: 'simplex' });
      syncPrice();
    });
  }
  if (el.duplexDouble) {
    el.duplexDouble.addEventListener('change', () => {
      store.setState({ duplexMode: 'duplex' });
      syncPrice();
    });
  }

  // Copies stepper
  if (el.btnCopiesMinus) {
    el.btnCopiesMinus.addEventListener('click', () => {
      const cur = store.getState().copies;
      if (cur > 1) {
        store.setState({ copies: cur - 1 });
        syncPrice();
      }
    });
  }
  if (el.btnCopiesPlus) {
    el.btnCopiesPlus.addEventListener('click', () => {
      const cur = store.getState().copies;
      if (cur < 99) {
        store.setState({ copies: cur + 1 });
        syncPrice();
      }
    });
  }
  if (el.copiesInput) {
    el.copiesInput.addEventListener('input', () => {
      let val = parseInt(el.copiesInput.value, 10);
      if (isNaN(val) || val < 1) val = 1;
      if (val > 99) val = 99;
      store.setState({ copies: val });
      syncPrice();
    });
  }

  // Page range input
  if (el.pageRangeInput) {
    el.pageRangeInput.addEventListener('input', e => {
      store.setState({ pageRange: e.target.value });
      syncPrice();
    });
  }

  // Submit button
  if (el.btnSubmit) {
    el.btnSubmit.addEventListener('click', submitJob);
  }

  // New Print button
  if (el.btnNewPrint) {
    el.btnNewPrint.addEventListener('click', () => {
      if (pollIntervalId) clearInterval(pollIntervalId);
      store.setState({
        file: null,
        fileName: '',
        fileSize: 0,
        pageCount: 1,
        pageRange: '',
        copies: 1,
        colorMode: 'bw',
        duplexMode: 'simplex',
        totalPrice: 2.0,
        jobId: null,
        trackingToken: null,
        shortCode: '',
        status: 'IDLE',
        jobStatus: '',
        uploadProgress: 0,
        errorMessage: '',
        fileCategory: 'pdf',
        fileBadge: '📄 PDF',
        fileIcon: '📄',
        fileBadgeClass: 'badge-pdf',
        isOffice: false
      });
      if (el.fileInput) el.fileInput.value = '';
      if (el.pageRangeInput) el.pageRangeInput.value = '';
      if (el.colorBw) el.colorBw.checked = true;
      if (el.duplexSingle) el.duplexSingle.checked = true;
      if (el.copiesInput) el.copiesInput.value = '1';

      const url = new URL(window.location);
      url.searchParams.delete('track');
      window.history.pushState({}, '', url);
    });
  }
}

async function handleFileSelected(file) {
  store.setState({ errorMessage: '' });
  const validation = validateFile(file);
  if (!validation.valid) {
    store.setState({ errorMessage: validation.error });
    return;
  }

  const cleanName = sanitizeFileName(file.name);
  const { category, badge, icon, cssClass } = validation.fileInfo;
  const isOffice = validation.isOffice;

  store.setState({
    file,
    fileName: cleanName,
    fileSize: file.size,
    pageCount: 1,
    fileCategory: category,
    fileBadge: badge,
    fileIcon: icon,
    fileBadgeClass: cssClass,
    isOffice
  });

  if (validation.isImage) {
    store.setState({ pageCount: 1 });
    syncPrice();
  } else if (validation.isPdf) {
    // Read PDF pages in background
    const pages = await detectPdfPages(file);
    store.setState({ pageCount: pages });
    syncPrice();
  } else {
    // Office document (.docx, .xlsx, .pptx)
    store.setState({ pageCount: 1 });
    syncPrice();
  }
}

function syncPrice() {
  const { pageCount, pageRange, copies, colorMode, duplexMode } = store.getState();
  const effectivePages = parsePageRangeCount(pageRange, pageCount);
  const totalPrice = calculatePrice(effectivePages, copies, colorMode, duplexMode);
  store.setState({ totalPrice });

  if (el.pageRangeHelper) {
    if (!pageRange || !pageRange.trim()) {
      el.pageRangeHelper.textContent = `e.g. 1-5, 8, 11-13 (All ${pageCount} pages selected)`;
      el.pageRangeHelper.style.color = '';
    } else {
      el.pageRangeHelper.textContent = `📄 ${effectivePages} page${effectivePages > 1 ? 's' : ''} selected of ${pageCount}`;
      el.pageRangeHelper.style.color = '#2563eb';
    }
  }
}

function resetSelection() {
  store.setState({
    file: null,
    fileName: '',
    fileSize: 0,
    pageCount: 1,
    pageRange: '',
    fileCategory: 'pdf',
    fileBadge: '📄 PDF',
    fileIcon: '📄',
    fileBadgeClass: 'badge-pdf',
    isOffice: false,
    errorMessage: ''
  });
  if (el.fileInput) el.fileInput.value = '';
  if (el.pageRangeInput) el.pageRangeInput.value = '';
  syncPrice();
}

/**
 * Submits the print job to /api/customer/jobs with multipart form data
 */
async function submitJob() {
  const state = store.getState();
  if (!state.file) {
    store.setState({ errorMessage: 'Please select a document before submitting.' });
    return;
  }

  store.setState({
    status: 'UPLOADING',
    uploadProgress: 0,
    errorMessage: ''
  });

  const formData = new FormData();
  formData.append('file', state.file);
  formData.append('shop_id', 'default');
  formData.append('copies', state.copies.toString());
  formData.append('color_mode', state.colorMode);
  formData.append('duplex_mode', state.duplexMode);
  formData.append('paper_size', 'A4');
  formData.append('page_count', state.pageCount.toString());
  formData.append('page_range', (state.pageRange && state.pageRange.trim()) ? state.pageRange.trim() : 'all');

  try {
    const job = await api.postMultipart('/api/customer/jobs', formData, progress => {
      store.setState({ uploadProgress: progress });
    });

    const jobId = job.job_id || job.id;
    const trackingToken = job.tracking_token || jobId;
    const shortCode = job.short_code || `PRN-${(trackingToken || '').substring(0, 4).toUpperCase()}`;

    store.setState({
      jobId,
      trackingToken,
      shortCode,
      status: 'TRACKING',
      jobStatus: job.status || 'PENDING_PAYMENT',
      totalPrice: Number(job.total_price || state.totalPrice)
    });

    // Update URL history for seamless resume
    const url = new URL(window.location);
    url.searchParams.set('track', jobId);
    window.history.pushState({}, '', url);

    startPolling(jobId);
  } catch (err) {
    store.setState({
      status: 'IDLE',
      uploadProgress: 0,
      errorMessage: err.message || 'Failed to upload document to counter. Please check connection and retry.'
    });
  }
}

function startPolling(jobId) {
  if (pollIntervalId) clearInterval(pollIntervalId);
  pollJobStatus(jobId);
  pollIntervalId = setInterval(() => pollJobStatus(jobId), 2000);
}

async function pollJobStatus(jobId) {
  try {
    let job = null;
    try {
      job = await api.get(`/api/customer/jobs/${encodeURIComponent(jobId)}/status`);
    } catch (_) {
      job = await api.get(`/api/customer/jobs/${encodeURIComponent(jobId)}`);
    }

    if (!job) return;

    store.setState({
      jobStatus: job.status || '',
      shortCode: job.short_code || store.getState().shortCode,
      totalPrice: job.total_price != null ? Number(job.total_price) : store.getState().totalPrice
    });

    const s = (job.status || '').toUpperCase();
    if (s === 'COMPLETED') {
      if (pollIntervalId) clearInterval(pollIntervalId);
    }
  } catch (err) {
    console.warn('[DropPrint Status Poller] Transient poll failure:', err);
  }
}

/**
 * Pure View Renderer - Synchronizes DOM strictly from State Store
 */
function render(state, prevState) {
  // 1. Error Banner
  if (el.errorBanner) {
    if (state.errorMessage) {
      el.errorBanner.textContent = state.errorMessage;
      el.errorBanner.classList.remove('hidden');
    } else {
      el.errorBanner.classList.add('hidden');
    }
  }

  // 2. Step Indicators
  const isSelected = !!state.file;
  const isTracking = state.status === 'TRACKING';

  if (el.stepInd1) {
    el.stepInd1.className = `step-item ${!isSelected && !isTracking ? 'step-active' : 'step-done'}`;
  }
  if (el.stepInd2) {
    el.stepInd2.className = `step-item ${isSelected && !isTracking ? 'step-active' : (isTracking ? 'step-done' : '')}`;
  }
  if (el.stepInd3) {
    el.stepInd3.className = `step-item ${isTracking ? 'step-active' : ''}`;
  }

  // 3. Form vs Tracking Screen Toggle
  if (isTracking) {
    if (el.printForm) el.printForm.classList.add('hidden');
    if (el.trackingSection) el.trackingSection.classList.remove('hidden');

    if (el.pickupCode) el.pickupCode.textContent = state.shortCode || 'PRN-WAIT';
    if (el.pickupAmount) el.pickupAmount.textContent = formatCurrency(state.totalPrice);

    renderStatusCard(state.jobStatus);
    return;
  }

  if (el.printForm) el.printForm.classList.remove('hidden');
  if (el.trackingSection) el.trackingSection.classList.add('hidden');

  // 4. Dropzone State
  if (isSelected) {
    if (el.dropzoneIdle) el.dropzoneIdle.classList.add('hidden');
    if (el.dropzoneSelected) el.dropzoneSelected.classList.remove('hidden');
    if (el.optionsSection) el.optionsSection.classList.remove('hidden');

    if (el.fileName) el.fileName.textContent = state.fileName;
    if (el.fileTypeBadge) {
      el.fileTypeBadge.textContent = state.fileBadge;
      el.fileTypeBadge.className = `file-type-badge ${state.fileBadgeClass}`;
    }
    if (el.fileIcon) {
      el.fileIcon.textContent = state.fileIcon;
    }
    if (el.pageCountBadge) {
      if (state.isOffice) {
        el.pageCountBadge.textContent = 'Office Doc (Auto-convert)';
      } else {
        el.pageCountBadge.textContent = `${state.pageCount} Page${state.pageCount === 1 ? '' : 's'}`;
      }
    }
  } else {
    if (el.dropzoneIdle) el.dropzoneIdle.classList.remove('hidden');
    if (el.dropzoneSelected) el.dropzoneSelected.classList.add('hidden');
    if (el.optionsSection) el.optionsSection.classList.add('hidden');
  }

  // 5. Copies, Page Range & Price
  if (el.copiesInput) el.copiesInput.value = state.copies;
  if (el.pageRangeInput && document.activeElement !== el.pageRangeInput) {
    el.pageRangeInput.value = state.pageRange || '';
  }
  if (el.totalPrice) el.totalPrice.textContent = formatCurrency(state.totalPrice);

  // 6. Upload Progress & Submit Button State
  const isUploading = state.status === 'UPLOADING';
  if (el.btnSubmit) {
    el.btnSubmit.disabled = isUploading;
    if (isUploading) {
      el.btnSubmit.innerHTML = state.isOffice
        ? '<span>🔄 Converting document...</span>'
        : '<span>⏳ Uploading Document...</span>';
    } else {
      el.btnSubmit.innerHTML = '<span>🚀 Submit for Print</span>';
    }
  }

  if (el.progressBox) {
    if (isUploading) {
      el.progressBox.classList.remove('hidden');
      if (el.progressFill) el.progressFill.style.width = `${state.uploadProgress}%`;
      if (el.progressText) {
        el.progressText.textContent = state.isOffice
          ? 'Converting document...'
          : `Uploading: ${state.uploadProgress}%`;
      }
    } else {
      el.progressBox.classList.add('hidden');
    }
  }
}

function renderStatusCard(status) {
  const s = (status || '').toUpperCase();
  if (s === 'COMPLETED') {
    if (el.statusCard) el.statusCard.className = 'status-card status-completed';
    if (el.statusIcon) el.statusIcon.textContent = '✅';
    if (el.statusTitle) el.statusTitle.textContent = 'Printed!';
    if (el.statusDesc) {
      el.statusDesc.textContent = 'Printed! Collect your prints from the counter. 🔒 File auto-purged from server in 1 min for your privacy.';
    }
  } else if (s === 'PRINTING') {
    if (el.statusCard) el.statusCard.className = 'status-card status-printing';
    if (el.statusIcon) el.statusIcon.textContent = '🖨️';
    if (el.statusTitle) el.statusTitle.textContent = 'Printing...';
    if (el.statusDesc) el.statusDesc.textContent = '🖨️ Printing on counter printer...';
  } else if (s === 'PAID' || s === 'APPROVED') {
    if (el.statusCard) el.statusCard.className = 'status-card status-paid';
    if (el.statusIcon) el.statusIcon.textContent = '💵';
    if (el.statusTitle) el.statusTitle.textContent = 'Cash Received';
    if (el.statusDesc) el.statusDesc.textContent = 'Cash received! Sent to printer...';
  } else {
    if (el.statusCard) el.statusCard.className = 'status-card status-pending';
    if (el.statusIcon) el.statusIcon.textContent = '⏳';
    if (el.statusTitle) el.statusTitle.textContent = 'Awaiting Payment';
    if (el.statusDesc) el.statusDesc.textContent = 'Please show this code at the counter and pay cash.';
  }
}

// Bootstrap on DOM ready
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
}
