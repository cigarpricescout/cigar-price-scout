/**
 * In-memory "what-if" retailer discounts (homepage compare).
 * Clears on page refresh; does not persist across reloads.
 */
(function (global) {
  let overrides = {};

  // Drop any legacy persisted storage from earlier versions.
  try {
    sessionStorage.removeItem('cps_whatif_v1');
    localStorage.removeItem('cps_whatif_v1');
  } catch (e) {
    /* ignore */
  }

  function load() {
    return { ...overrides };
  }

  function save(map) {
    const out = {};
    Object.keys(map || {}).forEach((k) => {
      const v = Math.min(90, Math.max(0, Number(map[k]) || 0));
      if (v > 0) out[k] = v;
    });
    overrides = out;
    return { ...overrides };
  }

  function clear() {
    overrides = {};
  }

  function hasActive() {
    return Object.keys(overrides).some((k) => overrides[k] > 0);
  }

  function getPct(retailerKey) {
    if (!retailerKey) return 0;
    return overrides[retailerKey] || 0;
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
    load,
    save,
    clear,
    hasActive,
    getPct,
    formatEstimate,
  };
})(window);
