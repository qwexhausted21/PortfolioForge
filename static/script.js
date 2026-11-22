(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const activate = (id, callback) => $(id).addEventListener("click", callback);
  const projectFields = ["projectName", "description", "techStack", "demoLink"];
  const publishBtn = $("publishBtn");
  const cancelBtn = $("cancelPublishBtn");
  const themeBtn = $("toggleThemeBtn");
  const busyButtons = [publishBtn, $("selectFolderBtn"), $("toggleReadmeEditorBtn"), $("openLibraryBtn"), themeBtn];
  let folder = "";
  let readme = null;
  let publishing = false;
  let libraryRequest = 0;

  async function api(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || data.error || `Ошибка запроса (${response.status}).`);
    return data;
  }

  const post = (url, body) => api(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  function message(id, text, state = "info") {
    const element = $(id);
    element.hidden = !text;
    element.dataset.state = state;
    element.textContent = text;
  }

  function working(busy) {
    busyButtons.forEach((button) => { button.disabled = busy; });
  }

  function showReadme(text, label) {
    readme = text;
    $("readmeState").textContent = label || "Сгенерируем из данных проекта";
  }

  function progress(percent, label) {
    $("progressBar").value = percent;
    $("progressLabel").textContent = label;
  }

  function addLog(text) {
    const logs = $("logsContainer");
    const line = document.createElement("div");
    line.textContent = text;
    logs.append(line);
    if (logs.childElementCount > 200) logs.firstElementChild.remove();
    logs.scrollTop = logs.scrollHeight;
  }

  function connectLogs() {
    const socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/logs`);
    const status = $("wsStatus");
    socket.onopen = () => {
      status.dataset.state = "ok";
      status.lastElementChild.textContent = "Подключён";
    };
    socket.onmessage = ({ data }) => {
      const frame = JSON.parse(data);
      if (frame.type === "log") addLog(frame.message);
      if (frame.type === "progress" && publishing) {
        progress(frame.percent, frame.message);
        if (frame.percent >= 100) {
          message("publishMessage", "Проект опубликован на GitHub.", "ok");
          finishPublishing();
          api("/last-published").then(({ url }) => { showRepoLink(url); }).catch(() => {});
        }
      }
    };
    socket.onclose = () => {
      status.dataset.state = "error";
      status.lastElementChild.textContent = "Переподключение…";
      setTimeout(connectLogs, 3000);
    };
  }

  async function selectFolder() {
    working(true);
    message("publishMessage", "");
    try {
      const { path, repo_name } = await post("/select-folder");
      if (!path || path === folder) return;
      folder = path;
      $("folderPath").textContent = path;
      showReadme(null);
      if (repo_name) {
        $("projectName").value = repo_name;
      }
      const { content } = await post("/readme/load", { folder_path: folder });
      if (content !== null) showReadme(content, "Загружен из папки проекта");
    } catch (error) {
      message("publishMessage", error.message, "error");
    } finally {
      working(false);
    }
  }

  function projectData() {
    const [project_name, description, tech_stack, demo_link] = projectFields.map((id) => $(id).value.trim());
    return { project_name, description, tech_stack, demo_link, private: $("publishForm").repoVisibility.value === "private" };
  }

  function validProject() {
    const name = $("projectName");
    name.value = name.value.trim();
    return name.reportValidity() && $("demoLink").reportValidity();
  }

  function showRepoLink(rawUrl) {
    const link = $("goToRepoBtn");
    const url = githubUrl(rawUrl);
    link.hidden = !url;
    if (url) link.href = url;
    else link.removeAttribute("href");
  }

  async function publish(event) {
    event.preventDefault();
    if (publishBtn.disabled) return;
    message("publishMessage", "");
    if (!validProject()) return;
    if (!folder) {
      message("publishMessage", "Выберите папку с проектом.", "error");
      $("selectFolderBtn").focus();
      return;
    }
    working(true);
    publishing = true;
    cancelBtn.hidden = false;
    showRepoLink(null);
    progress(0, "Подготовка публикации…");
    $("progressSection").hidden = false;
    publishBtn.lastElementChild.textContent = "Публикуем…";
    $("publishSpinner").hidden = false;
    try {
      await post("/publish", {
        ...projectData(), folder_path: folder,
        update_if_exists: $("updateExisting").checked, readme_content: readme,
      });
      // Успех покажем по прогрессу 100% через WebSocket, а не сразу.
    } catch (error) {
      message("publishMessage", error.message, "error");
      finishPublishing();
    }
  }

  function finishPublishing() {
    publishing = false;
    cancelBtn.hidden = true;
    $("publishSpinner").hidden = true;
    $("progressSection").hidden = true;
    publishBtn.lastElementChild.textContent = "Опубликовать на GitHub";
    working(false);
  }

  cancelBtn.addEventListener("click", async () => {
    cancelBtn.disabled = true;
    try {
      await post("/publish/cancel");
      message("publishMessage", "Отменяем публикацию…", "info");
    } catch (error) {
      message("publishMessage", error.message, "error");
    } finally {
      cancelBtn.disabled = false;
    }
  });

  async function generateReadme() {
    const editor = $("readmeEditor");
    const data = projectData();
    if (!data.project_name) {
      message("readmeResult", "Чтобы сгенерировать README, укажите название репозитория в форме проекта.");
      return;
    }
    const buttons = [$("generateReadmeBtn"), $("saveReadmeBtn")];
    buttons.forEach((button) => { button.disabled = true; });
    editor.readOnly = true;
    message("readmeResult", "Генерируем README…");
    try {
      const { content } = await post("/generate-readme", data);
      if ($("readmeModal").open) editor.value = content;
      message("readmeResult", "");
    } catch (error) {
      message("readmeResult", error.message, "error");
    } finally {
      editor.readOnly = false;
      buttons.forEach((button) => { button.disabled = false; });
    }
  }

  function tokenStatus(ok, text) {
    $("tokenStatus").dataset.state = ok ? "ok" : "error";
    $("tokenStatusText").textContent = text;
  }

  async function checkToken() {
    try {
      const result = await post("/validate-token", { token: "" });
      tokenStatus(result.ok, result.ok ? "GitHub подключён" : "GitHub не подключён");
    } catch {
      tokenStatus(false, "Не удалось проверить GitHub");
    }
  }

  async function submitToken(save) {
    const token = $("tokenInput").value.trim();
    if (!token) {
      message("tokenResult", "Введите токен GitHub.", "error");
      return;
    }
    const controls = [$("tokenInput"), $("validateTokenBtn"), $("saveTokenBtn")];
    controls.forEach((control) => { control.disabled = true; });
    message("tokenResult", "Проверяем токен…");
    try {
      const data = await post(save ? "/save-token" : "/validate-token", { token });
      message("tokenResult", data.message, data.ok ? "ok" : "error");
      if (save && data.ok) {
        $("tokenInput").value = "";
        tokenStatus(true, "GitHub подключён");
      }
    } catch (error) {
      message("tokenResult", error.message, "error");
    } finally {
      controls.forEach((control) => { control.disabled = false; });
    }
  }

  function githubUrl(value) {
    try {
      const url = new URL(value);
      if (url.origin === "https://github.com" && !url.username && !url.password) return url.href;
    } catch { /* Invalid or absent URL. */ }
    return null;
  }

  function repoAction(label, callback) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button";
    button.textContent = label;
    button.addEventListener("click", callback);
    return button;
  }

  function fillProject(repo) {
    $("projectName").value = repo.name || "";
    $("description").value = repo.description || "";
    $("techStack").value = "";
    $("demoLink").value = repo.homepage || "";
    $("publishForm").repoVisibility.value = repo.private ? "private" : "public";
    $("updateExisting").checked = false;
    folder = "";
    $("folderPath").textContent = "Папка не выбрана";
    showReadme(null);
    message("publishMessage", "");
    $("libraryDrawer").close();
    $("projectName").focus();
  }

  function renderRepos(repos, saved) {
    const list = $("libraryReposList");
    list.replaceChildren();
    if (!repos.length) {
      message("libraryResult", saved ? "Библиотека пуста. Добавьте репозиторий по ссылке." : "В аккаунте нет репозиториев.");
      return;
    }
    for (const repo of repos) {
      const name = repo.full_name || repo.name;
      const item = document.createElement("article");
      const title = document.createElement("strong");
      const description = document.createElement("p");
      const actions = document.createElement("div");
      item.className = "repo-item";
      title.textContent = name;
      description.className = "hint";
      description.textContent = repo.description || "";
      actions.className = "repo-actions";
      const url = githubUrl(repo.url);
      if (url) {
        const link = document.createElement("a");
        link.className = "button";
        link.href = url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "Открыть на GitHub";
        actions.append(link);
      }
      actions.append(repoAction("Заполнить форму", () => fillProject(repo)));
      if (saved) actions.append(repoAction("Удалить из библиотеки", async () => {
        if (!confirm(`Удалить «${name}» из библиотеки?`)) return;
        try {
          await api(`/repos/${encodeURIComponent(name)}`, { method: "DELETE" });
          await loadRepos(true);
        } catch (error) {
          message("libraryResult", error.message, "error");
        }
      }));
      item.append(title, description, actions);
      list.append(item);
    }
  }

  async function loadRepos(saved) {
    const request = ++libraryRequest;
    $("libraryReposList").replaceChildren();
    $("loadSavedReposBtn").setAttribute("aria-pressed", String(saved));
    $("loadUserReposBtn").setAttribute("aria-pressed", String(!saved));
    message("libraryResult", "Загружаем репозитории…");
    try {
      const result = await api(saved ? "/repos" : "/user-repos");
      if (request !== libraryRequest) return;
      message("libraryResult", "");
      renderRepos(saved ? result : result.repos, saved);
    } catch (error) {
      if (request === libraryRequest) message("libraryResult", error.message, "error");
    }
  }

  document.querySelectorAll("dialog").forEach((dialog) => {
    dialog.querySelector("[data-close]").addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
  });
  activate("selectFolderBtn", selectFolder);
  $("publishForm").addEventListener("submit", publish);
  activate("clearLogsBtn", () => $("logsContainer").replaceChildren());
  activate("toggleReadmeEditorBtn", () => {
    $("readmeEditor").value = readme ?? "";
    message("readmeResult", "");
    $("readmeModal").showModal();
    $("readmeEditor").focus();
    if (readme === null && !$("generateReadmeBtn").disabled) generateReadme();
  });
  activate("generateReadmeBtn", generateReadme);
  activate("saveReadmeBtn", () => {
    showReadme($("readmeEditor").value, "Сохранён в редакторе");
    $("readmeModal").close();
  });
  activate("openTokenModalBtn", () => {
    message("tokenResult", "");
    $("tokenModal").showModal();
    $("tokenInput").focus();
  });
  $("tokenModal").addEventListener("close", () => { $("tokenInput").value = ""; });
  activate("validateTokenBtn", () => submitToken(false));
  activate("saveTokenBtn", () => submitToken(true));
  activate("openLibraryBtn", () => {
    $("libraryDrawer").showModal();
    loadRepos(true);
  });
  activate("loadSavedReposBtn", () => loadRepos(true));
  activate("loadUserReposBtn", () => loadRepos(false));
  $("manualAddForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("manualRepoUrl");
    const button = event.submitter;
    button.disabled = true;
    try {
      await post("/repos/manual", { url: input.value.trim() });
      input.value = "";
      await loadRepos(true);
    } catch (error) {
      message("libraryResult", error.message, "error");
    } finally {
      button.disabled = false;
    }
  });

  async function restoreLastFolder() {
    try {
      const { folder: saved } = await api("/last-folder");
      if (saved) {
        folder = saved;
        $("folderPath").textContent = saved;
        const { content } = await post("/readme/load", { folder_path: saved });
        if (content !== null) showReadme(content, "Загружен из папки проекта");
      }
    } catch {
      // Игнорируем — папка будет выбрана вручную
    }
  }

  function initTheme() {
    const saved = localStorage.getItem("portfolioforge-theme");
    const dark = saved === "dark" || (!saved && window.matchMedia("(prefers-color-scheme: dark)").matches);
    if (dark) {
      document.documentElement.dataset.theme = "dark";
      themeBtn.querySelector("use").setAttribute("href", "#i-sun");
    } else {
      document.documentElement.dataset.theme = "light";
      themeBtn.querySelector("use").setAttribute("href", "#i-moon");
    }
  }

  themeBtn.addEventListener("click", () => {
    const isDark = document.documentElement.dataset.theme === "dark";
    if (isDark) {
      document.documentElement.dataset.theme = "light";
      localStorage.setItem("portfolioforge-theme", "light");
      themeBtn.querySelector("use").setAttribute("href", "#i-moon");
    } else {
      document.documentElement.dataset.theme = "dark";
      localStorage.setItem("portfolioforge-theme", "dark");
      themeBtn.querySelector("use").setAttribute("href", "#i-sun");
    }
  });

  initTheme();
  restoreLastFolder();
  connectLogs();
  checkToken();
  api("/last-published").then(({ url }) => { if (!publishing) showRepoLink(url); }).catch(() => {});
})();
