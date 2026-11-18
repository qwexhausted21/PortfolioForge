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
    goToRepoBtn: document.getElementById("goToRepoBtn"),
    savedReposList: document.getElementById("libraryReposList"),

    // Редактор README (модал)
    toggleReadmeEditorBtn: document.getElementById("toggleReadmeEditorBtn"),
    readmeModal: document.getElementById("readmeModal"),
    readmeModalBackdrop: document.getElementById("readmeModalBackdrop"),
    closeReadmeModalBtn: document.getElementById("closeReadmeModalBtn"),
    readmeEditor: document.getElementById("readmeEditor"),
    saveReadmeBtn: document.getElementById("saveReadmeBtn"),
    readmeEditorVisible: false,
    readmeManualContent: null,

    // Прогресс-бар
    progressSection: document.getElementById("progressSection"),
    progressBar: document.getElementById("progressBar"),
    progressPercent: document.getElementById("progressPercent"),
    progressLabel: document.getElementById("progressLabel"),

    // Логи
    toggleLogsBtn: document.getElementById("toggleLogsBtn"),
    logsContainer: document.getElementById("logsContainer"),

    // Библиотека (drawer)
    openLibraryBtn: document.getElementById("openLibraryBtn"),
    libraryDrawer: document.getElementById("libraryDrawer"),
    libraryBackdrop: document.getElementById("libraryBackdrop"),
    closeLibraryBtn: document.getElementById("closeLibraryBtn"),
    loadUserReposBtn: document.getElementById("loadUserReposBtn"),
    showManualAddBtn: document.getElementById("showManualAddBtn"),
    manualAddForm: document.getElementById("manualAddForm"),
    manualRepoUrl: document.getElementById("manualRepoUrl"),
    addManualRepoBtn: document.getElementById("addManualRepoBtn"),

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

    // Диалог конфликта пуша
    pushConflictModal: document.getElementById("pushConflictModal"),
    pushConflictBackdrop: document.getElementById("pushConflictBackdrop"),
    pushMergeBtn: document.getElementById("pushMergeBtn"),
    pushForceBtn: document.getElementById("pushForceBtn"),
    pendingPush: null,
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
        } else if (data.type === "progress") {
          updateProgress(data.percent, data.message);
        } else if (data.type === "push_conflict") {
          appendLog("Конфликт пуша: на GitHub есть новые изменения.");
          openPushConflictModal({
            project_name: data.project_name,
            folder_path: data.folder_path,
          });
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
      renderLibraryRepos(repos || []);
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
        // Подгружаем существующий README.md, если есть
        await loadExistingReadme(data.path);
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

  /* ---------- Загрузка существующего README.md ---------- */

  async function loadExistingReadme(folderPath) {
    if (!folderPath) return;
    try {
      const res = await fetch(`${BASE}/readme/load`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder_path: folderPath }),
      });
      const data = await res.json();
      if (data.content) {
        els.readmeManualContent = data.content;
        appendLog("Найден существующий README.md в папке проекта.");
      } else {
        els.readmeManualContent = null;
      }
    } catch (err) {
      // silently ignore — folder may not have README yet
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
      private: document.querySelector('input[name="repoVisibility"]:checked').value === "private",
      readme_content: els.readmeManualContent || undefined,
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

    // Сброс прогресс-бара
    els.progressSection.classList.remove("hidden");
    els.progressBar.style.width = "0%";
    els.progressPercent.textContent = "0%";
    els.progressLabel.textContent = "Начало публикации…";

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
        // Проверяем, есть ли конфликт пуша (409)
        if (res.status === 409) {
          appendLog("Конфликт пуша: на GitHub есть новые изменения.");
          openPushConflictModal(payload);
        } else {
          appendLog(`Ошибка запуска: ${data.error || res.status}`);
        }
        els.progressSection.classList.add("hidden");
        return;
      }

      appendLog("Публикация запущена. Следите за логами справа…");
    } catch (err) {
      appendLog(`Сетевая ошибка: ${err.message}`);
      els.progressSection.classList.add("hidden");
    } finally {
      els.publishBtn.disabled = false;
      els.publishBtn.textContent = "Опубликовать на GitHub";
    }
  }

  /* ---------- Редактор README (модал) ---------- */

  async function openReadmeModal() {
    if (els.readmeModal) els.readmeModal.classList.remove("hidden");
    if (els.readmeModalBackdrop) els.readmeModalBackdrop.classList.remove("hidden");
    // Если уже есть загруженный из папки контент — показываем его, иначе генерируем
    if (els.readmeManualContent) {
      els.readmeEditor.value = els.readmeManualContent;
    } else {
      await generateReadmePreview();
    }
    els.readmeEditor.focus();
  }

  function closeReadmeModal() {
    if (els.readmeModal) els.readmeModal.classList.add("hidden");
    if (els.readmeModalBackdrop) els.readmeModalBackdrop.classList.add("hidden");
  }

  async function generateReadmePreview() {
    const payload = {
      project_name: els.projectName.value,
      description: els.description.value,
      tech_stack: els.techStack.value,
      demo_link: els.demoLink.value,
      private: document.querySelector('input[name="repoVisibility"]:checked').value === "private",
    };

    if (!payload.project_name) {
      els.readmeEditor.value = "Заполните название проекта для генерации README…";
      return;
    }

    try {
      const res = await fetch(`${BASE}/generate-readme`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.content) {
        els.readmeEditor.value = data.content;
      } else {
        els.readmeEditor.value = `Ошибка генерации: ${data.error || "неизвестная ошибка"}`;
      }
    } catch (err) {
      els.readmeEditor.value = `Ошибка генерации README: ${err.message}`;
    }
  }

  function saveReadmeContent() {
    els.readmeManualContent = els.readmeEditor.value.trim() || null;
    closeReadmeModal();
    appendLog("README.md отредактирован вручную.");
  }

  /* ---------- Прогресс-бар ---------- */

  function updateProgress(percent, message) {
    els.progressSection.classList.remove("hidden");
    els.progressBar.style.width = percent + "%";
    els.progressPercent.textContent = percent + "%";
    if (message) {
      els.progressLabel.textContent = message;
    }
    if (percent >= 100) {
      setTimeout(() => {
        els.progressSection.classList.add("hidden");
      }, 1500);
    }
  }

  /* ---------- Логи: показать/скрыть ---------- */

  let logsVisible = false;

  function toggleLogs() {
    logsVisible = !logsVisible;
    els.logsContainer.classList.toggle("hidden", !logsVisible);
    els.toggleLogsBtn.innerHTML = logsVisible
      ? `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`
      : `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.482 7.225 8.016 4 13.542 4c5.537 0 10.071 3.225 11.095 8 1.017 4.772-4.963 8-10.595 8-5.537 0-10.071-3.225-11.095-8zM12 14l2-2 2 2m-1-5.036a3 3 0 11-5.364 0"></path></svg>`;
    els.toggleLogsBtn.title = logsVisible ? "Скрыть логи" : "Показать логи";
  }

  /* ---------- Диалог конфликта пуша ---------- */

  function openPushConflictModal(payload) {
    els.pendingPush = payload;
    if (els.pushConflictModal) els.pushConflictModal.classList.remove("hidden");
    if (els.pushConflictBackdrop) els.pushConflictBackdrop.classList.remove("hidden");
  }

  function closePushConflictModal() {
    if (els.pushConflictModal) els.pushConflictModal.classList.add("hidden");
    if (els.pushConflictBackdrop) els.pushConflictBackdrop.classList.add("hidden");
    els.pendingPush = null;
  }

  async function resolvePushMerge() {
    closePushConflictModal();
    appendLog("Разрешение конфликта: сливаю с локальными…");
    // Делаем pull --rebase, потом повторяем push
    try {
      const res = await fetch(`${BASE}/git/pull-rebase`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder_path: els.folderPath.textContent.replace("(папка не выбрана)", "").trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        appendLog(`Ошибка pull: ${data.error || res.status}`);
        if (data.error === "stash_pop_conflict") {
          appendLog(`Детали: ${data.message}`);
        }
        return;
      }
      appendLog("Пул выполнен. Повторяю публикацию…");
      // Просто делаем git push в текущей папке (не пересоздаём репозиторий)
      try {
        const pushRes = await fetch(`${BASE}/git/push`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ folder_path: els.folderPath.textContent.replace("(папка не выбрана)", "").trim() }),
        });
        const pushData = await pushRes.json();
        if (!pushRes.ok) {
          appendLog(`Ошибка пуша: ${pushData.error || pushRes.status}`);
          return;
        }
        appendLog("Пуш выполнен успешно!");
        appendLog(pushData.output || "");
      } catch (err) {
        appendLog(`Ошибка при пуше: ${err.message}`);
      }
    } catch (err) {
      appendLog(`Ошибка при пуле: ${err.message}`);
    }
  }

  async function resolvePushForce() {
    closePushConflictModal();
    appendLog("Разрешение конфликта: force push на GitHub…");
    if (els.pendingPush) {
      els.pendingPush.update_if_exists = true;
      publishWithPayload(els.pendingPush);
    }
  }

  async function publishWithPayload(payload) {
    els.publishBtn.disabled = true;
    els.publishBtn.textContent = "Идёт публикация…";

    // Сброс прогресс-бара
    els.progressSection.classList.remove("hidden");
    els.progressBar.style.width = "0%";
    els.progressPercent.textContent = "0%";
    els.progressLabel.textContent = "Начало публикации…";

    try {
      const res = await fetch(`${BASE}/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (!res.ok) {
        appendLog(`Ошибка запуска: ${data.error || res.status}`);
        els.progressSection.classList.add("hidden");
        return;
      }

      appendLog("Публикация запущена. Следите за логами справа…");
    } catch (err) {
      appendLog(`Сетевая ошибка: ${err.message}`);
      els.progressSection.classList.add("hidden");
    } finally {
      els.publishBtn.disabled = false;
      els.publishBtn.textContent = "Опубликовать на GitHub";
    }
  }

  /* ---------- Кнопка «Перейти к репозиторию» ---------- */

  async function loadLastPublishedUrl() {
    try {
      const res = await fetch(`${BASE}/last-published`);
      const data = await res.json();
      if (data.url) {
        els.goToRepoBtn.classList.remove("hidden");
        els.goToRepoBtn.onclick = () => {
          window.open(data.url, "_blank");
        };
      }
    } catch (err) {
      // silently ignore
    }
  }

  function openLastPublishedRepo() {
    if (els.goToRepoBtn && !els.goToRepoBtn.classList.contains("hidden")) {
      // URL уже привязан через onclick
      els.goToRepoBtn.click();
    }
  }

  /* ---------- Библиотека: drawer ---------- */

  function openLibraryDrawer() {
    if (els.libraryDrawer) els.libraryDrawer.classList.remove("translate-x-full");
    if (els.libraryBackdrop) els.libraryBackdrop.classList.remove("hidden");
  }

  function closeLibraryDrawer() {
    if (els.libraryDrawer) els.libraryDrawer.classList.add("translate-x-full");
    if (els.libraryBackdrop) els.libraryBackdrop.classList.add("hidden");
  }

  /* ---------- Библиотека: загрузка из GitHub ---------- */

  async function loadUserRepos() {
    try {
      const res = await fetch(`${BASE}/user-repos`);
      const data = await res.json();
      if (data.error) {
        appendLog(`Не удалось загрузить репозитории из GitHub: ${data.error}`);
        return;
      }
      renderLibraryRepos(data.repos || []);
      appendLog(`Загружено репозиториев из GitHub: ${data.repos ? data.repos.length : 0}`);
    } catch (err) {
      appendLog(`Ошибка при загрузке репозиториев из GitHub: ${err.message}`);
    }
  }

  /* ---------- Библиотека: ручное добавление ---------- */

  async function addManualRepo() {
    const url = els.manualRepoUrl.value.trim();
    if (!url) return;

    els.addManualRepoBtn.disabled = true;
    els.addManualRepoBtn.textContent = "Добавляю…";

    try {
      const res = await fetch(`${BASE}/repos/manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();
      if (data.ok) {
        els.manualRepoUrl.value = "";
        renderLibraryRepos(data.repos || []);
        appendLog(`Репозиторий добавлен в библиотеку: ${url}`);
      } else {
        appendLog(`Ошибка добавления: ${data.message || "неизвестная ошибка"}`);
      }
    } catch (err) {
      appendLog(`Сетевая ошибка при добавлении: ${err.message}`);
    } finally {
      els.addManualRepoBtn.disabled = false;
      els.addManualRepoBtn.textContent = "Добавить";
    }
  }

  /* ---------- Библиотека: рендеринг ---------- */

  function renderLibraryRepos(repos) {
    if (!els.savedReposList) return;
    els.savedReposList.innerHTML = "";

    if (!repos || repos.length === 0) {
      els.savedReposList.innerHTML = '<div class="text-xs text-gray-500 italic">Библиотека пуста. Загрузите репозитории из GitHub или добавьте их вручную.</div>';
      return;
    }

    repos.forEach((repo) => {
      const div = document.createElement("div");
      div.className = "flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-black/20 border border-white/5";
      const repoUrl = repo.url || `https://github.com/${repo.full_name || repo.name}`;
      div.innerHTML = `
        <div class="flex-1 min-w-0">
          <div class="text-sm font-medium text-white truncate">${escapeHtml(repo.full_name || repo.name || "")}</div>
          ${repo.description ? `<div class="text-xs text-gray-400 truncate">${escapeHtml(repo.description)}</div>` : ""}
          <div class="text-[10px] text-gray-500 mt-0.5 font-mono">${escapeHtml(repo.url || "")}</div>
        </div>
        <div class="flex items-center gap-2">
          <a href="${escapeHtml(repoUrl)}" target="_blank" rel="noopener noreferrer"
             class="text-xs text-cyan-400 hover:text-cyan-300 underline">Открыть на GitHub</a>
          <button class="delete-repo-btn p-1.5 text-gray-500 hover:text-red-400 transition-colors" data-name="${escapeHtml(repo.full_name || repo.name || "")}" title="Удалить из библиотеки">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
          </button>
        </div>
      `;
      els.savedReposList.appendChild(div);
    });

    els.savedReposList.querySelectorAll(".delete-repo-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const name = btn.dataset.name;
        if (!confirm(`Удалить "${name}" из библиотеки?`)) return;
        try {
          await fetch(`${BASE}/repos/${encodeURIComponent(name)}`, { method: "DELETE" });
          loadSavedRepos();
          appendLog(`Репозиторий "${name}" удалён из библиотеки.`);
        } catch (err) {
          appendLog(`Не удалось удалить репозиторий: ${err.message}`);
        }
      });
    });
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

  /* ---------- Вспомогательная функция для безопасной подписки ---------- */

  function safeAddEventListener(el, event, handler) {
    if (el) {
      el.addEventListener(event, handler);
    }
  }

  /* ---------- Инициализация ---------- */

  function init() {
    connectLogs();

    safeAddEventListener(els.selectFolderBtn, "click", selectFolder);
    safeAddEventListener(els.publishBtn, "click", publish);
    safeAddEventListener(els.clearLogsBtn, "click", clearLogs);
    if (els.publishForm) {
      els.publishForm.addEventListener("submit", (e) => e.preventDefault());
    }

    // Редактор README (модал)
    safeAddEventListener(els.toggleReadmeEditorBtn, "click", openReadmeModal);
    safeAddEventListener(els.closeReadmeModalBtn, "click", closeReadmeModal);
    safeAddEventListener(els.readmeModalBackdrop, "click", closeReadmeModal);
    safeAddEventListener(els.saveReadmeBtn, "click", saveReadmeContent);
    safeAddEventListener(els.cancelReadmeBtn, "click", closeReadmeModal);

    // Автогенерация при изменении полей (если модал открыт)
    const readmeFields = [els.projectName, els.description, els.techStack, els.demoLink];
    readmeFields.forEach((field) => {
      if (field) {
        field.addEventListener("input", () => {
          if (els.readmeModal && !els.readmeModal.classList.contains("hidden")) generateReadmePreview();
        });
      }
    });
    document.querySelectorAll('input[name="repoVisibility"]').forEach((radio) => {
      radio.addEventListener("change", () => {
        if (els.readmeModal && !els.readmeModal.classList.contains("hidden")) generateReadmePreview();
      });
    });

    // Логи: показать/скрыть
    safeAddEventListener(els.toggleLogsBtn, "click", toggleLogs);

    // Диалог конфликта пуша
    safeAddEventListener(els.pushConflictBackdrop, "click", closePushConflictModal);
    safeAddEventListener(els.pushMergeBtn, "click", resolvePushMerge);
    safeAddEventListener(els.pushForceBtn, "click", resolvePushForce);

    // Библиотека
    safeAddEventListener(els.openLibraryBtn, "click", openLibraryDrawer);
    safeAddEventListener(els.closeLibraryBtn, "click", closeLibraryDrawer);
    safeAddEventListener(els.libraryBackdrop, "click", closeLibraryDrawer);
    safeAddEventListener(els.loadUserReposBtn, "click", loadUserRepos);
    safeAddEventListener(els.showManualAddBtn, "click", () => {
      if (els.manualAddForm) els.manualAddForm.classList.toggle("hidden");
    });
    safeAddEventListener(els.addManualRepoBtn, "click", addManualRepo);
    safeAddEventListener(els.manualRepoUrl, "keypress", (e) => {
      if (e.key === "Enter") addManualRepo();
    });

    // Закрытие drawer по Escape
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && els.libraryDrawer && !els.libraryDrawer.classList.contains("translate-x-full")) {
        closeLibraryDrawer();
      }
    });

    // Токен-модал
    safeAddEventListener(els.openTokenModalBtn, "click", openTokenModal);
    safeAddEventListener(els.closeTokenModalBtn, "click", closeTokenModal);
    safeAddEventListener(els.tokenModalBackdrop, "click", closeTokenModal);
    safeAddEventListener(els.validateTokenBtn, "click", validateToken);
    safeAddEventListener(els.saveTokenBtn, "click", saveToken);

    // Закрытие модала по Escape
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && els.tokenModal && !els.tokenModal.classList.contains("hidden")) {
        closeTokenModal();
      }
    });

    // Первичная проверка токена, загрузка библиотеки и последнего опубликованного репозитория
    checkTokenStatus();
    loadSavedRepos();
    loadLastPublishedUrl();

    appendLog("Готов к работе. Заполните форму и нажмите «Опубликовать».", "info");
  }

  document.addEventListener("DOMContentLoaded", init);
})();
