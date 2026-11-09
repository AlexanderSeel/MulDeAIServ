/* MulDeAIServ AI Studio — real, authenticated, persistent multi-turn chat.
 * Untrusted model text is rendered as textContent, never injected as HTML.
 */
(() => {
  "use strict";

  const el = (id) => document.getElementById(id);
  const ui = {
    list: el("studioConversations"),
    search: el("studioSearch"),
    newChat: el("studioNew"),
    clear: el("studioClearChat"),
    messages: el("studioMessages"),
    welcome: el("studioWelcome"),
    feed: el("studioFeed"),
    model: el("studioModel"),
    status: el("studioStatus"),
    rename: el("studioRename"),
    export: el("studioExport"),
    prompt: el("studioPrompt"),
    form: el("studioComposer"),
    send: el("studioSend"),
    stop: el("studioStop"),
    settingsToggle: el("studioSettingsToggle"),
    settings: el("studioSettings"),
    system: el("studioSystemPrompt"),
    temperature: el("studioTemperature"),
    tempValue: el("studioTempValue"),
    maxTokens: el("studioMaxTokens"),
    streaming: el("studioStreaming"),
    notice: el("studioNotice")
  };
  if (!ui.list || !ui.form) return;

  const state = {
    unlocked: false,
    conversations: [],
    backends: [],
    active: null,
    messages: [],
    running: false,
    aborter: null,
    sequence: 0
  };
  const api = (path, method = "GET", body) => {
    if (!window.MulDeAI) throw Error("Controller UI is not ready.");
    return window.MulDeAI.request(path, method, body);
  };

  function status(message, isError = false) {
    ui.notice.textContent = message || "";
    ui.notice.hidden = !message;
    ui.notice.style.borderColor = isError ? "#9c5862" : "#386879";
    ui.notice.style.color = isError ? "#ffcfcb" : "#a1eee1";
    if (!message) ui.notice.removeAttribute("role");
    else ui.notice.setAttribute("role", isError ? "alert" : "status");
  }

  function setRunning(value) {
    state.running = Boolean(value);
    ui.send.hidden = state.running;
    ui.stop.hidden = !state.running;
    ui.send.disabled = state.running || !state.unlocked || !ui.model.value;
    ui.model.disabled = state.running || state.backends.length === 0;
    ui.newChat.disabled = state.running;
    ui.rename.disabled = state.running || !state.active;
    ui.export.disabled = state.running || !state.messages.length;
    ui.prompt.disabled = state.running || !state.unlocked;
  }

  function compact(text, length = 64) {
    const clean = String(text || "").replace(/\s+/g, " ").trim();
    return clean.length > length ? clean.slice(0, length - 1) + "…" : clean;
  }

  function formatTime(seconds) {
    if (!seconds) return "";
    const date = new Date(seconds * 1000);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
    });
  }

  function scrollEnd() {
    requestAnimationFrame(() => {
      ui.feed.scrollTop = ui.feed.scrollHeight;
    });
  }

  function appendPlain(parent, text) {
    if (!text) return;
    const block = document.createElement("div");
    block.className = "studio-text";
    block.textContent = text;
    parent.append(block);
  }

  function renderContent(parent, value) {
    const content = String(value ?? "");
    parent.replaceChildren();
    // Recognize fenced code without interpreting any untrusted HTML.
    const fence = /\x60{3}([^\n\x60]*)\n([\s\S]*?)\x60{3}/g;
    let offset = 0;
    let match;
    while ((match = fence.exec(content)) !== null) {
      appendPlain(parent, content.slice(offset, match.index));
      const label = document.createElement("small");
      label.className = "studio-code-label";
      label.textContent = match[1].trim() || "code";
      const pre = document.createElement("pre");
      const code = document.createElement("code");
      code.textContent = match[2];
      pre.append(code);
      parent.append(label, pre);
      offset = fence.lastIndex;
    }
    appendPlain(parent, content.slice(offset));
  }

  function copyText(value) {
    if (!navigator.clipboard || !navigator.clipboard.writeText) {
      status("Copy needs clipboard permission and HTTPS or localhost.", true);
      return;
    }
    navigator.clipboard.writeText(value)
      .then(() => status("Copied to clipboard."))
      .catch(() => status("Clipboard unavailable in this browser.", true));
  }

  function messageElement(message, temporary = false) {
    const article = document.createElement("article");
    const isUser = message.role === "user";
    article.className = "studio-message " + (isUser ? "user" : "assistant");
    const avatar = document.createElement("div");
    avatar.className = "studio-message-avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = isUser ? "Y" : "✳";

    const body = document.createElement("div");
    body.className = "studio-message-body";
    const meta = document.createElement("div");
    meta.className = "studio-message-meta";
    const who = document.createElement("span");
    who.textContent = isUser ? "YOU" : "LOCAL AI";
    const at = document.createElement("span");
    at.textContent = temporary ? "Generating…" : formatTime(message.created);
    meta.append(who, at);

    const bubble = document.createElement("div");
    bubble.className = "studio-message-bubble";
    const content = document.createElement("div");
    content.className = "studio-message-content";
    renderContent(content, message.content);
    bubble.append(content);
    const tools = document.createElement("div");
    tools.className = "studio-message-tools";
    const copy = document.createElement("button");
    copy.type = "button";
    copy.textContent = "Copy";
    copy.setAttribute("aria-label", "Copy " + (isUser ? "your message" : "AI response"));
    copy.addEventListener("click", () => copyText(message.content));
    tools.append(copy);
    if (temporary) tools.hidden = true;
    body.append(meta, bubble, tools);
    article.append(avatar, body);
    ui.messages.append(article);
    scrollEnd();
    return { article, content, meta: at, copy };
  }

  function renderMessages() {
    ui.messages.replaceChildren();
    ui.welcome.hidden = state.messages.length > 0;
    for (const message of state.messages) messageElement(message);
    scrollEnd();
    setRunning(state.running);
  }

  function newChat() {
    if (state.running) {
      status("Stop the current response before switching conversations.", true);
      return;
    }
    state.sequence += 1;
    state.active = null;
    state.messages = [];
    ui.system.value = "";
    ui.temperature.value = "0.7";
    ui.tempValue.textContent = "0.7";
    ui.prompt.value = "";
    ui.search.value = "";
    status("");
    renderList();
    renderMessages();
    ui.prompt.focus();
  }

  function renderList() {
    const filter = ui.search.value.trim().toLowerCase();
    const items = state.conversations.filter((chat) =>
      chat.title.toLowerCase().includes(filter) ||
      chat.model_id.toLowerCase().includes(filter));
    ui.list.replaceChildren();
    if (!state.unlocked || items.length === 0) {
      const empty = document.createElement("div");
      empty.className = "studio-history-empty";
      empty.textContent = !state.unlocked ? "Unlock the dashboard to load saved chats." :
        filter ? "No matching conversations." : "Your conversations will appear here.";
      ui.list.append(empty);
      return;
    }
    for (const chat of items) {
      const item = document.createElement("div");
      item.className = "studio-conversation-item" +
        (state.active?.id === chat.id ? " active" : "");
      const open = document.createElement("button");
      open.type = "button";
      open.className = "studio-conversation-open";
      open.title = chat.title;
      open.setAttribute("aria-current", state.active?.id === chat.id ? "page" : "false");
      const title = document.createElement("strong");
      title.textContent = chat.title;
      const subtitle = document.createElement("small");
      subtitle.textContent = compact(chat.model_id, 23) + " · " + formatTime(chat.updated);
      open.append(title, subtitle);
      open.addEventListener("click", () => openConversation(chat.id));
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "studio-history-trash";
      remove.textContent = "×";
      remove.title = "Delete this conversation";
      remove.setAttribute("aria-label", "Delete " + chat.title);
      remove.addEventListener("click", (event) => {
        event.stopPropagation();
        deleteConversation(chat.id, chat.title);
      });
      item.append(open, remove);
      ui.list.append(item);
    }
  }

  async function refreshHistory() {
    if (!state.unlocked) return;
    state.conversations = await api("/api/studio/conversations");
    renderList();
  }

  function setModels(backends) {
    state.backends = Array.isArray(backends) ? backends.filter((b) => b.model_id) : [];
    const selected = ui.model.value;
    const sessionModel = state.active?.model_id;
    ui.model.replaceChildren();
    if (state.backends.length === 0) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No model registered";
      ui.model.append(option);
      ui.status.textContent = "Register a model first";
      setRunning(state.running);
      return;
    }
    for (const backend of state.backends) {
      const option = document.createElement("option");
      option.value = backend.model_id;
      option.textContent = (backend.name ? backend.name + " · " : "") + backend.model_id;
      ui.model.append(option);
    }
    const available = (v) => state.backends.some((b) => b.model_id === v);
    ui.model.value = available(sessionModel) ? sessionModel :
      available(selected) ? selected : state.backends[0].model_id;
    ui.status.textContent = state.backends.length + " registered model" +
      (state.backends.length === 1 ? "" : "s");
    setRunning(state.running);
  }

  async function openConversation(id) {
    if (state.running) {
      status("Stop generation before opening another chat.", true);
      return;
    }
    const sequence = ++state.sequence;
    try {
      const result = await api("/api/studio/conversations/" + encodeURIComponent(id));
      if (sequence !== state.sequence || !state.unlocked) return;
      state.active = result;
      state.messages = result.messages || [];
      ui.system.value = result.system_prompt || "";
      ui.temperature.value = String(result.temperature ?? 0.7);
      ui.tempValue.textContent = Number(ui.temperature.value).toFixed(1);
      ui.prompt.value = "";
      status("");
      setModels(state.backends);
      renderList();
      renderMessages();
    } catch (error) {
      status(error.message, true);
    }
  }

  async function deleteConversation(id, title) {
    if (state.running) {
      status("Stop the active response before deleting a conversation.", true);
      return;
    }
    if (!window.confirm("Delete \"" + title + "\" and all its messages from this controller?")) return;
    try {
      await api("/api/studio/conversations/" + encodeURIComponent(id), "DELETE");
      if (state.active?.id === id) newChat();
      await refreshHistory();
      status("Conversation deleted.");
    } catch (error) {
      status(error.message, true);
    }
  }

  async function renameConversation() {
    if (!state.active || state.running) return;
    const title = window.prompt("Rename conversation", state.active.title);
    if (title === null) return;
    if (!title.trim() || title.trim().length > 120) {
      status("Please use a title between 1 and 120 characters.", true);
      return;
    }
    try {
      state.active = await api(
        "/api/studio/conversations/" + encodeURIComponent(state.active.id),
        "PATCH", { title: title.trim() }
      );
      state.messages = state.active.messages || state.messages;
      await refreshHistory();
      status("Conversation renamed.");
    } catch (error) { status(error.message, true); }
  }

  function exportConversation() {
    if (!state.active || !state.messages.length) {
      status("Open a conversation with messages before exporting.", true);
      return;
    }
    const lines = ["# " + state.active.title, "",
      "Model: " + state.active.model_id,
      "Exported from MulDeAIServ AI Studio.", ""];
    for (const message of state.messages) {
      lines.push("## " + (message.role === "user" ? "You" : "AI"),
                 "", message.content, "");
    }
    const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = (state.active.title.replace(/[^a-zA-Z0-9_.-]+/g, "-")
      .slice(0, 70) || "ai-chat") + ".md";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 500);
    status("Conversation exported as Markdown.");
  }

  function extractContent(result) {
    const content = result?.choices?.[0]?.message?.content;
    if (typeof content === "string") return content;
    if (Array.isArray(content)) return content
      .filter((item) => item && item.type === "text" && typeof item.text === "string")
      .map((item) => item.text).join("");
    return "";
  }

  async function streamCompletion(body, onChange, signal) {
    const response = await window.MulDeAI.streamChat(body, signal);
    if (!response.body || !response.headers.get("content-type")?.includes("text/event-stream"))
      throw Error("This model did not return an SSE stream. Disable streaming in Settings.");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let text = "";
    let complete = false;
    try {
      while (!complete) {
        const part = await reader.read();
        buffer += decoder.decode(part.value || new Uint8Array(), { stream: !part.done });
        buffer = buffer.replace(/\r\n/g, "\n");
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        for (const block of events) {
          const data = block.split("\n").filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5).trim()).join("\n");
          if (!data) continue;
          if (data === "[DONE]") { complete = true; break; }
          let event;
          try { event = JSON.parse(data); }
          catch { continue; }
          if (event.error) throw Error(event.error.message || "Model stream returned an error.");
          const delta = event.choices?.[0]?.delta?.content;
          if (typeof delta === "string") {
            text += delta;
            onChange(text);
          }
        }
        if (part.done) break;
      }
    } finally {
      if (complete) await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
    return text;
  }

  async function sendPrompt(event) {
    event.preventDefault();
    if (!state.unlocked || state.running) return;
    const prompt = ui.prompt.value.trim();
    const modelId = ui.model.value;
    if (!prompt) return;
    if (!modelId) {
      status("No AI model is registered yet. Open Models & API to add one.", true);
      return;
    }
    const temperature = Number(ui.temperature.value);
    const maxTokens = Number(ui.maxTokens.value);
    if (!Number.isInteger(maxTokens) || maxTokens < 64 || maxTokens > 8192) {
      status("Max output tokens must be between 64 and 8192.", true);
      return;
    }
    status("");
    const sequence = ++state.sequence;
    setRunning(true);
    ui.prompt.value = "";
    let partialNode = null;
    try {
      if (!state.active) {
        state.active = await api("/api/studio/conversations", "POST", {
          title: compact(prompt, 72),
          model_id: modelId,
          system_prompt: ui.system.value,
          temperature
        });
        state.messages = [];
        await refreshHistory();
      } else {
        state.active = await api(
          "/api/studio/conversations/" + encodeURIComponent(state.active.id),
          "PATCH", {
            model_id: modelId,
            system_prompt: ui.system.value,
            temperature
          }
        );
        state.messages = state.active.messages || [];
      }
      if (sequence !== state.sequence) return;
      const sent = await api(
        "/api/studio/conversations/" + encodeURIComponent(state.active.id) + "/messages",
        "POST", { role: "user", content: prompt }
      );
      state.messages.push(sent);
      renderMessages();
      ui.welcome.hidden = true;

      const context = state.messages.slice(-40).map((message) => ({
        role: message.role, content: message.content
      }));
      if (ui.system.value.trim()) context.unshift({
        role: "system", content: ui.system.value.trim()
      });
      const streaming = ui.streaming.checked;
      const payload = {
        model: modelId,
        messages: context,
        temperature,
        max_tokens: maxTokens,
        stream: streaming
      };
      let answer;
      partialNode = messageElement({
        role: "assistant", content: "", created: Date.now() / 1000
      }, true);
      if (streaming) {
        const controller = new AbortController();
        state.aborter = controller;
        answer = await streamCompletion(payload, (partial) => {
          partialNode.content.textContent = partial;
          scrollEnd();
        }, controller.signal);
      } else {
        const result = await api("/v1/chat/completions", "POST", payload);
        answer = extractContent(result);
      }
      if (!answer || !answer.trim()) {
        throw Error("The selected model returned an empty response.");
      }
      if (sequence !== state.sequence) return;
      const saved = await api(
        "/api/studio/conversations/" + encodeURIComponent(state.active.id) + "/messages",
        "POST", { role: "assistant", content: answer }
      );
      state.messages.push(saved);
      renderMessages();
      await refreshHistory();
    } catch (error) {
      const aborted = error.name === "AbortError";
      if (partialNode) {
        const partial = partialNode.content.textContent;
        partialNode.meta.textContent = aborted ? "Stopped" : "Incomplete response";
        if (!partial) {
          partialNode.content.textContent = aborted ? "Generation stopped." : "No response received.";
        }
      }
      status(aborted ? "Generation stopped. A partial response was not saved." :
        "Could not complete the response: " + error.message, !aborted);
    } finally {
      state.aborter = null;
      setRunning(false);
      ui.prompt.focus();
    }
  }

  function stopResponse() {
    if (state.aborter) state.aborter.abort();
    else status("Response preparation is in progress; retry when it finishes.");
  }

  function clearForLock() {
    state.unlocked = false;
    if (state.aborter) state.aborter.abort();
    state.sequence += 1;
    state.active = null;
    state.messages = [];
    state.conversations = [];
    ui.prompt.value = "";
    ui.system.value = "";
    ui.search.value = "";
    ui.welcome.hidden = false;
    ui.messages.replaceChildren();
    state.running = false;
    state.aborter = null;
    setRunning(false);
    status("");
    renderList();
  }

  async function initializeAfterUnlock() {
    state.unlocked = true;
    setRunning(false);
    try {
      await refreshHistory();
      status("");
    } catch (error) {
      status("Unable to load saved conversations: " + error.message, true);
    }
  }

  ui.newChat.addEventListener("click", newChat);
  ui.clear.addEventListener("click", () => {
    if (state.active) deleteConversation(state.active.id, state.active.title);
    else newChat();
  });
  ui.search.addEventListener("input", renderList);
  ui.rename.addEventListener("click", renameConversation);
  ui.export.addEventListener("click", exportConversation);
  ui.form.addEventListener("submit", sendPrompt);
  ui.stop.addEventListener("click", stopResponse);
  ui.model.addEventListener("change", async () => {
    if (!state.active || state.running) return;
    try {
      state.active = await api(
        "/api/studio/conversations/" + encodeURIComponent(state.active.id), "PATCH",
        { model_id: ui.model.value }
      );
      state.messages = state.active.messages || [];
      await refreshHistory();
    } catch (error) { status(error.message, true); }
  });
  ui.temperature.addEventListener("input", () => {
    ui.tempValue.textContent = Number(ui.temperature.value).toFixed(1);
  });
  ui.settingsToggle.addEventListener("click", () => {
    ui.settings.hidden = !ui.settings.hidden;
    ui.settingsToggle.setAttribute("aria-expanded", String(!ui.settings.hidden));
  });
  ui.prompt.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      ui.form.requestSubmit();
    }
  });
  document.querySelectorAll("[data-starter]").forEach((button) => {
    button.addEventListener("click", () => {
      ui.prompt.value = button.dataset.starter;
      ui.prompt.focus();
      if (!ui.model.value) status("Register a model under Models & API to use this prompt.", true);
      else status("");
    });
  });

  window.addEventListener("muldeai:models", (event) => setModels(event.detail));
  window.addEventListener("muldeai:unlocked", initializeAfterUnlock);
  window.addEventListener("muldeai:locked", clearForLock);
  window.addEventListener("muldeai:view", (event) => {
    if (event.detail === "studio" && state.unlocked) {
      refreshHistory().catch((error) => status(error.message, true));
    }
  });

  setRunning(false);
})();
