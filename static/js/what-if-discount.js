/**
 * Session-only "what-if" retailer discounts (homepage compare).
 * Clear by closing the browser tab (sessionStorage).
 */
(function (global) {
  const STORAGE_KEY = 'cps_whatif_v1';

  function load() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (e) {
      return {};
    }
  }

  function save(map) {
    const out = {};
    Object.keys(map || {}).forEach((k) => {
      const v = Math.min(90, Math.max(0, Number(map[k]) || 0));
      if (v > 0) out[k] = v;
    });
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(out));
    return out;
  }

  function clear() {
    sessionStorage.removeItem(STORAGE_KEY);
  }

  function hasActive() {
    const m = load();
    return Object.keys(m).some((k) => m[k] > 0);
  }

  function getPct(retailerKey) {
    if (!retailerKey) return 0;
    return load()[retailerKey] || 0;
  }

  function parseDollars(str) {
    if (!str) return null;
    const n = parseFloat(String(str).replace(/[$,]/g, ''));
    return Number.isFinite(n) ? n : null;
  }

  function formatEstimate(deliveredStr, retailerKey) {
    const base = parseDollars(deliveredStr);
    const pct = getPct(retailerKey);
    if (base == null || !pct) return '—';
    return '$' + (base * (1 - pct / 100)).toFixed(2);
  }

  global.CpsWhatIf = {
    STORAGE_KEY,
    load,
    save,
    clear,
    hasActive,
    getPct,
    formatEstimate,
  };
})(window);
