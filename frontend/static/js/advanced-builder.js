const DEFAULT_PAYLOAD = {
  flags: 32768,
  components: [
    {
      type: 17,
      components: [
        {
          type: 10,
          content: "Welcome to DailyBread. Create a polished Discord Components V2 message.",
        },
      ],
    },
  ],
};

const state = {
  selectedContainerId: null,
  payload: structuredClone(DEFAULT_PAYLOAD),
  savedContainers: [],
};

const createElement = (tag, attrs = {}, text = "") => {
  const el = document.createElement(tag);
  Object.entries(attrs).forEach(([key, value]) => {
    if (value === true) el.setAttribute(key, "");
    else if (value !== false && value != null) el.setAttribute(key, value);
  });
  if (text) el.textContent = text;
  return el;
};

const showAlert = (message, variant = "info") => {
  const alert = createElement("div", {
    class: `rounded-2xl border px-4 py-3 text-sm font-semibold ${variant === "error" ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`,
  }, message);
  const container = document.getElementById("container-alert");
  if (!container) return;
  container.innerHTML = "";
  container.appendChild(alert);
  window.setTimeout(() => {
    if (alert.parentElement) alert.parentElement.removeChild(alert);
  }, 5000);
};

const debounce = (fn, wait = 180) => {
  let timeout = null;
  return (...args) => {
    if (timeout) window.clearTimeout(timeout);
    timeout = window.setTimeout(() => fn(...args), wait);
  };
};

const getRoot = () => state.payload.components?.[0] || null;
const getChildren = () => getRoot()?.components || [];
const serializePayload = () => ({ flags: 32768, components: state.payload.components || [] });

const renderPreview = debounce(() => {
  const preview = document.getElementById("container-preview");
  const json = document.getElementById("container-json");
  if (preview) {
    preview.innerHTML = "";
    preview.appendChild(renderDiscordPreview(state.payload));
  }
  if (json) {
    json.textContent = JSON.stringify(serializePayload(), null, 2);
  }
});

const renderDiscordPreview = (payload) => {
  const shell = createElement("div", { class: "space-y-3" });
  (payload.components || []).forEach((component) => shell.appendChild(renderComponentPreview(component)));
  return shell;
};

const renderComponentPreview = (component) => {
  const card = createElement("div", { class: "rounded-[1.25rem] border border-bread-border bg-white p-3 shadow-sm" });
  if (component.type === 17) {
    card.appendChild(createElement("div", { class: "mb-2 text-xs font-bold uppercase tracking-[0.2em] text-bread-muted" }, "Container"));
    const children = createElement("div", { class: "space-y-2" });
    (component.components || []).forEach((child) => children.appendChild(renderComponentPreview(child)));
    card.appendChild(children);
  } else if (component.type === 10) {
    card.appendChild(createElement("div", { class: "text-sm leading-7 text-bread-ink" }, component.content || ""));
  } else if (component.type === 9) {
    const row = createElement("div", { class: "flex items-start justify-between gap-3" });
    row.appendChild(createElement("div", { class: "text-sm font-semibold text-bread-ink" }, component.text || "Section"));
    if (component.accessory) row.appendChild(createElement("div", { class: "rounded-full bg-bread-background px-3 py-1 text-xs text-bread-muted" }, "Accessory"));
    card.appendChild(row);
  } else if (component.type === 12) {
    const list = createElement("div", { class: "space-y-2" });
    (component.items || []).forEach((item) => {
      const image = createElement("img", { class: "h-24 w-full rounded-xl object-cover", src: item.media?.url || "", alt: "media" });
      list.appendChild(image);
    });
    card.appendChild(list);
  } else if (component.type === 14) {
    card.appendChild(createElement("div", { class: "h-px w-full bg-bread-border" }));
  } else if (component.type === 2) {
    card.appendChild(createElement("button", { class: "rounded-2xl bg-bread-gold px-3 py-2 text-sm font-semibold text-white" }, component.label || "Button"));
  }
  return card;
};

const renderEditor = () => {
  const componentList = document.getElementById("container-components");
  if (!componentList) return;
  componentList.innerHTML = "";
  const root = getRoot();
  if (!root) {
    componentList.appendChild(createElement("p", { class: "rounded-2xl border border-dashed border-bread-border bg-bread-background p-4 text-sm text-bread-muted" }, "Add a container to begin."));
    return;
  }

  getChildren().forEach((component, index) => componentList.appendChild(renderComponentEditor(component, index)));
};

const renderComponentEditor = (component, index) => {
  const card = createElement("div", { class: "rounded-[1.5rem] border border-bread-border bg-white/95 p-4 shadow-sm" });
  const header = createElement("div", { class: "mb-4 flex items-center justify-between gap-3" });
  header.appendChild(createElement("h3", { class: "text-sm font-semibold text-bread-ink" }, getComponentLabel(component)));
  const actions = createElement("div", { class: "flex gap-2" });
  const removeButton = createElement("button", { class: "rounded-full border border-red-200 bg-red-50 px-3 py-1 text-xs font-semibold text-red-700" }, "Remove");
  removeButton.addEventListener("click", () => {
    getChildren().splice(index, 1);
    renderEditor();
    renderPreview();
  });
  actions.appendChild(removeButton);
  header.appendChild(actions);
  card.appendChild(header);

  if (component.type === 10) {
    const field = createElement("label", { class: "flex flex-col gap-2 text-sm text-bread-ink" });
    field.innerHTML = '<span class="font-semibold">Content</span>';
    const textarea = createElement("textarea", { class: "min-h-[130px] rounded-2xl border border-bread-border bg-bread-background p-3 text-sm text-bread-ink outline-none" });
    textarea.value = component.content || "";
    textarea.addEventListener("input", () => {
      component.content = textarea.value;
      renderPreview();
    });
    field.appendChild(textarea);
    card.appendChild(field);
  }

  if (component.type === 9) {
    const field = createElement("label", { class: "flex flex-col gap-2 text-sm text-bread-ink" });
    field.innerHTML = '<span class="font-semibold">Section text</span>';
    const textarea = createElement("textarea", { class: "min-h-[100px] rounded-2xl border border-bread-border bg-bread-background p-3 text-sm text-bread-ink outline-none" });
    textarea.value = component.text || "";
    textarea.addEventListener("input", () => {
      component.text = textarea.value;
      renderPreview();
    });
    field.appendChild(textarea);
    card.appendChild(field);
  }

  if (component.type === 12) {
    const wrap = createElement("div", { class: "space-y-3" });
    (component.items || []).forEach((item) => {
      const row = createElement("div", { class: "rounded-2xl border border-bread-border bg-bread-background p-3" });
      const input = createElement("input", { class: "w-full rounded-2xl border border-bread-border bg-white px-3 py-2 text-sm text-bread-ink outline-none", placeholder: "https://example.com/image.png" });
      input.value = item.media?.url || "";
      input.addEventListener("input", () => {
        item.media = item.media || {};
        item.media.url = input.value;
        renderPreview();
      });
      row.appendChild(input);
      wrap.appendChild(row);
    });
    card.appendChild(wrap);
  }

  if (component.type === 2) {
    const fields = createElement("div", { class: "space-y-3" });
    const labelField = createElement("label", { class: "flex flex-col gap-2 text-sm text-bread-ink" });
    labelField.innerHTML = '<span class="font-semibold">Label</span>';
    const labelInput = createElement("input", { class: "rounded-2xl border border-bread-border bg-bread-background px-3 py-2 text-sm text-bread-ink outline-none" });
    labelInput.value = component.label || "";
    labelInput.addEventListener("input", () => {
      component.label = labelInput.value;
      renderPreview();
    });
    labelField.appendChild(labelInput);
    fields.appendChild(labelField);

    const styleField = createElement("label", { class: "flex flex-col gap-2 text-sm text-bread-ink" });
    styleField.innerHTML = '<span class="font-semibold">Style</span>';
    const styleSelect = createElement("select", { class: "rounded-2xl border border-bread-border bg-bread-background px-3 py-2 text-sm text-bread-ink outline-none" });
    [
      [1, "Primary"],
      [2, "Secondary"],
      [3, "Success"],
      [4, "Danger"],
      [5, "Link"],
    ].forEach(([value, label]) => {
      const option = createElement("option", { value }, label);
      if (String(component.style || 1) === String(value)) option.selected = true;
      styleSelect.appendChild(option);
    });
    styleSelect.addEventListener("change", () => {
      component.style = Number(styleSelect.value);
      renderPreview();
    });
    styleField.appendChild(styleSelect);
    fields.appendChild(styleField);

    const actionField = createElement("label", { class: "flex flex-col gap-2 text-sm text-bread-ink" });
    actionField.innerHTML = '<span class="font-semibold">Action</span>';
    const actionSelect = createElement("select", { class: "rounded-2xl border border-bread-border bg-bread-background px-3 py-2 text-sm text-bread-ink outline-none" });
    actionSelect.appendChild(createElement("option", { value: "url" }, "URL"));
    actionSelect.appendChild(createElement("option", { value: "custom_id" }, "Custom ID"));
    if ((component.action || "url") === "url") actionSelect.firstChild.selected = true; else actionSelect.lastChild.selected = true;
    actionSelect.addEventListener("change", () => {
      component.action = actionSelect.value;
      renderPreview();
    });
    actionField.appendChild(actionSelect);
    fields.appendChild(actionField);

    const targetField = createElement("label", { class: "flex flex-col gap-2 text-sm text-bread-ink" });
    targetField.innerHTML = '<span class="font-semibold">Target</span>';
    const targetInput = createElement("input", { class: "rounded-2xl border border-bread-border bg-bread-background px-3 py-2 text-sm text-bread-ink outline-none" });
    targetInput.value = (component.action === "custom_id" ? component.custom_id : component.url) || "";
    targetInput.addEventListener("input", () => {
      if (component.action === "custom_id") component.custom_id = targetInput.value;
      else component.url = targetInput.value;
      renderPreview();
    });
    targetField.appendChild(targetInput);
    fields.appendChild(targetField);
    card.appendChild(fields);
  }

  return card;
};

const getComponentLabel = (component) => {
  switch (component.type) {
    case 17: return "Container";
    case 10: return "Text Display";
    case 9: return "Section";
    case 12: return "Media Gallery";
    case 14: return "Separator";
    case 2: return "Button";
    default: return "Component";
  }
};

const addComponent = (type) => {
  const root = getRoot();
  if (!root) {
    state.payload = { flags: 32768, components: [{ type: 17, components: [] }] };
  }
  const target = getChildren();
  let component = null;
  switch (type) {
    case "text": component = { type: 10, content: "New text display" }; break;
    case "section": component = { type: 9, text: "Section heading" }; break;
    case "media": component = { type: 12, items: [{ media: { url: "https://example.com/image.png" } }] }; break;
    case "separator": component = { type: 14 }; break;
    case "button": component = { type: 2, label: "Open", style: 1, action: "url", url: "https://dailybread.app" }; break;
    default: component = { type: 17, components: [] };
  }
  target.push(component);
  renderEditor();
  renderPreview();
};

const loadSavedContainers = async () => {
  const containerSaved = document.getElementById("container-saved");
  if (!containerSaved) return;
  containerSaved.innerHTML = "Loading...";
  try {
    const response = await fetch("/api/containers");
    const data = await response.json();
    if (!data.success) throw new Error(data.error || "Unable to load containers.");
    state.savedContainers = data.containers || [];
    containerSaved.innerHTML = "";
    if (state.savedContainers.length === 0) {
      containerSaved.appendChild(createElement("p", { class: "text-sm text-bread-muted" }, "No saved containers yet."));
      return;
    }
    state.savedContainers.forEach((container) => {
      const row = createElement("div", { class: "rounded-2xl border border-bread-border bg-bread-background p-3" });
      const title = createElement("div", { class: "flex items-center justify-between gap-3" });
      title.appendChild(createElement("span", { class: "font-semibold text-bread-ink" }, container.name || "Untitled container"));
      title.appendChild(createElement("span", { class: "text-xs uppercase tracking-[0.18em] text-bread-muted" }, "Saved"));
      row.appendChild(title);
      const buttons = createElement("div", { class: "mt-3 flex flex-wrap gap-2" });
      const loadButton = createElement("button", { class: "rounded-2xl border border-bread-border bg-white px-3 py-2 text-xs font-semibold text-bread-ink" }, "Load");
      loadButton.addEventListener("click", () => {
        state.selectedContainerId = container.id;
        state.payload = structuredClone(container.container_json || DEFAULT_PAYLOAD);
        renderEditor();
        renderPreview();
      });
      buttons.appendChild(loadButton);
      const sendButton = createElement("button", { class: "rounded-2xl border border-bread-border bg-white px-3 py-2 text-xs font-semibold text-bread-ink" }, "Send");
      sendButton.addEventListener("click", async () => {
        const channelId = document.getElementById("container-channel")?.value || "";
        const response = await fetch(`/api/containers/${container.id}/send`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ channel_id: channelId }) });
        const data = await response.json();
        if (!data.success) throw new Error(data.error || "Send failed.");
        showAlert("Container sent successfully.");
      });
      buttons.appendChild(sendButton);
      row.appendChild(buttons);
      containerSaved.appendChild(row);
    });
  } catch (error) {
    containerSaved.innerHTML = "";
    showAlert(error.message || "Unable to load containers.", "error");
  }
};

const getCurrentGuildId = () => document.getElementById("container-guild")?.value || "";
const getCurrentChannelId = () => document.getElementById("builder-channel-id")?.value || document.getElementById("container-channel")?.value || "";

const saveContainer = async () => {
  const guildId = getCurrentGuildId();
  const channelId = getCurrentChannelId();
  try {
    const response = await fetch("/api/containers/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "DailyBread container", container_json: serializePayload(), guild_discord_id: guildId, channel_discord_id: channelId }),
    });
    const data = await response.json();
    if (!data.success) throw new Error(data.error || "Unable to save container.");
    state.selectedContainerId = data.container_id;
    showAlert("Container saved successfully.");
    await loadSavedContainers();
    return true;
  } catch (error) {
    showAlert(error.message || "Unable to save container.", "error");
    return false;
  }
};

const sendContainer = async () => {
  if (!state.selectedContainerId) {
    const saved = await saveContainer();
    if (!saved) return;
  }
  const channelId = getCurrentChannelId();
  try {
    const response = await fetch(`/api/containers/${state.selectedContainerId}/send`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ channel_id: channelId }) });
    const data = await response.json();
    if (!data.success) throw new Error(data.error || "Unable to send container.");
    showAlert("Container sent successfully.");
  } catch (error) {
    showAlert(error.message || "Unable to send container.", "error");
  }
};

const init = () => {
  renderEditor();
  renderPreview();
  loadSavedContainers();

  document.querySelectorAll("[data-add-component]").forEach((button) => {
    button.addEventListener("click", () => addComponent(button.dataset.addComponent));
  });

  document.getElementById("container-save")?.addEventListener("click", saveContainer);
  document.getElementById("container-send")?.addEventListener("click", sendContainer);

  const guildSelect = document.getElementById("container-guild");
  const channelSelect = document.getElementById("container-channel");

  guildSelect?.addEventListener("change", async () => {
    channelSelect.innerHTML = '<option value="">Select a channel</option>';
    const guildId = guildSelect.value;
    if (!guildId) return;
    try {
      const response = await fetch(`/api/guilds/${guildId}/channels`);
      const data = await response.json();
      if (!data.success) throw new Error(data.error || "Unable to load channels.");
      (data.channels || []).forEach((channel) => {
        const option = createElement("option", { value: channel.id }, `#${channel.name || channel.id}`);
        channelSelect.appendChild(option);
      });
    } catch (error) {
      showAlert(error.message || "Unable to load channels.", "error");
    }
  });
};

init();
window.DailyBreadAdvancedBuilder = { saveContainer, sendContainer, init };
