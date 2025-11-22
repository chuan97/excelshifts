window.addEventListener("DOMContentLoaded", () => {
  const statusEl = document.getElementById("status-indicator");

  async function checkBackend() {
    try {
      const resp = await fetch("/api/ping");
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      const data = await resp.json();
      console.log("Ping response:", data);
      statusEl.textContent = "Backend: ok";
    } catch (err) {
      console.error("Ping failed:", err);
      statusEl.textContent = "Backend: error";
    }
  }

  checkBackend();
});