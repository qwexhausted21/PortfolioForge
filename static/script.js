// PortfolioForge — клиентская логика UI (Vanilla JS)

(() => {
  "use strict";

  const BASE = window.location.origin;

  const els = {
    projectName: document.getElementById("projectName"),
    description: document.getElementById("description"),
    techStack: document.getElementById("techStack"),
    demoLink: document.getElementById("demoLink"),
    folderPath: document.getElementById("folderPath"),
    selectFolderBtn: document.getElementById("selectFolderBtn"),
    publishBtn: document.getElementById("publishBtn"),
    updateExisting: document.getElementById("updateExisting"),
    logsContainer: document.getElementById("logsContainer"),
    clearLogsBtn: document.getElementById("clearLogsBtn"),
    wsStatus: document.getElementById("wsStatus"),
    wsStatusText: document.querySelector("#wsStatus + span"),
    publishForm: document.getElementById("publishForm"),
    savedReposList: document.getElementById("savedReposList"),

    // Токен-модал
    tokenModal: document.getElementById("tokenModal"),
    tokenModalBackdrop: document.getElementById("tokenModalBackdrop"),
    openTokenModalBtn: document.getElementById("openTokenModalBtn"),
    closeTokenModalBtn: document.getElementById("closeTokenModalBtn"),
    tokenInput: document.getElementById("tokenInput"),
    validateTokenBtn: document.getElementById("validateTokenBtn"),
    saveTokenBtn: document.getElementById("saveTokenBtn"),
    tokenResult: document.getElementById("tokenResult"),
    tokenStatus: document.getElementById("tokenStatus"),
    tokenStatusDot: document.getElementById("tokenStatusDot"),
    tokenStatusText: document.getElementById("tokenStatusText"),
  };

  let ws = null;

  /* ---------- Логи ---------- */

  function appendLog(text, level = "info") {
    const now = new Date().toLocaleTimeString("ru-RU", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });

    const div = document.createElement("div");
    div.className = "log-line";

    let colorClass = "text-gray-400";
    const upper = String(text).toUpperCase();
    if (upper.includes("ОШИБКА") || upper.includes("ERROR") || upper.includes("FAILED")) {
      colorClass = "text-red-400";
    } else if (
      upper.includes("ГОТОВО") ||
      upper.includes("ОПУБЛИКОВАН") ||
      upper.includes("СОЗДАН")
    ) {
      colorClass = "text-emerald-400";
    } else if (String(text).startsWith("$")) {
      colorClass = "text-cyan-200/80";
    } else if (level === "warn") {
      colorClass = "text-yellow-400";
    }

    div.className = `log-line ${colorClass} text-sm font-mono leading-relaxed`;
    div.textContent = `[${now}] ${text}`;

    els.logsContainer.appendChild(div);
    els.logsContainer.scrollTop = els.logsContainer.scrollHeight;
  }

  function clearLogs() {
    els.logsContainer.innerHTML = "";
    appendLog("Логи очищены.");
  }

  /* ---------- WebSocket для логов ---------- */

  function connectLogs() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${window.location.host}/ws/logs`);

    ws.onopen = () => {
      els.wsStatus.className = "w-2 h-2 rounded-full bg-emerald-500";
      if (els.wsStatusText) els.wsStatusText.textContent = "Веб-сокет подключён";
      appendLog("Канал логов открыт.");
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "log") {
          appendLog(data.message);
        }
      } catch (err) {
        // silently ignore malformed frames
      }
    };

    ws.onclose = () => {
      els.wsStatus.className = "w-2 h-2 rounded-full bg-gray-600";
      if (els.wsStatusText) els.wsStatusText.textContent = "Веб-сокет отключён";
      appendLog("Канал логов закрыт. Переподключение через 3 секунды…", "warn");
      setTimeout(connectLogs, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }

  /* ---------- Токен: статус ---------- */

  function setTokenStatus(ok, text) {
    if (!els.tokenStatus) return;
    els.tokenStatus.classList.remove("hidden");
    if (els.tokenStatusDot) {
      els.tokenStatusDot.className = `w-2 h-2 rounded-full ${ok ? "bg-emerald-500" : "bg-red-500"}`;
    }
    if (els.tokenStatusText) els.tokenStatusText.textContent = text;
  }

  async function checkTokenStatus() {
    try {
      const res = await fetch(`${BASE}/validate-token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: "" }), // пустой -> проверит токен из .env
      });
      const data = await res.json();
      setTokenStatus(data.ok, data.message || (data.ok ? "Токен задан" : "Токен не задан"));
    } catch (err) {
      setTokenStatus(false, "Не удалось проверить токен");
    }
  }

  /* ---------- Токен: модал ---------- */

  function openTokenModal() {
    els.tokenModal.classList.remove("hidden");
    els.tokenInput.focus();
    els.tokenResult.classList.add("hidden");
    els.tokenResult.textContent = "";
    els.validateTokenBtn.disabled = false;
    els.saveTokenBtn.disabled = true;
  }

  function closeTokenModal() {
    els.tokenModal.classList.add("hidden");
  }

  function showTokenResult(ok, text) {
    els.tokenResult.classList.remove("hidden");
    els.tokenResult.className = `p-3 rounded-lg text-sm ${ok ? "bg-emerald-500/10 border border-emerald-500/30 text-emerald-300" : "bg-red-500/10 border border-red-500/30 text-red-300"}`;
    els.tokenResult.textContent = text;
  }

  /* ---------- Сохранённые репозитории ---------- */

  async function loadSavedRepos() {
    try {
      const res = await fetch(`${BASE}/repos`);
      const repos = await res.json();
      renderSavedRepos(repos);
    } catch (err) {
      appendLog(`Не удалось загрузить список репозиториев: ${err.message}`);
    }
  }

  function renderSavedRepos(repos) {
    if (!els.savedReposList) return;
    els.savedReposList.innerHTML = "";

    if (!repos || repos.length === 0) {
      els.savedReposList.innerHTML = '<div class="text-xs text-gray-500 italic">Нет сохранённых репозиториев.</div>';
      return;
    }

    repos.forEach((repo) => {
      const div = document.createElement("div");
      div.className = "flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-black/20 border border-white/5";
      div.innerHTML = `
        <div class="flex-1 min-w-0">
          <div class="text-sm font-medium text-white truncate">${escapeHtml(repo.name || "")}</div>
          ${repo.description ? `<div class="text-xs text-gray-400 truncate">${escapeHtml(repo.description)}</div>` : ""}
          <div class="text-[10px] text-gray-500 mt-0.5 font-mono">${escapeHtml(repo.folder_path || "")}</div>
        </div>
        <div class="flex items-center gap-2">
          <a href="${escapeHtml(repo.url || `https://github.com/${repo.name}`)}" target="_blank" rel="noopener noreferrer"
             class="text-xs text-cyan-400 hover:text-cyan-300 underline">Открыть на GitHub</a>
          <button class="delete-repo-btn p-1.5 text-gray-500 hover:text-red-400 transition-colors" data-name="${escapeHtml(repo.name || "")}" title="Удалить из списка">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
          </button>
        </div>
      `;
      els.savedReposList.appendChild(div);
    });

    // Навешиваем обработчики удаления
    els.savedReposList.querySelectorAll(".delete-repo-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const name = btn.dataset.name;
        if (!confirm(`Удалить "${name}" из списка сохранённых?`)) return;
        try {
          await fetch(`${BASE}/repos/${encodeURIComponent(name)}`, { method: "DELETE" });
          loadSavedRepos();
          appendLog(`Репозиторий "${name}" удалён из списка.`);
        } catch (err) {
          appendLog(`Не удалось удалить репозиторий: ${err.message}`);
        }
      });
    });
  }

  /* ---------- API ---------- */

  async function selectFolder() {
    els.publishBtn.disabled = true;
    els.publishBtn.textContent = "Открываю диалог…";
    try {
      const res = await fetch(`${BASE}/select-folder`, { method: "POST" });
      const data = await res.json();
      els.folderPath.textContent = data.path || "(папка не выбрана)";
      els.folderPath.className =
        "mt-2 text-xs font-mono rounded-lg p-2 border " +
        (data.path ? "border-cyan-500/40 text-cyan-300 bg-cyan-500/10" : "border-white/5 text-gray-400 bg-black/20");
      if (data.path) {
        appendLog(`Папка выбрана: ${data.path}`);
      } else {
        appendLog("Выбор папки отменён пользователем.");
      }
    } catch (err) {
      appendLog(`Ошибка при выборе папки: ${err.message}`);
    } finally {
      els.publishBtn.disabled = false;
      els.publishBtn.textContent = "Опубликовать на GitHub";
    }
  }

  async function publish() {
    const payload = {
      project_name: els.projectName.value,
      description: els.description.value,
      tech_stack: els.techStack.value,
      demo_link: els.demoLink.value,
      folder_path: els.folderPath.textContent.replace("(папка не выбрана)", "").trim(),
      update_if_exists: els.updateExisting.checked,
    };

    if (!payload.project_name) {
      appendLog("Укажите название проекта.", "warn");
      els.projectName.focus();
      return;
    }
    if (!payload.folder_path) {
      appendLog("Выберите папку с проектом.", "warn");
      els.selectFolderBtn.focus();
      return;
    }

    els.publishBtn.disabled = true;
    els.publishBtn.textContent = "Идёт публикация…";

    try {
      const res = await fetch(`${BASE}/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (!res.ok) {
        appendLog(`Ошибка запуска: ${data.error || res.status}`);
        return;
      }

      appendLog("Публикация запущена. Следите за логами справа…");
    } catch (err) {
      appendLog(`Сетевая ошибка: ${err.message}`);
    } finally {
      els.publishBtn.disabled = false;
      els.publishBtn.textContent = "Опубликовать на GitHub";
    }
  }

  async function validateToken() {
    const token = els.tokenInput.value.trim();
    if (!token) {
      showTokenResult(false, "Введите токен.");
      return;
    }

    els.validateTokenBtn.disabled = true;
    els.validateTokenBtn.textContent = "Проверяю…";

    try {
      const res = await fetch(`${BASE}/validate-token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      const data = await res.json();
      showTokenResult(data.ok, data.message || (data.ok ? "Токен валиден" : "Токен не валиден"));
      if (data.ok) {
        els.saveTokenBtn.disabled = false;
      }
    } catch (err) {
      showTokenResult(false, `Ошибка проверки: ${err.message}`);
    } finally {
      els.validateTokenBtn.disabled = false;
      els.validateTokenBtn.textContent = "Проверить токен";
    }
  }

  async function saveToken() {
    const token = els.tokenInput.value.trim();
    if (!token) return;

    els.saveTokenBtn.disabled = true;
    els.saveTokenBtn.textContent = "Сохраняю…";

    try {
      const res = await fetch(`${BASE}/save-token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      const data = await res.json();
      showTokenResult(data.ok, data.message);
      if (data.ok) {
        setTokenStatus(true, "Токен задан");
        // Закрываем модал через короткую задержку, чтобы пользователь увидел результат
        setTimeout(closeTokenModal, 800);
        appendLog("GITHUB_TOKEN сохранён и проверен.");
      }
    } catch (err) {
      showTokenResult(false, `Не удалось сохранить токен: ${err.message}`);
    } finally {
      els.saveTokenBtn.disabled = false;
      els.saveTokenBtn.textContent = "Сохранить";
    }
  }

  /* ---------- Утилиты ---------- */

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  /* ---------- Инициализация ---------- */

  function init() {
    connectLogs();

    els.selectFolderBtn.addEventListener("click", selectFolder);
    els.publishBtn.addEventListener("click", publish);
    els.clearLogsBtn.addEventListener("click", clearLogs);
    els.publishForm.addEventListener("submit", (e) => e.preventDefault());

    // Токен-модал
    els.openTokenModalBtn.addEventListener("click", openTokenModal);
    els.closeTokenModalBtn.addEventListener("click", closeTokenModal);
    els.tokenModalBackdrop.addEventListener("click", closeTokenModal);
    els.validateTokenBtn.addEventListener("click", validateToken);
    els.saveTokenBtn.addEventListener("click", saveToken);

    // Закрытие модала по Escape
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !els.tokenModal.classList.contains("hidden")) {
        closeTokenModal();
      }
    });

    // Первичная проверка токена и загрузка списка репозиториев
    checkTokenStatus();
    loadSavedRepos();

    appendLog("Готов к работе. Заполните форму и нажмите «Опубликовать».", "info");
  }

  document.addEventListener("DOMContentLoaded", init);
})();
