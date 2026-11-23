/**
 * DropPrint - Shared Reactive State Store
 * Lightweight pub/sub store ensuring unified single-source-of-truth state,
 * preventing race conditions, global variable pollution, and DOM sync drift.
 */

export class Store {
  /**
   * Initializes store with an optional initial state object
   * @param {Object} [initialState={}]
   */
  constructor(initialState = {}) {
    this._state = Object.freeze({ ...initialState });
    this._listeners = new Set();
  }

  /**
   * Retrieves an immutable snapshot of the current state
   * @returns {Object}
   */
  getState() {
    return this._state;
  }

  /**
   * Merges partial state updates and notifies active subscribers
   * @param {Object|Function} partialOrUpdater
   */
  setState(partialOrUpdater) {
    const prevState = this._state;
    const patch = typeof partialOrUpdater === 'function'
      ? partialOrUpdater(prevState)
      : partialOrUpdater;

    if (!patch || typeof patch !== 'object') {
      return;
    }

    const nextState = Object.freeze({ ...prevState, ...patch });
    this._state = nextState;

    // Notify listeners with fresh and previous state snapshots
    for (const listener of Array.from(this._listeners)) {
      try {
        listener(nextState, prevState);
      } catch (err) {
        console.error('[DropPrint Store] Subscriber error:', err);
      }
    }
  }

  /**
   * Subscribes a listener to state changes
   * @param {Function} listener - (currentState, prevState) => void
   * @returns {Function} Unsubscribe cleanup function
   */
  subscribe(listener) {
    if (typeof listener !== 'function') {
      throw new TypeError('[DropPrint Store] Subscriber must be a callable function');
    }
    this._listeners.add(listener);
    return () => {
      this._listeners.delete(listener);
    };
  }

  /**
   * Clears all registered subscribers
   */
  destroy() {
    this._listeners.clear();
  }
}

/**
 * Factory helper to construct a new reactive store instance
 * @param {Object} [initialState={}]
 * @returns {Store}
 */
export function createStore(initialState = {}) {
  return new Store(initialState);
}

// Global UMD / Window fallback for browser interoperability
if (typeof window !== 'undefined') {
  window.DropPrint = window.DropPrint || {};
  window.DropPrint.Store = Store;
  window.DropPrint.createStore = createStore;
}
