/**
 * DropPrint - Shared Centralized API Client
 * Unified HTTP interface with configurable timeouts, automatic retries for transient
 * failures, structured error responses, and integrated toast alert notifications.
 */

export class ApiError extends Error {
  /**
   * @param {string} message
   * @param {number} [status=0]
   * @param {any} [data=null]
   */
  constructor(message, status = 0, data = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

export class ApiClient {
  /**
   * @param {Object} [config]
   * @param {string} [config.baseUrl='']
   * @param {number} [config.timeout=15000]
   * @param {number} [config.maxRetries=2]
   * @param {Function} [config.onToast]
   */
  constructor(config = {}) {
    this.baseUrl = config.baseUrl || '';
    this.timeout = config.timeout || 15000;
    this.maxRetries = config.maxRetries !== undefined ? config.maxRetries : 2;
    this.onToast = config.onToast || null;
  }

  /**
   * Configures the global toast notification handler
   * @param {Function} handler - (message: string, type: 'error'|'info'|'success'|'warning') => void
   */
  setToastHandler(handler) {
    this.onToast = handler;
  }

  /**
   * Triggers a user toast alert notification
   * @param {string} message
   * @param {'error'|'info'|'success'|'warning'} [type='error']
   */
  notifyToast(message, type = 'error') {
    if (typeof this.onToast === 'function') {
      try {
        this.onToast(message, type);
      } catch (err) {
        console.error('[DropPrint API] Toast callback failed:', err);
      }
    }
    // Also dispatch decoupled DOM event
    if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
      try {
        window.dispatchEvent(new CustomEvent('dropprint:toast', { detail: { message, type } }));
      } catch (_) {}
    }
  }

  /**
   * Performs an HTTP request with timeout, JSON parsing, and retry handling
   * @private
   */
  async _requestWithRetry(url, options = {}, retries = this.maxRetries) {
    const fullUrl = this.baseUrl ? `${this.baseUrl.replace(/\/$/, '')}/${url.replace(/^\//, '')}` : url;
    let attempt = 0;

    while (attempt <= retries) {
      attempt++;
      const controller = new AbortController();
      const timeoutMs = options.timeout || this.timeout;
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

      try {
        const response = await fetch(fullUrl, {
          ...options,
          signal: controller.signal
        });
        clearTimeout(timeoutId);

        let data = null;
        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
          data = await response.json();
        } else {
          data = await response.text();
        }

        if (!response.ok) {
          const detail = (data && typeof data === 'object' && (data.detail || data.error_message || data.message))
            || response.statusText
            || `HTTP error ${response.status}`;

          // Do NOT retry 4xx client errors (400 Bad Request, 404 Not Found, 422 Validation)
          if (response.status >= 400 && response.status < 500) {
            throw new ApiError(detail, response.status, data);
          }

          // Retry on 5xx or 429 if attempts remain
          if (attempt <= retries && (response.status >= 500 || response.status === 429)) {
            await new Promise(r => setTimeout(r, attempt * 400));
            continue;
          }

          const apiErr = new ApiError(detail, response.status, data);
          this.notifyToast(detail, 'error');
          throw apiErr;
        }

        return data;
      } catch (err) {
        clearTimeout(timeoutId);

        if (err instanceof ApiError) {
          throw err;
        }

        const isAbort = err.name === 'AbortError';
        const msg = isAbort
          ? `Request timed out after ${timeoutMs}ms`
          : (err.message || 'Network connection failed');

        // Retry transient network dropouts
        if (attempt <= retries && !isAbort) {
          await new Promise(r => setTimeout(r, attempt * 400));
          continue;
        }

        const finalErr = new ApiError(msg, 0, err);
        this.notifyToast(msg, 'error');
        throw finalErr;
      }
    }
  }

  /**
   * HTTP GET method
   * @param {string} url
   * @param {Object} [headers={}]
   * @returns {Promise<any>}
   */
  async get(url, headers = {}) {
    return this._requestWithRetry(url, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        ...headers
      }
    });
  }

  /**
   * HTTP POST method (JSON payload)
   * @param {string} url
   * @param {any} body
   * @param {Object} [headers={}]
   * @returns {Promise<any>}
   */
  async post(url, body, headers = {}) {
    return this._requestWithRetry(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        ...headers
      },
      body: JSON.stringify(body)
    });
  }

  /**
   * HTTP POST Multipart method (FormData) with real-time upload progress reporting
   * @param {string} url
   * @param {FormData} formData
   * @param {Function} [onProgress] - (percent: number) => void
   * @returns {Promise<any>}
   */
  async postMultipart(url, formData, onProgress = null) {
    const fullUrl = this.baseUrl ? `${this.baseUrl.replace(/\/$/, '')}/${url.replace(/^\//, '')}` : url;

    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', fullUrl, true);
      xhr.timeout = this.timeout * 3; // Generous upload timeout for large PDF files

      if (typeof onProgress === 'function' && xhr.upload) {
        xhr.upload.addEventListener('progress', e => {
          if (e.lengthComputable) {
            const pct = Math.round((e.loaded / e.total) * 100);
            onProgress(pct);
          }
        });
      }

      xhr.onload = () => {
        let data = null;
        try {
          data = JSON.parse(xhr.responseText);
        } catch (_) {
          data = xhr.responseText;
        }

        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data);
        } else {
          const detail = (data && typeof data === 'object' && (data.detail || data.error_message || data.message))
            || `Upload error (${xhr.status})`;
          const err = new ApiError(detail, xhr.status, data);
          this.notifyToast(detail, 'error');
          reject(err);
        }
      };

      xhr.ontimeout = () => {
        const msg = `Upload timed out after ${xhr.timeout}ms`;
        const err = new ApiError(msg, 0);
        this.notifyToast(msg, 'error');
        reject(err);
      };

      xhr.onerror = () => {
        const msg = 'Network error connecting to counter server. Please retry.';
        const err = new ApiError(msg, 0);
        this.notifyToast(msg, 'error');
        reject(err);
      };

      xhr.send(formData);
    });
  }
}

// Default singleton instance
export const api = new ApiClient();

// Global UMD / Window fallback for browser interoperability
if (typeof window !== 'undefined') {
  window.DropPrint = window.DropPrint || {};
  window.DropPrint.ApiClient = ApiClient;
  window.DropPrint.ApiError = ApiError;
  window.DropPrint.api = api;
}
