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
    byId("newKeyValue").textContent = "";
    byId("newKeyPanel").hidden = true;
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
    byId("statVRAMHint").textContent = stats.gpu_free_reporting === stats.gpu_count && stats.gpu_count > 0
      ? mb(stats.gpu_free_vram_mb) + " free reported (not pooled)" : "Reported total · not shared RAM";
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
        ' · Last seen ' + new Date(d.seen * 1000).toLocaleString() +
        '</div><div class="runtime-details"><strong>Runtime readiness</strong><p>' +
        (d.readiness?.vllm_candidate ? 'vLLM GPU candidate' : 'Not a vLLM GPU node') +
        (d.readiness?.vllm_runtime_verified ? ' · driver/runtime detected' : ' · runtime not verified') +
        '</p><small>' + escapeHtml((d.runtime?.cuda_driver ? 'NVIDIA driver ' + d.runtime.cuda_driver : 'CUDA driver unverified') +
        (d.gpus.some((g) => g.free_memory_mb != null) ? ' · Free GPU VRAM ' +
          mb(d.gpus.reduce((sum, g) => sum + (g.free_memory_mb ?? 0), 0)) : '') +
        (d.runtime?.docker_present ? ' · Docker available' : '') +
        (d.runtime?.rpc_server_present ? ' · RPC server found' : '') +
        (d.runtime?.exo_present ? ' · exo found' : '') +
        (d.runtime?.vllm_version ? ' · vLLM ' + d.runtime.vllm_version : '')) +
        '</small></div><button class="text-button" type="button" data-revoke-device="' +
        escapeHtml(d.id) + '">Revoke device access</button></article>').join("")
      : '<div class="empty">Your connected computers will appear here with live GPU/RAM telemetry.</div>';

    const guidePreviouslySelected = byId("guideDevice").value;
    byId("guideDevice").innerHTML = '<option value="">This / new computer</option>' +
      data.devices.map((d) => '<option value="' + escapeHtml(d.id) + '">' +
        escapeHtml(d.name) + ' · ' + escapeHtml(d.platform) + (d.online ? '' : ' (offline)') +
        '</option>').join("");
    if (data.devices.some((d) => d.id === guidePreviouslySelected))
      byId("guideDevice").value = guidePreviouslySelected;

    byId("planDevices").innerHTML = data.devices.length
      ? data.devices.map((d) => '<label><input type="checkbox" value="' + escapeHtml(d.id) +
        '"> ' + escapeHtml(d.name) + ' · ' + (d.online ? "online" : "offline") + ' · ' +
        d.gpus.length + ' GPU(s)</label>').join("")
      : '<p class="muted">Connect devices first. The planner can still show a no-GPU assessment.</p>';

    const rpcExisting = new Map([...byId("rpcWorkers").querySelectorAll("[data-rpc-endpoint]")]
      .map((input) => [input.dataset.rpcEndpoint, input.value]));
    const rpcSelected = new Set([...byId("rpcWorkers").querySelectorAll("[data-rpc-device]:checked")]
      .map((input) => input.value));
    byId("rpcWorkers").innerHTML = data.devices.length
      ? data.devices.map((d) => '<div class="rpc-line"><label><input type="checkbox" data-rpc-device value="' +
          escapeHtml(d.id) + '" ' + (rpcSelected.has(d.id) ? "checked" : "") +
          '> ' + escapeHtml(d.name) + ' · ' + escapeHtml(d.platform) +
          (d.online ? ' (online)' : ' (offline)') + '</label><input aria-label="RPC endpoint for ' +
          escapeHtml(d.name) + '" data-rpc-endpoint="' + escapeHtml(d.id) +
          '" placeholder="192.168.1.25:50052" value="' +
          escapeHtml(rpcExisting.get(d.id) ?? "") + '"></div>').join("")
      : '<div class="empty">Connect a computer agent before planning RPC workers.</div>';
    byId("backendList").innerHTML = data.backends.length
      ? data.backends.map((b) => '<div class="list-row"><div><div class="list-name">' +
        escapeHtml(b.name) + '</div><div class="list-meta">' + escapeHtml(b.model_id) +
        ' · ' + escapeHtml(b.base_url) + '</div></div><button class="text-button" data-delete="' +
        escapeHtml(b.id) + '" aria-label="Remove backend">Remove</button><button class="text-button" data-test-backend="' +
        escapeHtml(b.id) + '">Test</button></div>').join("")
      : '<div class="empty">No inference backend connected.</div>';
    const selected = byId("chatModel").value;
    byId("chatModel").innerHTML = data.backends.map((b) =>
      '<option value="' + escapeHtml(b.model_id) + '">' + escapeHtml(b.model_id) + '</option>').join("");
    if (data.backends.some((b) => b.model_id === selected)) byId("chatModel").value = selected;
  }

  async function refreshKeys() {
    if (!secret) return;
    const keys = await api("/api/inference-keys");
    byId("inferenceKeyList").innerHTML = keys.length
      ? keys.map((key) => '<div class="list-row"><div><div class="list-name">' +
          escapeHtml(key.name) + '</div><div class="list-meta">' + escapeHtml(key.prefix) +
          '… · created ' + new Date(key.created * 1000).toLocaleString() +
          '</div></div><button class="text-button" data-revoke-key="' +
          escapeHtml(key.id) + '">Revoke</button></div>').join("")
      : '<div class="empty">No scoped inference keys yet.</div>';
  }

  async function refresh() {
    if (!secret || refreshBusy) return;
    refreshBusy = true;
    try {
      render(await api("/api/overview"));
      await refreshKeys();
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
      await refreshKeys();
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
          ['Reported free VRAM', p.reported_free_vram_mb == null ? "Unknown" : mb(p.reported_free_vram_mb)],
          ['Conservative VRAM budget', mb(p.conservative_usable_vram_mb)],
          ['Estimated weight requirement', mb(p.estimated_model_weights_mb)],
          ['Weight estimate within budget', p.likely_fits_weights_only ? "LIKELY" : "NO"]]
          .map((pair) => '<div class="row"><span>' + pair[0] + '</span><b>' + escapeHtml(pair[1]) + '</b></div>').join("") +
        (p.command ? '<div class="command">' + escapeHtml(p.command) + '</div>' : "") +
        (p.blockers.length ? '<div class="info-band">' + p.blockers.map(escapeHtml).join("<br>") + '</div>' : "") +
        '<ul class="warnings">' + p.warnings.map((w) => '<li>' + escapeHtml(w) + '</li>').join("") + '</ul>';
    } catch (err) { toast(err.message); }
  });

  byId("rpcPlanForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const selected = [...byId("rpcWorkers").querySelectorAll("[data-rpc-device]:checked")];
    if (!selected.length) { toast("Select at least one enrolled device."); return; }
    const workers = selected.map((cb) => ({
      device_id: cb.value,
      endpoint: byId("rpcWorkers").querySelector('[data-rpc-endpoint="' + cb.value + '"]').value.trim()
    }));
    try {
      const plan = await api("/api/plans/llama-rpc", "POST", {
        model_id: form.get("model_id"), workers,
        network_acknowledged: byId("rpcAck").checked
      });
      byId("rpcPlanResult").innerHTML =
        '<h3>Experimental RPC topology · ' + plan.worker_count + ' workers</h3>' +
        plan.workers.map((w) =>
          '<div class="row"><span>' + escapeHtml(w.name) + '</span><b>' +
          escapeHtml(w.endpoint) + ' · ' + mb(w.reported_gpu_vram_mb) + ' reported VRAM</b></div>').join("") +
        (plan.command ? '<div class="command">' + escapeHtml(plan.command) + '</div>' : "") +
        (plan.blockers.length ? '<div class="info-band">' + plan.blockers.map(escapeHtml).join("<br>") + '</div>' : "") +
        '<ul class="warnings">' + plan.warnings.map((w) => '<li>' + escapeHtml(w) + '</li>').join("") + '</ul>';
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
    const test = event.target.closest("[data-test-backend]");
    const remove = event.target.closest("[data-delete]");
    try {
      if (test) {
        const report = await api("/api/backends/" + encodeURIComponent(test.dataset.testBackend) + "/health");
        toast("Backend: " + report.status + (report.model_count == null ? "" : " · " + report.model_count + " models") +
          (report.reason ? " · " + report.reason : ""));
      } else if (remove && confirm("Remove this model backend?")) {
        await api("/api/backends/" + encodeURIComponent(remove.dataset.delete), "DELETE");
        await refresh();
        toast("Backend removed.");
      }
    } catch (err) { toast(err.message); }
  });

  byId("deviceGrid").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-revoke-device]");
    if (!button || !confirm("Revoke this device? Its agent will need to enroll again.")) return;
    try {
      await api("/api/devices/" + encodeURIComponent(button.dataset.revokeDevice), "DELETE");
      await refresh();
      toast("Device credentials revoked.");
    } catch (err) { toast(err.message); }
  });

  byId("keyForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const name = new FormData(event.currentTarget).get("name");
      const result = await api("/api/inference-keys", "POST", { name });
      byId("newKeyValue").textContent = result.token;
      byId("newKeyPanel").hidden = false;
      event.currentTarget.reset();
      await refreshKeys();
      toast("Inference-only key created.");
    } catch (err) { toast(err.message); }
  });

  byId("copyInferenceKey").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(byId("newKeyValue").textContent); toast("Key copied."); }
    catch { toast("Copy manually; clipboard access requires a secure origin."); }
  });

  byId("inferenceKeyList").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-revoke-key]");
    if (!button || !confirm("Revoke this inference key immediately?")) return;
    try {
      await api("/api/inference-keys/" + encodeURIComponent(button.dataset.revokeKey), "DELETE");
      byId("newKeyValue").textContent = "";
      byId("newKeyPanel").hidden = true;
      await refreshKeys();
      toast("Inference key revoked.");
    } catch (err) { toast(err.message); }
  });

  byId("chatForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const output = byId("chatOutput");
    output.textContent = "Generating response...";
    const streaming = byId("chatStream").checked;
    const payload = {
      model: form.get("model"),
      messages: [{ role: "user", content: form.get("prompt") }],
      stream: streaming
    };
    try {
      if (!streaming) {
        const result = await api("/v1/chat/completions", "POST", payload);
        output.textContent = result.choices?.[0]?.message?.content ?? JSON.stringify(result, null, 2);
        return;
      }
      const response = await fetch("/v1/chat/completions", {
        method: "POST",
        headers: { Authorization: "Bearer " + secret, "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw Error(data.detail || "Streaming request failed (" + response.status + ")");
      }
      if (!response.body || !response.headers.get("content-type")?.includes("text/event-stream"))
        throw Error("Backend returned no event stream.");
      output.textContent = "";
      let buffer = "", full = "";
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let ended = false;
      while (!ended) {
        const {value, done} = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done }).replace(/\r\n/g, "\n");
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        for (const eventText of events) {
          for (const line of eventText.split("\n")) {
            if (!line.startsWith("data:")) continue;
            const dataText = line.slice(5).trim();
            if (dataText === "[DONE]") { ended = true; break; }
            let chunk;
            try { chunk = JSON.parse(dataText); } catch { continue; }
            const delta = chunk.choices?.[0]?.delta?.content;
            if (typeof delta === "string") full += delta;
            if (chunk.error) throw Error(chunk.error.message || "Upstream stream error.");
          }
          if (ended) break;
        }
        output.textContent = full || (ended ? "(empty response)" : "Generating response...");
        if (done) break;
      }
      if (ended) await reader.cancel();
    } catch (err) { output.textContent += "\n" + err.message; }
  });

  byId("setupGuideForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const params = new URLSearchParams();
    params.set("engine", form.get("engine"));
    params.set("platform_name", form.get("platform_name"));
    if (form.get("device_id")) params.set("device_id", form.get("device_id"));
    const target = byId("setupGuideResult");
    target.textContent = "Preparing checklist...";
    try {
      const guide = await api("/api/setup/guide?" + params);
      target.innerHTML = '<div class="info-band">' +
        (guide.supported ? 'Manual checklist ready. No changes have been made to the device.' :
          '<strong>Unsupported target</strong> ' + guide.blockers.map(escapeHtml).join('; ')) +
        '</div>' +
        guide.steps.map((step, index) =>
          '<section class="guide-step"><div class="eyebrow">STEP ' + (index + 1) +
          ' / ' + guide.steps.length + '</div><h3>' + escapeHtml(step.title) + '</h3><p>' +
          escapeHtml(step.note) + '</p>' +
          (step.command ? '<div class="command">' + escapeHtml(step.command) + '</div>' : '') +
          (step.detected == null ? '' : '<small class="muted">' +
           (step.detected ? 'Dependency reported on selected device' : 'Dependency not detected') +
           '</small>') + '</section>').join('') +
        '<ul class="warnings">' + guide.warnings.map((w) => '<li>' +
        escapeHtml(w) + '</li>').join('') + '</ul>';
    } catch (err) {
      target.textContent = err.message;
    }
  });

  byId("checkDoctor").addEventListener("click", async () => {
    try {
      const d = await api("/api/doctor");
      byId("doctorOutput").textContent = [
        "Controller OS: " + d.os, "Python: " + d.python,
        "Docker: " + (d.docker ? "found" : "not on PATH"),
        "Ray: " + (d.ray ? "found" : "not on PATH"),
        "vLLM: " + (d.vllm ? "found" : "not on PATH"),
        "NVIDIA-SMI: " + (d.nvidia_smi ? "found" : "not on PATH"),
        "Driver version: " + (d.runtime?.cuda_driver || "unverified"),
        "vLLM: " + (d.runtime?.vllm_version || "not installed in controller Python"),
        "Ray: " + (d.runtime?.ray_version || "not installed in controller Python"),
        "llama.cpp RPC: " + (d.runtime?.rpc_server_present ? "binary found" : "not detected"),
        "exo: " + (d.runtime?.exo_present ? "binary found" : "not detected"),
        "Free disk: " + mb(d.runtime?.disk_free_mb), "", d.note
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
