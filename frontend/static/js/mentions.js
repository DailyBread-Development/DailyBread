(function () {
  const names = { members: new Map(), roles: new Map() };
  const cache = new Map();
  let menu = null; let activeInput = null; let results = []; let selectedIndex = 0; let requestToken = 0;
  const guildId = () => document.getElementById("container-guild")?.value || document.getElementById("select-guild")?.value || "";
  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  const cacheKey = (type, query) => `${guildId()}:${type}:${query.toLowerCase()}`;
  function close() { menu?.remove(); menu = null; activeInput = null; results = []; }
  function currentMention(input) {
    const before = input.value.slice(0, input.selectionStart ?? input.value.length);
    const match = before.match(/(?:^|\s)(<@&?[^<>\s]*)$/);
    if (!match) return null;
    const token = match[1];
    return { token, start: before.length - token.length, type: token.startsWith("<@&") ? "roles" : "members", query: token.replace(/^<@&?/, "") };
  }
  function position() { if (menu && activeInput) { const rect = activeInput.getBoundingClientRect(); menu.style.left = `${Math.max(8, rect.left)}px`; menu.style.top = `${rect.bottom + 6}px`; menu.style.width = `${Math.min(Math.max(rect.width, 250), 360)}px`; } }
  function render() {
    if (!menu) return;
    menu.innerHTML = results.length ? results.map((item, index) => {
      const name = item.display_name || item.name;
      const secondary = item.username && item.username !== name ? `<span class="dailybread-mention-secondary">@${escapeHtml(item.username)}</span>` : "";
      const marker = item.avatar_url ? `<img src="${escapeHtml(item.avatar_url)}" alt="" class="dailybread-mention-avatar">` : `<span class="dailybread-mention-role" style="background:${item.color ? `#${Number(item.color).toString(16).padStart(6, "0")}` : "#c9b27a"}"></span>`;
      return `<button type="button" class="dailybread-mention-option${index === selectedIndex ? " is-selected" : ""}" data-index="${index}">${marker}<span class="dailybread-mention-label"><strong>${escapeHtml(name)}</strong>${secondary}</span></button>`;
    }).join("") : '<div class="dailybread-mention-empty">No matches</div>';
    menu.querySelectorAll("[data-index]").forEach((button) => button.addEventListener("mousedown", (event) => { event.preventDefault(); choose(Number(button.dataset.index)); }));
    position();
  }
  async function search(type, query) {
    const key = cacheKey(type, query);
    if (cache.has(key)) return cache.get(key);
    const response = await fetch(`/api/guilds/${encodeURIComponent(guildId())}/${type}/search?q=${encodeURIComponent(query)}`);
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || "Mention search failed.");
    const found = data[type] || []; cache.set(key, found);
    found.forEach((item) => (type === "roles" ? names.roles.set(String(item.id), item.name) : names.members.set(String(item.id), item.display_name || item.username)));
    return found;
  }
  async function prime(guild) {
    if (guild) {
      await Promise.allSettled([search("members", ""), search("roles", "")]);
    }
  }
  async function update(input) {
    const mention = currentMention(input); if (!mention || !guildId()) return close();
    activeInput = input;
    if (!menu) { menu = document.createElement("div"); menu.className = "dailybread-mention-menu"; document.body.appendChild(menu); }
    position(); const token = ++requestToken;
    try { results = await search(mention.type, mention.query); if (token !== requestToken || activeInput !== input) return; selectedIndex = 0; render(); } catch (error) { close(); }
  }
  function choose(index) {
    const mention = activeInput && currentMention(activeInput); const item = results[index]; if (!mention || !item) return close();
    const replacement = mention.type === "roles" ? `<@&${item.id}>` : `<@${item.id}>`; const end = activeInput.selectionStart ?? activeInput.value.length;
    activeInput.value = `${activeInput.value.slice(0, mention.start)}${replacement}${activeInput.value.slice(end)}`;
    activeInput.setSelectionRange(mention.start + replacement.length, mention.start + replacement.length); activeInput.dispatchEvent(new Event("input", { bubbles: true })); close();
  }
  function renderPreviewText(element, value) {
    const fragment = document.createDocumentFragment(); const pattern = /<@&(\d+)>|<@(\d+)>|<#(\d+)>|@(everyone|here)/g; let last = 0; let match;
    while ((match = pattern.exec(String(value || "")))) { fragment.append(document.createTextNode(String(value).slice(last, match.index))); const mention = document.createElement("span"); mention.className = match[1] ? "discord-mention discord-role-mention" : "discord-mention"; mention.textContent = match[1] ? `@${names.roles.get(match[1]) || "Role"}` : match[2] ? `@${names.members.get(match[2]) || "User"}` : match[3] ? "#channel" : `@${match[4]}`; fragment.append(mention); last = pattern.lastIndex; }
    fragment.append(document.createTextNode(String(value || "").slice(last))); element.replaceChildren(fragment);
  }
  document.addEventListener("input", (event) => { if (event.target.matches("input:not([type=color]):not([type=url]):not([type=hidden]), textarea")) update(event.target); });
  document.addEventListener("keydown", (event) => { if (!menu || event.target !== activeInput) return; if (event.key === "Escape") { event.preventDefault(); close(); } if (event.key === "ArrowDown") { event.preventDefault(); selectedIndex = Math.min(selectedIndex + 1, results.length - 1); render(); } if (event.key === "ArrowUp") { event.preventDefault(); selectedIndex = Math.max(selectedIndex - 1, 0); render(); } if (event.key === "Enter" && results[selectedIndex]) { event.preventDefault(); choose(selectedIndex); } });
  document.addEventListener("click", (event) => { if (menu && event.target !== activeInput && !menu.contains(event.target)) close(); });
  window.addEventListener("scroll", position, true); window.addEventListener("resize", position);
  window.DailyBreadMentions = { renderPreviewText, names, prime };
}());