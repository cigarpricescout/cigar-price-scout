import { setConsentState, getObserverId } from "./config.js";

document.getElementById("continue").addEventListener("click", async () => {
  const optedIn = document.getElementById("optin").checked;
  await setConsentState(optedIn ? "opted_in" : "opted_out");
  // Eagerly mint the observer id so the first observation doesn't pay
  // the random-bytes + storage round-trip on the hot path.
  if (optedIn) await getObserverId();
  window.close();
});
