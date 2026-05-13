import {
  getConsentState,
  setConsentState,
  getObserverId,
  rotateObserverId,
  getZip,
  setZip,
  publicFetch,
} from "./config.js";

(async () => {
  const optToggle = document.getElementById("opt-toggle");
  const state = await getConsentState();
  optToggle.checked = (state === "opted_in");

  optToggle.addEventListener("change", async () => {
    await setConsentState(optToggle.checked ? "opted_in" : "opted_out");
  });

  const zipInput = document.getElementById("zip-input");
  zipInput.value = await getZip();
  zipInput.addEventListener("blur", async () => {
    const cleaned = await setZip(zipInput.value);
    zipInput.value = cleaned;
  });

  const observerId = await getObserverId();
  const idDisplay = document.getElementById("observer-id-display");
  idDisplay.textContent = observerId
    ? `${observerId.slice(0, 12)}… (48 random hex chars; no PII)`
    : "(not yet generated)";

  document.getElementById("rotate-id").addEventListener("click", async () => {
    const status = document.getElementById("rotate-status");
    const newId = await rotateObserverId();
    idDisplay.textContent = `${newId.slice(0, 12)}… (rotated)`;
    status.textContent = "New anonymous ID generated. Past observations remain tied to the old ID.";
    setTimeout(() => { status.textContent = ""; }, 6000);
  });

  document.getElementById("forget-me").addEventListener("click", async () => {
    if (!confirm("Delete every observation and proposal you've ever submitted? This cannot be undone.")) {
      return;
    }
    const status = document.getElementById("forget-status");
    status.textContent = "Deleting…";
    try {
      const id = await getObserverId();
      const result = await publicFetch("/api/community/delete-my-observations", {
        method: "POST",
        body: { observer_id: id },
      });
      const totals = result.deleted || {};
      status.textContent = `Deleted ${totals.observed_prices || 0} observation(s) and ${totals.community_url_proposals || 0} proposal(s). Opt-in turned off.`;
      // Reset opt-in too — they asked to be forgotten, don't keep recording.
      await setConsentState("opted_out");
      optToggle.checked = false;
      // Rotate the ID so future contributions (if they re-opt-in) aren't
      // linked to the now-deleted history.
      const newId = await rotateObserverId();
      idDisplay.textContent = `${newId.slice(0, 12)}… (fresh)`;
    } catch (e) {
      status.textContent = `Failed: ${e.message || e}`;
    }
  });
})();
