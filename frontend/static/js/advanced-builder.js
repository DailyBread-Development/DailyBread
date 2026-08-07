const DEFAULT_CONTAINER = {
  flags: 32768,
  components: [
    {
      type: 17,
      components: [],
    },
  ],
};

const state = {
  selectedContainerId: null,
  currentPayload: JSON.parse(JSON.stringify(DEFAULT_CONTAINER)),
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
    class: `toast-notification rounded-2xl border px-4 py-3 text-sm font-semibold ${
      variant === "error"
        ? "border-red-200 bg-red-50 text-red-700"
        : "border-emerald-200 bg-emerald-50 text-emerald-700"
    }`,
  });
  alert.textContent = message;
  const container = document.getElementById("alert-container");
  if (!container) return;
  container.innerHTML = "";
  container.appendChild(alert);
  window.setTimeout(() => {
    if (alert.parentElement) {
      alert.parentElement.removeChild(alert);
    }
  }, 6000);
};

const debounce = (fn, wait = 250) => {
  let timeout = null;
  return (...args) => {
    if (timeout) window.clearTimeout(timeout);
    timeout = window.setTimeout(() => fn(...args), wait);
  };
};

const getRootComponent = () => {
  return state.currentPayload.components.find((c) => c.type === 17) || null;
};

const updatePayload = debounce(() => {
  state.currentPayload.flags = 32768;
  const preview = document.getElementById("preview-json");
  if (preview) {
    preview.textContent = JSON.stringify(state.currentPayload, null, 2);
  }
});

const renderBlock = (component, parentIndex = 0, index = 0) => {
  const block = createElement("div", {
    class: "rounded-2xl border border-bread-border bg-white p-4 shadow-sm",
  });

  const header = createElement("div", {
    class: "mb-3 flex items-center justify-between gap-3",
  });
  const title = createElement("h3", { class: "text-sm font-semibold text-bread-ink" }, `Block ${parentIndex}-${index}: ${component.type === 17 ? "Container" : component.type === 10 ? "TextDisplay" : component.type === 9 ? "Section" : component.type === 12 ? "MediaGallery" : component.type === 14 ? "Separator" : "Unknown"}`);
  header.appendChild(title);

  const buttonGroup = createElement("div", { class: "flex gap-2" });
  if (component.type !== 17) {
    const removeButton = createElement("button", { class: "rounded-full border border-red-200 bg-red-50 px-3 py-1 text-xs font-semibold text-red-700 transition hover:bg-red-100" }, "Remove");
    removeButton.addEventListener("click", () => {
      state.currentPayload.components = state.currentPayload.components.filter((_, i) => i !== index);
      renderEditor();
      updatePayload();
    });
    buttonGroup.appendChild(removeButton);

    const promoteButton = createElement("button", { class: "rounded-full border border-bread-border bg-bread-background px-3 py-1 text-xs font-semibold text-bread-ink transition hover:bg-bread-hover" }, "Promote");
    promoteButton.addEventListener("click", () => {
      const block = state.currentPayload.components.splice(index, 1)[0];
      state.currentPayload.components.unshift(block);
      renderEditor();
      updatePayload();
    });
    buttonGroup.appendChild(promoteButton);
  }

  header.appendChild(buttonGroup);
  block.appendChild(header);

  if (component.type === 10) {
    const label = createElement("label", { class: "flex flex-col gap-2 text-sm text-bread-ink" });
    label.innerHTML = `<span class="font-semibold">TextDisplay content</span>`;
    const textarea = createElement("textarea", { class: "min-h-[120px] rounded-2xl border border-bread-border bg-bread-background p-3 text-sm text-bread-ink outline-none", placeholder: "Enter text content..." });
    textarea.value = component.value || "";
    textarea.addEventListener("input", () => {
      component.value = textarea.value;
      updatePayload();
    });
    label.appendChild(textarea);
    block.appendChild(label);
  }

  if (component.type === 9) {
    const label = createElement("label", { class: "flex flex-col gap-2 text-sm text-bread-ink" });
    label.innerHTML = `<span class="font-semibold">Section text</span>`;
    const textarea = createElement("textarea", { class: "min-h-[120px] rounded-2xl border border-bread-border bg-bread-background p-3 text-sm text-bread-ink outline-none", placeholder: "Enter section text..." });
    textarea.value = component.text || "";
    textarea.addEventListener("input", () => {
      component.text = textarea.value;
      updatePayload();
    });
    label.appendChild(textarea);
    block.appendChild(label);
  }

  if (component.type === 12) {
    const label = createElement("label", { class: "flex flex-col gap-2 text-sm text-bread-ink" });
    label.innerHTML = `<span class="font-semibold">Media URL</span>`;
    const input = createElement("input", { type: "text", class: "rounded-2xl border border-bread-border bg-bread-background px-4 py-3 text-sm text-bread-ink outline-none", placeholder: "https://..." });
    input.value = component.url || "";
    input.addEventListener("input", () => {
      component.url = input.value;
      updatePayload();
    });
    label.appendChild(input);
    block.appendChild(label);
  }

  if (component.type === 14) {
    block.appendChild(createElement("p", { class: "text-sm text-bread-muted" }, "Separator blocks have no editable fields."));
  }

  if (component.type === 17) {
    const addChildRow = createElement("div", { class: "mt-4 grid gap-2 sm:grid-cols-2" });
    [
      { label: "TextDisplay", type: 10 },
      { label: "Section", type: 9 },
      { label: "MediaGallery", type: 12 },
      { label: "Separator", type: 14 },
    ].forEach((item) => {
      const button = createElement("button", {
        class: "rounded-2xl border border-bread-border bg-bread-background px-4 py-3 text-sm font-semibold text-bread-ink transition hover:bg-bread-hover",
      }, `Add ${item.label}`);
      button.addEventListener("click", () => {
        const child = { type: item.type };
        if (item.type === 10) child.value = "";
        if (item.type === 9) child.text = "";
        if (item.type === 12) child.url = "";
        state.currentPayload.components[0].components = state.currentPayload.components[0].components || [];
        state.currentPayload.components[0].components.push(child);
        renderEditor();
        updatePayload();
      });
      addChildRow.appendChild(button);
    });
    block.appendChild(addChildRow);

    const childList = createElement("div", { class: "mt-4 space-y-3" });
    (component.components || []).forEach((child, childIndex) => {
      const childBlock = createElement("div", { class: "rounded-2xl border border-bread-border bg-bread-background p-4" });
      const childHeader = createElement("div", { class: "mb-3 flex items-center justify-between gap-3" });
      childHeader.appendChild(createElement("span", { class: "font-semibold text-bread-ink" }, `Child ${childIndex + 1}: ${child.type === 10 ? "TextDisplay" : child.type === 9 ? "Section" : child.type === 12 ? "MediaGallery" : child.type === 14 ? "Separator" : "Unknown"}`));
      const removeChild = createElement("button", { class: "rounded-full border border-red-200 bg-red-50 px-3 py-1 text-xs font-semibold text-red-700 transition hover:bg-red-100" }, "Remove");
      removeChild.addEventListener("click", () => {
        component.components.splice(childIndex, 1);
        renderEditor();
        updatePayload();
      });
      childHeader.appendChild(removeChild);
      childBlock.appendChild(childHeader);

      if (child.type === 10) {
        const textarea = createElement("textarea", { class: "min-h-[100px] w-full rounded-2xl border border-bread-border bg-white p-3 text-sm text-bread-ink outline-none", placeholder: "TextDisplay content..." });
        textarea.value = child.value || "";
        textarea.addEventListener("input", () => {
          child.value = textarea.value;
          updatePayload();
        });
        childBlock.appendChild(textarea);
      }
      if (child.type === 9) {
        const textarea = createElement("textarea", { class: "min-h-[100px] w-full rounded-2xl border border-bread-border bg-white p-3 text-sm text-bread-ink outline-none", placeholder: "Section text..." });
        textarea.value = child.text || "";
        textarea.addEventListener("input", () => {
          child.text = textarea.value;
          updatePayload();
        });
        childBlock.appendChild(textarea);
      }
      if (child.type === 12) {
        const input = createElement("input", { type: "text", class: "w-full rounded-2xl border border-bread-border bg-white px-4 py-3 text-sm text-bread-ink outline-none", placeholder: "Media URL..." });
        input.value = child.url || "";
        input.addEventListener("input", () => {
          child.url = input.value;
          updatePayload();
        });
        childBlock.appendChild(input);
      }
      if (child.type === 14) {
        childBlock.appendChild(createElement("p", { class: "text-sm text-bread-muted" }, "Separator block - no additional properties."));
      }

      childList.appendChild(childBlock);
    });
    block.appendChild(childList);
  }

  return block;
};

const renderEditor = () => {
  const blockList = document.getElementById("block-list");
  if (!blockList) return;
  blockList.innerHTML = "";

  state.currentPayload.components.forEach((component, index) => {
    blockList.appendChild(renderBlock(component, 0, index));
  });
};

const loadSavedContainers = async () => {
  const savedPanel = document.getElementById("saved-containers");
  if (!savedPanel) return;
  savedPanel.innerHTML = "Loading...";

  try {
    const response = await fetch("/api/containers");
    const data = await response.json();
    if (!data.success) {
      throw new Error(data.error || "Unable to load containers.");
    }
    state.savedContainers = data.containers || [];
    savedPanel.innerHTML = "";
    if (state.savedContainers.length === 0) {
      savedPanel.appendChild(createElement("p", { class: "text-sm text-bread-muted" }, "No saved containers yet."));
      return;
    }

    state.savedContainers.forEach((container) => {
      const row = createElement("div", { class: "rounded-2xl border border-bread-border bg-bread-background p-4" });
      const title = createElement("div", { class: "mb-2 flex items-center justify-between gap-2" });
      title.appendChild(createElement("span", { class: "font-semibold text-bread-ink" }, `Container ${container.id}`));
      title.appendChild(createElement("span", { class: "text-xs uppercase tracking-[0.18em] text-bread-muted" }, container.guild_discord_id ? "Guild" : "Private"));
      row.appendChild(title);

      const footer = createElement("div", { class: "flex flex-wrap gap-2" });
      const loadButton = createElement("button", { class: "rounded-2xl border border-bread-border bg-bread-background px-3 py-2 text-xs font-semibold text-bread-ink transition hover:bg-bread-hover" }, "Load");
      loadButton.addEventListener("click", () => {
        state.selectedContainerId = container.id;
        state.currentPayload = JSON.parse(JSON.stringify(container.container_json || DEFAULT_CONTAINER));
        renderEditor();
        updatePayload();
      });
      footer.appendChild(loadButton);

      const resendButton = createElement("button", { class: "rounded-2xl border border-bread-border bg-bread-background px-3 py-2 text-xs font-semibold text-bread-ink transition hover:bg-bread-hover" }, "Resend");
      resendButton.addEventListener("click", async () => {
        if (!container.id) return;
        const channelId = document.getElementById("select-channel")?.value || "";
        const response = await fetch(`/api/containers/${container.id}/send`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ channel_id: channelId }) });
        const result = await response.json();
        if (!result.success) {
          showAlert(result.error || "Send failed.", "error");
          return;
        }
        showAlert("Container sent successfully.");
        loadSavedContainers();
      });
      footer.appendChild(resendButton);
      row.appendChild(footer);
      savedPanel.appendChild(row);
    });
  } catch (error) {
    savedPanel.innerHTML = "";
    showAlert(error.message || "Unable to load containers.", "error");
  }
};

const saveContainer = async () => {
  const guildId = document.getElementById("select-guild")?.value || "";
  const channelId = document.getElementById("select-channel")?.value || "";
  const payload = {
    container_json: state.currentPayload,
    guild_discord_id: guildId,
    channel_discord_id: channelId,
  };

  try {
    const response = await fetch("/api/containers/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!data.success) {
      throw new Error(data.error || "Unable to save container.");
    }
    state.selectedContainerId = data.container_id;
    showAlert("Container saved successfully.");
    loadSavedContainers();
  } catch (error) {
    showAlert(error.message || "Unable to save container.", "error");
  }
};

const sendContainer = async () => {
  const containerId = state.selectedContainerId;
  if (!containerId) {
    showAlert("Save the container first before sending.", "error");
    return;
  }

  try {
    const channelId = document.getElementById("select-channel")?.value || "";
    const response = await fetch(`/api/containers/${containerId}/send`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ channel_id: channelId }) });
    const data = await response.json();
    if (!data.success) {
      throw new Error(data.error || "Unable to send container.");
    }
    showAlert("Container sent successfully.");
    loadSavedContainers();
  } catch (error) {
    showAlert(error.message || "Unable to send container.", "error");
  }
};

const init = () => {
  const addContainer = document.getElementById("add-container");
  const addText = document.getElementById("add-text");
  const saveButton = document.getElementById("save-container");
  const sendButton = document.getElementById("send-container");

  if (addContainer) {
    addContainer.addEventListener("click", () => {
      state.currentPayload.components = [
        {
          type: 17,
          components: [],
        },
      ];
      state.selectedContainerId = null;
      renderEditor();
      updatePayload();
    });
  }

  if (addText) {
    addText.addEventListener("click", () => {
      const root = getRootComponent();
      if (!root) return;
      root.components = root.components || [];
      root.components.push({ type: 10, value: "" });
      renderEditor();
      updatePayload();
    });
  }

  const selectGuild = document.getElementById("select-guild");
  const selectChannel = document.getElementById("select-channel");

  if (selectGuild && selectChannel) {
    selectGuild.addEventListener("change", async () => {
      selectChannel.innerHTML = "<option value=''>Select a channel</option>";
      const guildId = selectGuild.value;
      if (!guildId) return;
      try {
        const response = await fetch(`/api/guilds/${guildId}/channels`);
        const data = await response.json();
        if (!data.success) {
          throw new Error(data.error || "Unable to load channels.");
        }
        data.channels.forEach((channel) => {
          const option = createElement("option", { value: channel.id }, channel.name || channel.id);
          selectChannel.appendChild(option);
        });
      } catch (error) {
        showAlert(error.message || "Unable to load channels.", "error");
      }
    });
  }

  if (saveButton) {
    saveButton.addEventListener("click", saveContainer);
  }

  if (sendButton) {
    sendButton.addEventListener("click", sendContainer);
  }

  renderEditor();
  updatePayload();
  loadSavedContainers();
};

window.addEventListener("DOMContentLoaded", init);
