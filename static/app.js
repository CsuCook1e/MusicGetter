const state = {
  workflow: "music",
  clients: [],
  defaults: [],
  selectedClients: new Set(),
  searchId: null,
  results: [],
  selectedResults: new Set(),
  currentJobId: null,
  pollTimer: null,
  douyinUserSearchId: null,
  douyinUsers: [],
  selectedDouyinUserId: null,
  douyinVideoSetId: null,
  douyinVideos: [],
  selectedDouyinVideos: new Set(),
  douyinJobId: null,
  douyinPollTimer: null,
};

const els = {
  workflowTabs: document.querySelectorAll("[data-workflow]"),
  musicWorkflow: document.querySelector("#musicWorkflow"),
  douyinWorkflow: document.querySelector("#douyinWorkflow"),
  musicSidebarTools: document.querySelector("#musicSidebarTools"),
  douyinSidebarTools: document.querySelector("#douyinSidebarTools"),
  clientGroups: document.querySelector("#clientGroups"),
  clientFilter: document.querySelector("#clientFilter"),
  selectDefaults: document.querySelector("#selectDefaults"),
  selectAll: document.querySelector("#selectAll"),
  clearClients: document.querySelector("#clearClients"),
  searchForm: document.querySelector("#searchForm"),
  keyword: document.querySelector("#keyword"),
  limitPerClient: document.querySelector("#limitPerClient"),
  searchButton: document.querySelector("#searchButton"),
  clientCount: document.querySelector("#clientCount"),
  resultCount: document.querySelector("#resultCount"),
  statusText: document.querySelector("#statusText"),
  countsText: document.querySelector("#countsText"),
  resultsBody: document.querySelector("#resultsBody"),
  toggleAllResults: document.querySelector("#toggleAllResults"),
  downloadSelected: document.querySelector("#downloadSelected"),
  jobPanel: document.querySelector("#jobPanel"),
  jobStatus: document.querySelector("#jobStatus"),
  jobMessage: document.querySelector("#jobMessage"),
  fileList: document.querySelector("#fileList"),
  douyinUserForm: document.querySelector("#douyinUserForm"),
  douyinKeyword: document.querySelector("#douyinKeyword"),
  douyinUserLimit: document.querySelector("#douyinUserLimit"),
  douyinUserButton: document.querySelector("#douyinUserButton"),
  douyinUserCount: document.querySelector("#douyinUserCount"),
  douyinVideoCount: document.querySelector("#douyinVideoCount"),
  douyinStatusText: document.querySelector("#douyinStatusText"),
  douyinDownloadSelected: document.querySelector("#douyinDownloadSelected"),
  douyinNotes: document.querySelector("#douyinNotes"),
  douyinUsers: document.querySelector("#douyinUsers"),
  douyinToggleAllVideos: document.querySelector("#douyinToggleAllVideos"),
  douyinVideoMeta: document.querySelector("#douyinVideoMeta"),
  douyinVideosBody: document.querySelector("#douyinVideosBody"),
  douyinJobPanel: document.querySelector("#douyinJobPanel"),
  douyinJobStatus: document.querySelector("#douyinJobStatus"),
  douyinJobMessage: document.querySelector("#douyinJobMessage"),
  douyinFileList: document.querySelector("#douyinFileList"),
  openDouyinLogin: document.querySelector("#openDouyinLogin"),
  refreshDouyinSession: document.querySelector("#refreshDouyinSession"),
  douyinSessionState: document.querySelector("#douyinSessionState"),
  clearDouyinCache: document.querySelector("#clearDouyinCache"),
  douyinCacheStats: document.querySelector("#douyinCacheStats"),
};

function initIcons() {
  if (window.lucide) window.lucide.createIcons();
}

function setStatus(text, tone = "") {
  els.statusText.textContent = text;
  els.statusText.className = tone;
}

function setDouyinStatus(text, tone = "") {
  els.douyinStatusText.textContent = text;
  els.douyinStatusText.className = tone;
}

function formatBytes(size) {
  if (!Number.isFinite(size) || size <= 0) return "";
  const units = ["B", "KB", "MB", "GB"];
  let value = size;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function formatDuration(msOrSeconds) {
  const raw = Number(msOrSeconds || 0);
  const seconds = raw > 1000 ? Math.round(raw / 1000) : Math.round(raw);
  if (!seconds) return "-";
  const mins = Math.floor(seconds / 60);
  const secs = String(seconds % 60).padStart(2, "0");
  return `${mins}:${secs}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function switchWorkflow(workflow) {
  state.workflow = workflow;
  els.musicWorkflow.hidden = workflow !== "music";
  els.douyinWorkflow.hidden = workflow !== "douyin";
  els.musicSidebarTools.hidden = workflow !== "music";
  els.douyinSidebarTools.hidden = workflow !== "douyin";
  for (const tab of els.workflowTabs) {
    tab.classList.toggle("active", tab.dataset.workflow === workflow);
  }
  if (window.location.hash !== `#${workflow}`) {
    history.replaceState(null, "", `#${workflow}`);
  }
  initIcons();
}

function selectedClientList() {
  return [...state.selectedClients].filter((name) => state.clients.some((client) => client.name === name));
}

function updateClientCount() {
  els.clientCount.textContent = selectedClientList().length;
}

function renderClients() {
  const query = els.clientFilter.value.trim().toLowerCase();
  const grouped = new Map();

  for (const client of state.clients) {
    const searchable = `${client.name} ${client.label} ${client.group}`.toLowerCase();
    if (query && !searchable.includes(query)) continue;
    if (!grouped.has(client.group)) grouped.set(client.group, []);
    grouped.get(client.group).push(client);
  }

  els.clientGroups.innerHTML = [...grouped.entries()]
    .map(([group, clients]) => {
      const items = clients
        .map(
          (client) => `
            <label class="client-item" title="${escapeHtml(client.name)}">
              <input type="checkbox" data-client="${escapeHtml(client.name)}" ${
                state.selectedClients.has(client.name) ? "checked" : ""
              }>
              <span>${escapeHtml(client.label)}</span>
            </label>
          `,
        )
        .join("");
      return `<section class="client-group"><h2>${escapeHtml(group)}</h2><div class="client-list">${items}</div></section>`;
    })
    .join("");

  updateClientCount();
}

function renderResults() {
  els.resultCount.textContent = state.results.length;
  els.downloadSelected.disabled = state.selectedResults.size === 0;
  els.toggleAllResults.checked = state.results.length > 0 && state.selectedResults.size === state.results.length;
  els.toggleAllResults.indeterminate = state.selectedResults.size > 0 && state.selectedResults.size < state.results.length;

  if (!state.results.length) {
    els.resultsBody.innerHTML = `<tr class="empty-row"><td colspan="7">没有结果</td></tr>`;
    return;
  }

  els.resultsBody.innerHTML = state.results
    .map((item) => {
      const checked = state.selectedResults.has(item.id) ? "checked" : "";
      const cover = item.coverUrl
        ? `<img class="cover" src="${escapeHtml(item.coverUrl)}" alt="">`
        : `<div class="cover" aria-hidden="true"></div>`;
      const root = item.rootSource ? ` · ${escapeHtml(item.rootSource)}` : "";
      const parent = item.parentTitle ? ` · ${escapeHtml(item.parentTitle)}` : "";
      const disabled = item.downloadable ? "" : "disabled";
      return `
        <tr>
          <td><input class="row-check" type="checkbox" data-result="${escapeHtml(item.id)}" ${checked}></td>
          <td>
            <div class="song-cell">
              ${cover}
              <div>
                <div class="song-title" title="${escapeHtml(item.songName)}">${escapeHtml(item.songName)}</div>
                <div class="song-meta" title="${escapeHtml(item.singers)}">${escapeHtml(item.singers || "未知艺人")}${parent}</div>
              </div>
            </div>
          </td>
          <td><span class="tag" title="${escapeHtml(item.source)}">${escapeHtml(item.sourceLabel)}${root}</span></td>
          <td>${escapeHtml(item.ext || "-")}</td>
          <td>${escapeHtml(item.fileSize || "-")}</td>
          <td>${escapeHtml(item.duration || "-")}</td>
          <td><button class="row-button" type="button" data-download-one="${escapeHtml(item.id)}" ${disabled}>下载</button></td>
        </tr>
      `;
    })
    .join("");
}

function renderCounts(counts) {
  const text = Object.entries(counts || {})
    .map(([source, count]) => `${source.replace("MusicClient", "")}: ${count}`)
    .join(" · ");
  els.countsText.textContent = text;
}

function renderDouyinUsers() {
  els.douyinUserCount.textContent = state.douyinUsers.length;
  if (!state.douyinUsers.length) {
    els.douyinUsers.classList.add("empty-panel");
    els.douyinUsers.innerHTML = "没有用户候选";
    return;
  }
  els.douyinUsers.classList.remove("empty-panel");
  els.douyinUsers.innerHTML = state.douyinUsers
    .map((user) => {
      const avatar = user.avatar
        ? `<img class="avatar" src="${escapeHtml(user.avatar)}" alt="">`
        : `<div class="avatar" aria-hidden="true"></div>`;
      const active = state.selectedDouyinUserId === user.id ? "active" : "";
      const meta = [user.douyinId ? `抖音号 ${user.douyinId}` : "", user.uid ? `UID ${user.uid}` : "", user.source]
        .filter(Boolean)
        .join(" · ");
      return `
        <button class="user-card ${active}" type="button" data-douyin-user="${escapeHtml(user.id)}">
          ${avatar}
          <div>
            <div class="song-title" title="${escapeHtml(user.nickname)}">${escapeHtml(user.nickname)}</div>
            <div class="song-meta" title="${escapeHtml(meta)}">${escapeHtml(meta || "抖音用户")}</div>
            <div class="song-meta" title="${escapeHtml(user.signature)}">${escapeHtml(user.signature || "")}</div>
          </div>
        </button>
      `;
    })
    .join("");
  initIcons();
}

function renderDouyinVideos() {
  els.douyinVideoCount.textContent = state.douyinVideos.length;
  els.douyinDownloadSelected.disabled = state.selectedDouyinVideos.size === 0;
  els.douyinToggleAllVideos.checked =
    state.douyinVideos.length > 0 && state.selectedDouyinVideos.size === state.douyinVideos.length;
  els.douyinToggleAllVideos.indeterminate =
    state.selectedDouyinVideos.size > 0 && state.selectedDouyinVideos.size < state.douyinVideos.length;
  els.douyinVideoMeta.textContent = state.douyinVideos.length ? `可选 ${state.douyinVideos.length} 条` : "";

  if (!state.douyinVideos.length) {
    els.douyinVideosBody.innerHTML = `<tr class="empty-row"><td colspan="5">选择用户后获取视频</td></tr>`;
    return;
  }

  els.douyinVideosBody.innerHTML = state.douyinVideos
    .map((video) => {
      const checked = state.selectedDouyinVideos.has(video.id) ? "checked" : "";
      const cover = video.coverUrl
        ? `<img class="video-cover" src="${escapeHtml(video.coverUrl)}" alt="">`
        : `<div class="video-cover" aria-hidden="true"></div>`;
      const disabled = video.downloadable ? "" : "disabled";
      const music = [video.musicTitle, video.musicAuthor].filter(Boolean).join(" · ");
      return `
        <tr>
          <td><input class="row-check" type="checkbox" data-douyin-video="${escapeHtml(video.id)}" ${checked}></td>
          <td>
            <div class="video-cell">
              ${cover}
              <div>
                <div class="song-title" title="${escapeHtml(video.desc)}">${escapeHtml(video.desc)}</div>
                <div class="song-meta">时长 ${formatDuration(video.duration)} · 赞 ${escapeHtml(video.diggCount ?? "-")}</div>
              </div>
            </div>
          </td>
          <td>${escapeHtml(video.createTimeText || "-")}</td>
          <td><span class="tag" title="${escapeHtml(music)}">${escapeHtml(music || "原声")}</span></td>
          <td><button class="row-button" type="button" data-douyin-download-one="${escapeHtml(video.id)}" ${disabled}>音频</button></td>
        </tr>
      `;
    })
    .join("");
}

function renderNotes(notes) {
  const useful = (notes || []).filter(Boolean).slice(0, 5);
  els.douyinNotes.textContent = useful.join(" · ");
}

function renderDouyinCacheStats(stats) {
  const fileCount = stats?.fileCount ?? 0;
  const bytes = stats?.bytes ?? 0;
  els.douyinCacheStats.textContent = `缓存 ${fileCount} 个文件 · ${formatBytes(bytes) || "0 B"}`;
}

function renderDouyinSession(session) {
  if (!els.douyinSessionState) return;
  const stateText = session?.loggedIn ? "已登录" : session?.running ? "等待登录" : "未登录";
  const message = session?.message || "登录态未检测";
  els.douyinSessionState.textContent = `${stateText} · ${message}`;
  els.douyinSessionState.classList.toggle("ok", Boolean(session?.loggedIn));
}

async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data.detail || data.error || "请求失败");
  }
  return data;
}

async function loadClients() {
  const data = await apiFetch("/api/clients");
  state.clients = data.clients;
  state.defaults = data.defaults;
  state.selectedClients = new Set(data.defaults);
  renderClients();
  initIcons();
}

async function loadDouyinCacheStats() {
  try {
    const data = await apiFetch("/api/douyin/cache");
    renderDouyinCacheStats(data.stats);
  } catch {
    els.douyinCacheStats.textContent = "缓存状态不可用";
  }
}

async function loadDouyinSession() {
  if (!els.douyinSessionState) return;
  try {
    const data = await apiFetch("/api/douyin/session");
    renderDouyinSession(data.session);
  } catch {
    els.douyinSessionState.textContent = "登录状态不可用";
  }
}

async function openDouyinLoginWindow() {
  els.openDouyinLogin.disabled = true;
  try {
    const data = await apiFetch("/api/douyin/session/login", { method: "POST", body: "{}" });
    renderDouyinSession(data.session);
    setDouyinStatus("登录窗口已打开");
  } catch (error) {
    setDouyinStatus(error.message, "danger");
  } finally {
    els.openDouyinLogin.disabled = false;
  }
}

async function runSearch(event) {
  event.preventDefault();
  const keyword = els.keyword.value.trim();
  const clients = selectedClientList();
  if (!keyword || !clients.length) return;

  els.searchButton.disabled = true;
  state.searchId = null;
  state.results = [];
  state.selectedResults.clear();
  renderResults();
  renderCounts({});
  setStatus("搜索中");

  try {
    const data = await apiFetch("/api/search", {
      method: "POST",
      body: JSON.stringify({
        keyword,
        clients,
        limitPerClient: Number(els.limitPerClient.value || 5),
      }),
    });
    state.searchId = data.searchId;
    state.results = data.results;
    state.selectedResults.clear();
    setStatus(data.results.length ? "搜索完成" : "未找到结果");
    renderCounts(data.counts);
    renderResults();
  } catch (error) {
    setStatus(error.message, "danger");
    els.resultsBody.innerHTML = `<tr class="empty-row"><td colspan="7">${escapeHtml(error.message)}</td></tr>`;
  } finally {
    els.searchButton.disabled = false;
  }
}

async function startDownload(ids) {
  if (!state.searchId || !ids.length) return;
  els.downloadSelected.disabled = true;
  els.jobPanel.hidden = false;
  els.fileList.innerHTML = "";
  els.jobStatus.textContent = "下载任务";
  els.jobMessage.textContent = "创建任务中";

  try {
    const data = await apiFetch("/api/download", {
      method: "POST",
      body: JSON.stringify({ searchId: state.searchId, ids }),
    });
    state.currentJobId = data.job.id;
    renderJob(data.job, "music");
    pollJob(data.job.id, "music");
  } catch (error) {
    els.jobStatus.textContent = "下载失败";
    els.jobMessage.textContent = error.message;
    els.downloadSelected.disabled = state.selectedResults.size === 0;
  }
}

async function runDouyinUserSearch(event) {
  event.preventDefault();
  const keyword = els.douyinKeyword.value.trim();
  if (!keyword) return;

  els.douyinUserButton.disabled = true;
  state.douyinUserSearchId = null;
  state.douyinUsers = [];
  state.selectedDouyinUserId = null;
  state.douyinVideoSetId = null;
  state.douyinVideos = [];
  state.selectedDouyinVideos.clear();
  renderDouyinUsers();
  renderDouyinVideos();
  renderNotes([]);
  setDouyinStatus("搜索用户中");

  try {
    const data = await apiFetch("/api/douyin/users", {
      method: "POST",
      body: JSON.stringify({ keyword, limit: Number(els.douyinUserLimit.value || 10) }),
    });
    state.douyinUserSearchId = data.searchId;
    state.douyinUsers = data.users || [];
    renderNotes(data.notes || []);
    renderDouyinUsers();
    loadDouyinCacheStats();
    setDouyinStatus(state.douyinUsers.length ? "请选择用户" : "未找到用户");
  } catch (error) {
    setDouyinStatus(error.message, "danger");
    els.douyinUsers.classList.add("empty-panel");
    els.douyinUsers.innerHTML = escapeHtml(error.message);
  } finally {
    els.douyinUserButton.disabled = false;
  }
}

async function loadDouyinVideos(userId) {
  if (!state.douyinUserSearchId || !userId) return;
  state.selectedDouyinUserId = userId;
  state.douyinVideos = [];
  state.selectedDouyinVideos.clear();
  state.douyinVideoSetId = null;
  renderDouyinUsers();
  renderDouyinVideos();
  setDouyinStatus("获取视频中");

  try {
    const data = await apiFetch("/api/douyin/videos", {
      method: "POST",
      body: JSON.stringify({ searchId: state.douyinUserSearchId, userId }),
    });
    state.douyinVideoSetId = data.videoSetId;
    state.douyinVideos = data.videos || [];
    renderNotes(data.notes || []);
    renderDouyinVideos();
    loadDouyinCacheStats();
    setDouyinStatus(state.douyinVideos.length ? "视频获取完成" : "没有拿到视频");
  } catch (error) {
    setDouyinStatus(error.message, "danger");
    els.douyinVideosBody.innerHTML = `<tr class="empty-row"><td colspan="5">${escapeHtml(error.message)}</td></tr>`;
  }
}

async function startDouyinAudioDownload(ids) {
  if (!state.douyinVideoSetId || !ids.length) return;
  els.douyinDownloadSelected.disabled = true;
  els.douyinJobPanel.hidden = false;
  els.douyinFileList.innerHTML = "";
  els.douyinJobStatus.textContent = "音频任务";
  els.douyinJobMessage.textContent = "创建任务中";

  try {
    const data = await apiFetch("/api/douyin/download-audio", {
      method: "POST",
      body: JSON.stringify({ videoSetId: state.douyinVideoSetId, ids }),
    });
    state.douyinJobId = data.job.id;
    renderJob(data.job, "douyin");
    pollJob(data.job.id, "douyin");
  } catch (error) {
    els.douyinJobStatus.textContent = "音频下载失败";
    els.douyinJobMessage.textContent = error.message;
    els.douyinDownloadSelected.disabled = state.selectedDouyinVideos.size === 0;
  }
}

function renderJob(job, target = "music") {
  const panel = target === "douyin" ? els.douyinJobPanel : els.jobPanel;
  const statusEl = target === "douyin" ? els.douyinJobStatus : els.jobStatus;
  const messageEl = target === "douyin" ? els.douyinJobMessage : els.jobMessage;
  const fileListEl = target === "douyin" ? els.douyinFileList : els.fileList;
  panel.hidden = false;
  const labels = {
    queued: "排队中",
    running: target === "douyin" ? "音频处理中" : "下载中",
    complete: "下载完成",
    empty: "没有文件",
    error: "下载失败",
  };
  statusEl.textContent = labels[job.status] || job.status;
  messageEl.textContent = job.message || "";

  const files = job.files || [];
  if (!files.length) {
    fileListEl.innerHTML = "";
  } else {
    fileListEl.innerHTML = files
      .map(
        (file) => `
          <div class="file-item">
            <div>
              <div class="file-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</div>
              <div class="file-meta">${escapeHtml(file.source || "")} · ${formatBytes(file.size)}</div>
            </div>
            <a class="file-link" href="${escapeHtml(file.url)}">
              <i data-lucide="download"></i>
              <span>取回</span>
            </a>
          </div>
        `,
      )
      .join("");
    initIcons();
  }

  if (["complete", "empty", "error"].includes(job.status)) {
    if (target === "douyin") {
      window.clearInterval(state.douyinPollTimer);
      state.douyinPollTimer = null;
      els.douyinDownloadSelected.disabled = state.selectedDouyinVideos.size === 0;
    } else {
      window.clearInterval(state.pollTimer);
      state.pollTimer = null;
      els.downloadSelected.disabled = state.selectedResults.size === 0;
    }
  }
}

function pollJob(jobId, target = "music") {
  const timerName = target === "douyin" ? "douyinPollTimer" : "pollTimer";
  window.clearInterval(state[timerName]);
  state[timerName] = window.setInterval(async () => {
    try {
      const data = await apiFetch(`/api/jobs/${jobId}`);
      renderJob(data.job, target);
    } catch (error) {
      window.clearInterval(state[timerName]);
      state[timerName] = null;
      if (target === "douyin") {
        els.douyinJobStatus.textContent = "任务状态不可用";
        els.douyinJobMessage.textContent = error.message;
      } else {
        els.jobStatus.textContent = "任务状态不可用";
        els.jobMessage.textContent = error.message;
      }
    }
  }, 1500);
}

for (const tab of els.workflowTabs) {
  tab.addEventListener("click", () => switchWorkflow(tab.dataset.workflow));
}

els.clientGroups.addEventListener("change", (event) => {
  const input = event.target.closest("input[data-client]");
  if (!input) return;
  if (input.checked) state.selectedClients.add(input.dataset.client);
  else state.selectedClients.delete(input.dataset.client);
  updateClientCount();
});

els.clientFilter.addEventListener("input", renderClients);

els.selectDefaults.addEventListener("click", () => {
  state.selectedClients = new Set(state.defaults);
  renderClients();
});

els.selectAll.addEventListener("click", () => {
  state.selectedClients = new Set(state.clients.map((client) => client.name));
  renderClients();
});

els.clearClients.addEventListener("click", () => {
  state.selectedClients.clear();
  renderClients();
});

els.searchForm.addEventListener("submit", runSearch);

els.resultsBody.addEventListener("change", (event) => {
  const input = event.target.closest("input[data-result]");
  if (!input) return;
  if (input.checked) state.selectedResults.add(input.dataset.result);
  else state.selectedResults.delete(input.dataset.result);
  renderResults();
});

els.resultsBody.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-download-one]");
  if (!button) return;
  startDownload([button.dataset.downloadOne]);
});

els.toggleAllResults.addEventListener("change", () => {
  if (els.toggleAllResults.checked) {
    state.selectedResults = new Set(state.results.map((item) => item.id));
  } else {
    state.selectedResults.clear();
  }
  renderResults();
});

els.downloadSelected.addEventListener("click", () => {
  startDownload([...state.selectedResults]);
});

els.douyinUserForm.addEventListener("submit", runDouyinUserSearch);

els.douyinUsers.addEventListener("click", (event) => {
  const card = event.target.closest("[data-douyin-user]");
  if (!card) return;
  loadDouyinVideos(card.dataset.douyinUser);
});

els.douyinVideosBody.addEventListener("change", (event) => {
  const input = event.target.closest("input[data-douyin-video]");
  if (!input) return;
  if (input.checked) state.selectedDouyinVideos.add(input.dataset.douyinVideo);
  else state.selectedDouyinVideos.delete(input.dataset.douyinVideo);
  renderDouyinVideos();
});

els.douyinVideosBody.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-douyin-download-one]");
  if (!button) return;
  startDouyinAudioDownload([button.dataset.douyinDownloadOne]);
});

els.douyinToggleAllVideos.addEventListener("change", () => {
  if (els.douyinToggleAllVideos.checked) {
    state.selectedDouyinVideos = new Set(state.douyinVideos.map((item) => item.id));
  } else {
    state.selectedDouyinVideos.clear();
  }
  renderDouyinVideos();
});

els.douyinDownloadSelected.addEventListener("click", () => {
  startDouyinAudioDownload([...state.selectedDouyinVideos]);
});

els.openDouyinLogin.addEventListener("click", openDouyinLoginWindow);

els.refreshDouyinSession.addEventListener("click", loadDouyinSession);

els.clearDouyinCache.addEventListener("click", async () => {
  els.clearDouyinCache.disabled = true;
  try {
    const data = await apiFetch("/api/douyin/cache/clear", { method: "POST", body: "{}" });
    renderDouyinCacheStats(data.stats);
    setDouyinStatus("缓存已清理");
  } catch (error) {
    setDouyinStatus(error.message, "danger");
  } finally {
    els.clearDouyinCache.disabled = false;
  }
});

loadClients().catch((error) => {
  setStatus(error.message, "danger");
});

loadDouyinCacheStats();
loadDouyinSession();
switchWorkflow(window.location.hash === "#douyin" ? "douyin" : "music");
initIcons();
