/**
 * DropPrint - Shared Pure Utility Functions
 * Reusable formatting, sanitization, and mathematical helpers.
 */

/**
 * Formats a monetary amount into standard Indian Rupees (INR) format: '₹X.XX'
 * Handles string numbers, null, negative, or invalid values cleanly.
 * @param {number|string} amount
 * @returns {string} e.g. '₹2.00', '₹10.50'
 */
export function formatCurrency(amount) {
  const num = Number(amount);
  if (isNaN(num)) return '₹0.00';
  return `₹${num.toFixed(2)}`;
}

/**
 * Formats print job specifications into a clean, human-readable specification string.
 * @param {number|string} pages - Document page count
 * @param {number|string} copies - Number of copies requested
 * @param {string} color - 'bw' | 'mono' | 'color'
 * @param {string} duplex - 'simplex' | 'duplex'
 * @returns {string} e.g. '2p × 3c • B&W • Duplex'
 */
export function formatSpecs(pages, copies, color, duplex) {
  const p = Math.max(1, parseInt(pages, 10) || 1);
  const c = Math.max(1, parseInt(copies, 10) || 1);
  const isColor = String(color || '').toLowerCase() === 'color';
  const colorLabel = isColor ? 'Color' : 'B&W';
  const isDuplex = String(duplex || '').toLowerCase() === 'duplex';
  const duplexLabel = isDuplex ? 'Duplex' : 'Simplex';
  return `${p}p × ${c}c • ${colorLabel} • ${duplexLabel}`;
}

/**
 * Formats seconds remaining into human-readable countdown text.
 * @param {number|string} seconds
 * @returns {string} e.g. '45s', '1m 15s'
 */
export function formatTimeRemaining(seconds) {
  const sec = Math.max(0, parseInt(seconds, 10) || 0);
  if (sec < 60) {
    return `${sec}s`;
  }
  const mins = Math.floor(sec / 60);
  const remSec = sec % 60;
  return `${mins}m ${remSec}s`;
}

/**
 * Escapes unsafe HTML characters to strictly prevent Cross-Site Scripting (XSS).
 * @param {any} str
 * @returns {string}
 */
export function escapeHtml(str) {
  if (str == null) return '';
  return String(str).replace(/[&<>"']/g, m => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  })[m]);
}

/**
 * Sanitizes a filename, preventing directory traversal and removing control/illegal characters.
 * @param {string} str
 * @returns {string} Safe, sanitized filename
 */
export function sanitizeFileName(str) {
  if (!str || typeof str !== 'string') return 'document.pdf';
  // Strip null bytes and non-printable control characters
  let clean = str.replace(/[\x00-\x1f\x80-\x9f]/g, '');
  // Extract basename to safely eliminate any directory path components
  clean = clean.split(/[/\\]/).pop() || '';
  // Replace illegal characters (\, /, :, *, ?, ", <, >, |) with underscore
  clean = clean.replace(/[/\\?%*:|"<>]/g, '_');
  // Collapse repeated dots
  clean = clean.replace(/\.{2,}/g, '.');
  clean = clean.trim();
  // Strip leading dots to prevent hidden files
  clean = clean.replace(/^\.+/, '');
  if (!clean || clean === '_') return 'document.pdf';
  return clean;
}

// Global UMD / Window fallback for browser interoperability
if (typeof window !== 'undefined') {
  window.DropPrint = window.DropPrint || {};
  window.DropPrint.Utils = {
    formatCurrency,
    formatSpecs,
    formatTimeRemaining,
    escapeHtml,
    sanitizeFileName
  };
}
