const state = {
  clients: [],
  defaults: [],
  selectedClients: new Set(),
  searchId: null,
  results: [],
  selectedResults: new Set(),
  currentJobId: null,
  pollTimer: null,
};

const els = {
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
};

function initIcons() {
  if (window.lucide) {
    window.lucide.createIcons();
  }
}

function setStatus(text, tone = "") {
  els.statusText.textContent = text;
  els.statusText.className = tone;
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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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
    renderJob(data.job);
    pollJob(data.job.id);
  } catch (error) {
    els.jobStatus.textContent = "下载失败";
    els.jobMessage.textContent = error.message;
    els.downloadSelected.disabled = state.selectedResults.size === 0;
  }
}

function renderJob(job) {
  els.jobPanel.hidden = false;
  const labels = {
    queued: "排队中",
    running: "下载中",
    complete: "下载完成",
    empty: "没有文件",
    error: "下载失败",
  };
  els.jobStatus.textContent = labels[job.status] || job.status;
  els.jobMessage.textContent = job.message || "";

  const files = job.files || [];
  if (!files.length) {
    els.fileList.innerHTML = "";
  } else {
    els.fileList.innerHTML = files
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
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
    els.downloadSelected.disabled = state.selectedResults.size === 0;
  }
}

function pollJob(jobId) {
  window.clearInterval(state.pollTimer);
  state.pollTimer = window.setInterval(async () => {
    try {
      const data = await apiFetch(`/api/jobs/${jobId}`);
      renderJob(data.job);
    } catch (error) {
      window.clearInterval(state.pollTimer);
      state.pollTimer = null;
      els.jobStatus.textContent = "任务状态不可用";
      els.jobMessage.textContent = error.message;
    }
  }, 1500);
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

loadClients().catch((error) => {
  setStatus(error.message, "danger");
});

initIcons();
