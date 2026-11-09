/* MulDeAIServ dashboard. Secrets are kept in memory, never localStorage. */
(() => {
  "use strict";
  const byId = (id) => document.getElementById(id);
  const escapeHtml = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const mb = (v) => (Number(v || 0) / 1024).toFixed(1) + " GB";
  let secret = "", current = null, joinCommand = "", refreshBusy = false;

  async function api(path, method = "GET", body) {
    const options = { method, headers: { Authorization: "Bearer " + secret } };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    let response;
    try { response = await fetch(path, options); }
    catch { throw Error("Cannot contact the controller."); }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401 && path !== "/api/overview") lock();
      throw Error(typeof data.detail === "string" ? data.detail : "Request failed (" + response.status + ").");
    }
    return data;
  }

  function toast(message) {
    const el = byId("toast");
    el.textContent = message;
    el.classList.add("visible");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => el.classList.remove("visible"), 4400);
  }

  function view(name) {
    document.querySelectorAll("[data-view]").forEach((x) => x.classList.toggle("active", x.dataset.view === name));
    document.querySelectorAll("[data-tab]").forEach((x) => x.classList.toggle("active", x.dataset.tab === name));
    byId("breadcrumb").textContent = {
      overview: "Overview", devices: "Device network", models: "Models & API", setup: "Setup"
    }[name] || name;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function lock() {
    secret = "";
    current = null;
    joinCommand = "";
    byId("authOverlay").hidden = false;
    byId("connection").textContent = "Locked";
    byId("adminToken").value = "";
  }

  function row(title, subtitle, status, symbol = "◈") {
    return '<div class="list-row"><div class="list-left"><div class="item-icon">' + symbol +
      '</div><div><div class="list-name">' + escapeHtml(title) +
      '</div><div class="list-meta">' + escapeHtml(subtitle) +
      '</div></div></div><span class="status ' + (status === "offline" ? "offline" : "") +
      '">' + escapeHtml(status) + '</span></div>';
  }

  function render(data) {
    current = data;
    const stats = data.stats;
    byId("statNodes").textContent = stats.online_devices + " / " + stats.total_devices;
    byId("statNodesHint").textContent = stats.online_devices + " nodes actively reporting";
    byId("statVRAM").textContent = mb(stats.gpu_vram_mb);
    byId("statRAM").textContent = mb(stats.cpu_ram_mb);
    byId("statModels").textContent = stats.backends;
    byId("deviceTotal").textContent = data.devices.length + " registered";

    byId("overviewDevices").innerHTML = data.devices.length
      ? data.devices.slice(0, 5).map((d) =>
        row(d.name, d.platform + " · " + d.gpus.length + " GPU(s) · " + mb(d.ram_mb) + " RAM",
          d.online ? "online" : "offline", "⌘")).join("")
      : '<div class="empty">No devices yet. Generate a join token to connect your first worker.</div>';
    byId("overviewBackends").innerHTML = data.backends.length
      ? data.backends.slice(0, 5).map((b) => row(b.name, b.model_id, b.kind, "◈")).join("")
      : '<div class="empty">No models registered. Connect vLLM or Ollama to create your first endpoint.</div>';

    byId("deviceGrid").innerHTML = data.devices.length
      ? data.devices.map((d) => '<article class="device-card"><div class="device-heading"><h3>' +
        escapeHtml(d.name) + '</h3><span class="status ' + (d.online ? "" : "offline") + '">' +
        (d.online ? "ONLINE" : "OFFLINE") + '</span></div><div class="list-meta">' +
        escapeHtml(d.os_version) + '</div><div class="device-specs"><div class="spec"><small>SYSTEM RAM</small><strong>' +
        mb(d.ram_mb) + '</strong></div><div class="spec"><small>GPU VRAM</small><strong>' +
        mb(d.gpus.reduce((a, g) => a + g.memory_mb, 0)) +
        '</strong></div><div class="spec"><small>PROCESSORS</small><strong>' +
        Number(d.cpu_count) + '</strong></div><div class="spec"><small>GPUs</small><strong>' +
        d.gpus.length + '</strong></div></div><div class="device-foot">' +
        (d.gpus.length ? escapeHtml(d.gpus.map((g) => g.name).join(", ")) : "CPU-only device") +
        ' · Last seen ' + new Date(d.seen * 1000).toLocaleString() + '</div></article>').join("")
      : '<div class="empty">Your connected computers will appear here with live GPU/RAM telemetry.</div>';

    byId("planDevices").innerHTML = data.devices.length
      ? data.devices.map((d) => '<label><input type="checkbox" value="' + escapeHtml(d.id) +
        '"> ' + escapeHtml(d.name) + ' · ' + (d.online ? "online" : "offline") + ' · ' +
        d.gpus.length + ' GPU(s)</label>').join("")
      : '<p class="muted">Connect devices first. The planner can still show a no-GPU assessment.</p>';

    byId("backendList").innerHTML = data.backends.length
      ? data.backends.map((b) => '<div class="list-row"><div><div class="list-name">' +
        escapeHtml(b.name) + '</div><div class="list-meta">' + escapeHtml(b.model_id) +
        ' · ' + escapeHtml(b.base_url) + '</div></div><button class="text-button" data-delete="' +
        escapeHtml(b.id) + '" aria-label="Remove backend">Remove</button></div>').join("")
      : '<div class="empty">No inference backend connected.</div>';
    const selected = byId("chatModel").value;
    byId("chatModel").innerHTML = data.backends.map((b) =>
      '<option value="' + escapeHtml(b.model_id) + '">' + escapeHtml(b.model_id) + '</option>').join("");
    if (data.backends.some((b) => b.model_id === selected)) byId("chatModel").value = selected;
  }

  async function refresh() {
    if (!secret || refreshBusy) return;
    refreshBusy = true;
    try {
      render(await api("/api/overview"));
      byId("connection").textContent = "Controller connected";
    } catch (err) {
      byId("connection").textContent = "Connection failed";
      toast(err.message);
    } finally { refreshBusy = false; }
  }

  document.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => view(b.dataset.tab)));
  document.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => view(b.dataset.go)));
  byId("refreshButton").addEventListener("click", refresh);
  byId("lockButton").addEventListener("click", lock);

  byId("authForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    secret = byId("adminToken").value.trim();
    byId("authError").textContent = "";
    try {
      const data = await api("/api/overview");
      render(data);
      byId("authOverlay").hidden = true;
      byId("adminToken").value = "";
      byId("connection").textContent = "Controller connected";
    } catch (err) {
      byId("authError").textContent = err.message;
      secret = "";
    }
  });

  byId("createJoin").addEventListener("click", async () => {
    try {
      const result = await api("/api/join-tokens", "POST", { expires_minutes: 15 });
      joinCommand = "python -m muldeaiserv.agent --server " +
        location.origin + " --join-token " + result.token;
      byId("joinCommand").textContent = joinCommand;
      byId("joinPanel").hidden = false;
      toast("Single-use enrollment token created. It expires in 15 minutes.");
    } catch (err) { toast(err.message); }
  });

  byId("copyJoin").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(joinCommand); toast("Command copied."); }
    catch { toast("Clipboard requires HTTPS or localhost. Select and copy the command manually."); }
  });

  byId("planForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const ids = [...byId("planDevices").querySelectorAll('input[type="checkbox"]:checked')].map((x) => x.value);
    try {
      const p = await api("/api/plans", "POST", {
        model_id: String(form.get("model_id")).trim(),
        parameters_b: Number(form.get("parameters_b")),
        quantization_bits: Number(form.get("quantization_bits")),
        device_ids: ids.length ? ids : null
      });
      byId("planResult").innerHTML = '<h3>Deployment estimate</h3>' +
        [['Selected nodes', p.node_count], ['Available GPUs', p.gpu_count],
          ['Reported VRAM', mb(p.total_gpu_vram_mb)],
          ['Conservative VRAM budget', mb(p.conservative_usable_vram_mb)],
          ['Estimated weight requirement', mb(p.estimated_model_weights_mb)],
          ['Weight estimate within budget', p.likely_fits_weights_only ? "LIKELY" : "NO"]]
          .map((pair) => '<div class="row"><span>' + pair[0] + '</span><b>' + escapeHtml(pair[1]) + '</b></div>').join("") +
        (p.command ? '<div class="command">' + escapeHtml(p.command) + '</div>' : "") +
        (p.blockers.length ? '<div class="info-band">' + p.blockers.map(escapeHtml).join("<br>") + '</div>' : "") +
        '<ul class="warnings">' + p.warnings.map((w) => '<li>' + escapeHtml(w) + '</li>').join("") + '</ul>';
    } catch (err) { toast(err.message); }
  });

  byId("backendForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api("/api/backends", "POST", Object.fromEntries(form));
      event.currentTarget.reset();
      await refresh();
      toast("Backend registered. The endpoint can now be used through the gateway.");
    } catch (err) { toast(err.message); }
  });

  byId("backendList").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-delete]");
    if (!button) return;
    try {
      await api("/api/backends/" + encodeURIComponent(button.dataset.delete), "DELETE");
      await refresh();
      toast("Backend removed.");
    } catch (err) { toast(err.message); }
  });

  byId("chatForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const output = byId("chatOutput");
    output.textContent = "Generating response...";
    try {
      const result = await api("/v1/chat/completions", "POST", {
        model: form.get("model"),
        messages: [{ role: "user", content: form.get("prompt") }],
        stream: false
      });
      output.textContent = result.choices?.[0]?.message?.content ?? JSON.stringify(result, null, 2);
    } catch (err) { output.textContent = err.message; }
  });

  byId("checkDoctor").addEventListener("click", async () => {
    try {
      const d = await api("/api/doctor");
      byId("doctorOutput").textContent = [
        "Controller OS: " + d.os, "Python: " + d.python,
        "Docker: " + (d.docker ? "found" : "not on PATH"),
        "Ray: " + (d.ray ? "found" : "not on PATH"),
        "vLLM: " + (d.vllm ? "found" : "not on PATH"),
        "NVIDIA-SMI: " + (d.nvidia_smi ? "found" : "not on PATH"), "", d.note
      ].join("\n");
    } catch (err) { toast(err.message); }
  });

  fetch("/api/health").then((r) => r.json()).then((d) => {
    byId("connection").textContent = d.configured ? "Locked" : "Needs admin token";
    if (!d.configured) byId("authError").textContent =
      "Set MULDEAI_ADMIN_TOKEN on the server or start it with the CLI for a temporary token.";
  }).catch(() => byId("connection").textContent = "Offline");
  setInterval(refresh, 15000);
})();
