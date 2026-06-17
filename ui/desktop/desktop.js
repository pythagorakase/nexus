const status = document.getElementById("status");
const detail = document.getElementById("detail");

window.__nexusDesktopStatus = (label, message) => {
  status.textContent = label;
  detail.textContent = message || "";
};

window.__nexusDesktopReady = (origin, runtimeStatus) => {
  const slot = runtimeStatus?.slot ?? "?";
  status.textContent = "Runtime ready";
  detail.textContent = `${origin} - slot ${slot}`;
};
