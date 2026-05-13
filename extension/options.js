import { apiFetch, getAdminKey, setAdminKey, API_BASE } from "./config.js";

const $key    = document.getElementById("admin-key");
const $save   = document.getElementById("save");
const $test   = document.getElementById("test");
const $show   = document.getElementById("show-hide");
const $status = document.getElementById("status");

function setStatus(msg, kind = "mute") {
  $status.textContent = msg;
  $status.className = `status ${kind}`;
}

(async function init() {
  const current = await getAdminKey();
  if (current) {
    $key.value = current;
    setStatus("Loaded saved key.", "mute");
  }
})();

$save.addEventListener("click", async () => {
  const value = ($key.value || "").trim();
  await setAdminKey(value);
  setStatus(value ? "Saved." : "Cleared.", "ok");
});

$test.addEventListener("click", async () => {
  setStatus("Testing…", "mute");
  // Save first so the test uses the value in the input box.
  await setAdminKey(($key.value || "").trim());
  try {
    const res = await apiFetch("/api/admin/retailer-registry");
    setStatus(`OK — ${res.total} retailers known at ${API_BASE}.`, "ok");
  } catch (e) {
    setStatus(`Error: ${e.message || e}`, "err");
  }
});

$show.addEventListener("click", () => {
  if ($key.type === "password") {
    $key.type = "text";
    $show.textContent = "Hide";
  } else {
    $key.type = "password";
    $show.textContent = "Show";
  }
});
