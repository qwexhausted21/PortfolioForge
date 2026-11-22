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
let pendingPublishData = null;

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
      if (frame.type === "push_conflict") {
        pendingPublishData = {
          project_name: $("projectName").value.trim(),
          description: $("description").value.trim(),
          tech_stack: $("techStack").value.trim(),
          demo_link: $("demoLink").value.trim(),
          folder_path: folder,
          update_if_exists: $("updateExisting").checked,
          private: $("publishForm").repoVisibility.value === "private",
          branch: $("repoBranch").value.trim() || "main",
          create_release: $("createRelease").checked,
          tag: $("repoTag").value.trim() || "v0.1.0",
        };
        publishing = false;
        cancelBtn.hidden = true;
        $("publishSpinner").hidden = true;
        $("progressSection").hidden = true;
        publishBtn.lastElementChild.textContent = "Опубликовать на GitHub";
        working(false);
        $("pushConflictModal").showModal();
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
    return { project_name, description, tech_stack, demo_link, branch: $("repoBranch").value.trim() || "main", private: $("publishForm").repoVisibility.value === "private", createRelease: $("createRelease").checked, tag: $("repoTag").value.trim() || "v0.1.0" };
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
      if (saved) {
        actions.append(repoAction("Удалить из библиотеки", async () => {
          if (!confirm(`Удалить «${name}» из библиотеки?`)) return;
          try {
            await api(`/repos/${encodeURIComponent(name)}`, { method: "DELETE" });
            await loadRepos(true);
          } catch (error) {
            message("libraryResult", error.message, "error");
          }
        }));
        actions.append(repoAction("Удалить с GitHub", async () => {
          if (!confirm(`Удалить репозиторий «${name}» с GitHub? Это действие нельзя отменить.`)) return;
          try {
            await api(`/repos/${encodeURIComponent(name)}/delete-github`, { method: "DELETE" });
            await loadRepos(true);
          } catch (error) {
            message("libraryResult", error.message, "error");
          }
        }));
      }
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

  function renderPreview(text) {
    const preview = $("readmePreviewContent");
    preview.innerHTML = marked.parse(text || "");
  }

  function switchReadmeTab(tab) {
    const isEdit = tab === "edit";
    $("tabEdit").classList.toggle("active", isEdit);
    $("tabPreview").classList.toggle("active", !isEdit);
    $("readmeEditView").hidden = !isEdit;
    $("readmePreviewView").hidden = isEdit;
    if (!isEdit) renderPreview($("readmeEditor").value);
  }

  $("tabEdit").addEventListener("click", () => switchReadmeTab("edit"));
  $("tabPreview").addEventListener("click", () => switchReadmeTab("preview"));

  $("readmeEditor").addEventListener("input", () => {
    if ($("tabPreview").classList.contains("active")) renderPreview($("readmeEditor").value);
  });

  const releaseCheckbox = $("createRelease");
  const releaseVersion = $("repoTag").closest(".release-version");
  releaseCheckbox.addEventListener("change", () => {
    releaseVersion.hidden = !releaseCheckbox.checked;
  });
  activate("selectFolderBtn", selectFolder);
  $("publishForm").addEventListener("submit", publish);
  activate("clearLogsBtn", () => $("logsContainer").replaceChildren());
  activate("toggleReadmeEditorBtn", () => {
    $("readmeEditor").value = readme ?? "";
    message("readmeResult", "");
    $("readmeModal").showModal();
    $("readmeEditor").focus();
    switchReadmeTab("edit");
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

  let currentReleaseRepo = "";
  let currentReleaseTag = "";

  async function openReleaseModal(repoName) {
    // Ищем репозиторий в библиотеке, чтобы взять full_name (owner/repo)
    let fullName = repoName;
    try {
      const repos = await api("/repos");
      const found = repos.find((r) => r.name === repoName || r.full_name === repoName);
      if (found && found.full_name) fullName = found.full_name;
    } catch {
      // Игнорируем — будем использовать repoName как есть
    }
    currentReleaseRepo = fullName;
    $("releaseRepoInfo").hidden = true;
    $("releaseTagsList").replaceChildren();
    $("releaseAssetsList").replaceChildren();
    $("releaseChangelogEditor").value = "";
    $("releaseTagsView").hidden = false;
    $("releaseChangelogView").hidden = true;
    $("releaseAssetsView").hidden = true;
    $("releaseTabTags").classList.add("active");
    $("releaseTabChangelog").classList.remove("active");
    $("releaseTabAssets").classList.remove("active");
    $("releaseModal").showModal();
    await loadReleaseTags();
  }

  async function loadReleaseTags() {
    const list = $("releaseTagsList");
    list.replaceChildren();
    try {
      const { tags, error } = await api(`/repos/${encodeURIComponent(currentReleaseRepo)}/tags`);
      if (error) {
        message("releaseTagsResult", error, "error");
        return;
      }
      if (!tags.length) {
        list.textContent = "Тегов пока нет. Создайте первый релиз при публикации.";
        return;
      }
      for (const t of tags) {
        const item = document.createElement("div");
        item.className = "release-tag-item";
        const nameEl = document.createElement("div");
        nameEl.className = "tag-name";
        nameEl.textContent = t.name;
        const shaEl = document.createElement("div");
        shaEl.className = "tag-sha";
        shaEl.textContent = t.sha ? `Commit: ${t.sha.substring(0, 7)}` : "";
        const actions = document.createElement("div");
        actions.className = "tag-actions";
        actions.append(releaseTagAction("ChangeLog", () => openReleaseChangelog(t.name)));
        actions.append(releaseTagAction("Файлы", () => openReleaseAssets(t.name)));
        item.append(nameEl, shaEl, actions);
        list.append(item);
      }
    } catch (error) {
      message("releaseTagsResult", error.message, "error");
    }
  }

  async function openReleaseChangelog(tag) {
    currentReleaseTag = tag;
    $("releaseTagsView").hidden = true;
    $("releaseChangelogView").hidden = false;
    $("releaseAssetsView").hidden = true;
    $("releaseTabTags").classList.remove("active");
    $("releaseTabChangelog").classList.add("active");
    $("releaseTabAssets").classList.remove("active");
    try {
      const { release, error } = await api(`/repos/${encodeURIComponent(currentReleaseRepo)}/releases/${encodeURIComponent(tag)}`);
      if (error) {
        message("releaseChangelogResult", error, "error");
        $("releaseChangelogEditor").value = "";
        return;
      }
      $("releaseChangelogEditor").value = release.body || "";
      $("releaseChangelogResult").hidden = true;
      $("releaseChangelogEditor").dataset.tag = tag;
    } catch (error) {
      message("releaseChangelogResult", error.message, "error");
    }
  }

  async function openReleaseAssets(tag) {
    currentReleaseTag = tag;
    $("releaseTagsView").hidden = true;
    $("releaseChangelogView").hidden = true;
    $("releaseAssetsView").hidden = false;
    $("releaseTabTags").classList.remove("active");
    $("releaseTabChangelog").classList.remove("active");
    $("releaseTabAssets").classList.add("active");
    await loadReleaseAssets(tag);
  }

  async function loadReleaseAssets(tag) {
    const list = $("releaseAssetsList");
    list.replaceChildren();
    try {
      const { release, error } = await api(`/repos/${encodeURIComponent(currentReleaseRepo)}/releases/${encodeURIComponent(tag)}`);
      if (error) {
        message("releaseAssetsResult", error, "error");
        return;
      }
      const assets = release.assets || [];
      if (!assets.length) {
        list.textContent = "Файлов пока нет. Загрузите первый.";
        return;
      }
      for (const a of assets) {
        const item = document.createElement("div");
        item.className = "release-asset-item";
        const info = document.createElement("div");
        const nameEl = document.createElement("div");
        nameEl.className = "asset-name";
        nameEl.textContent = a.name;
        const sizeEl = document.createElement("div");
        sizeEl.className = "asset-size";
        sizeEl.textContent = a.size ? `${(a.size / 1024).toFixed(1)} KB` : "";
        info.append(nameEl, sizeEl);
        const link = document.createElement("a");
        link.href = a.url;
        link.textContent = "Скачать";
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        item.append(info, link);
        list.append(item);
      }
    } catch (error) {
      message("releaseAssetsResult", error.message, "error");
    }
  }

  async function saveReleaseChangelog() {
    const editor = $("releaseChangelogEditor");
    const tag = editor.dataset.tag;
    if (!tag) return;
    const btn = $("releaseChangelogSaveBtn");
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Сохраняем…";
    try {
      await api(`/repos/${encodeURIComponent(currentReleaseRepo)}/releases/${encodeURIComponent(tag)}/body`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: editor.value }),
      });
      message("releaseChangelogResult", "ChangeLog сохранён.", "ok");
    } catch (error) {
      message("releaseChangelogResult", error.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = original;
    }
  }

  async function uploadReleaseAsset() {
    const input = $("releaseAssetFile");
    if (!input.files || !input.files.length) {
      message("releaseAssetsResult", "Выберите файл.", "error");
      return;
    }
    const file = input.files[0];
    const assetName = $("releaseAssetName").value.trim() || undefined;
    const btn = $("releaseAssetUploadBtn");
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Загружаем…";
    try {
      const form = new FormData();
      form.append("file", file);
      if (assetName) form.append("asset_name", assetName);
      await api(`/repos/${encodeURIComponent(currentReleaseRepo)}/releases/${encodeURIComponent(currentReleaseTag)}/assets`, {
        method: "POST",
        body: form,
      });
      message("releaseAssetsResult", `Файл "${file.name}" загружен.`, "ok");
      input.value = "";
      $("releaseAssetName").value = "";
      await loadReleaseAssets(currentReleaseTag);
    } catch (error) {
      message("releaseAssetsResult", error.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = original;
    }
  }

  function releaseTagAction(label, callback) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "button";
    btn.textContent = label;
    btn.addEventListener("click", callback);
    return btn;
  }

  function switchReleaseTab(tab) {
    $("releaseTagsView").hidden = tab !== "tags";
    $("releaseChangelogView").hidden = tab !== "changelog";
    $("releaseAssetsView").hidden = tab !== "assets";
    $("releaseTabTags").classList.toggle("active", tab === "tags");
    $("releaseTabChangelog").classList.toggle("active", tab === "changelog");
    $("releaseTabAssets").classList.toggle("active", tab === "assets");
  }

  async function resolvePushConflict(action) {
    $("pushConflictModal").close();
    if (action === "force") {
      // Повторная публикация с force push
      await republishPending({ ...pendingPublishData, force_push: true, update_if_exists: true });
    } else if (action === "merge") {
      // Сначала pull --rebase, потом публикация
      try {
        await api("/git/pull-rebase", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ folder_path: pendingPublishData.folder_path }),
        });
        message("publishMessage", "Изменения слиты. Повторная публикация…", "ok");
        await republishPending(pendingPublishData);
      } catch (error) {
        message("publishMessage", "Ошибка слияния: " + error.message, "error");
      }
    }
    pendingPublishData = null;
  }

  async function republishPending(data) {
    publishing = true;
    cancelBtn.hidden = false;
    $("publishSpinner").hidden = false;
    $("progressSection").hidden = false;
    publishBtn.lastElementChild.textContent = "Публикуем…";
    working(true);
    try {
      await post("/publish", data);
      // Успех покажем по прогрессу 100% через WebSocket
    } catch (error) {
      message("publishMessage", error.message, "error");
      finishPublishing();
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

  $("releaseTabTags").addEventListener("click", () => switchReleaseTab("tags"));
  $("releaseTabChangelog").addEventListener("click", () => switchReleaseTab("changelog"));
  $("releaseTabAssets").addEventListener("click", () => switchReleaseTab("assets"));
  $("releaseRefreshBtn").addEventListener("click", () => loadReleaseTags());
  $("releaseChangelogSaveBtn").addEventListener("click", saveReleaseChangelog);
  $("releaseAssetUploadBtn").addEventListener("click", uploadReleaseAsset);
  $("viewTagsBtn").addEventListener("click", () => {
    const name = $("projectName").value.trim();
    if (!name) {
      message("publishMessage", "Укажите название репозитория.", "error");
      $("projectName").focus();
      return;
    }
    openReleaseModal(name);
  });

  $("pushConflictMergeBtn").addEventListener("click", () => resolvePushConflict("merge"));
  $("pushConflictForceBtn").addEventListener("click", () => resolvePushConflict("force"));

  initTheme();
  restoreLastFolder();
  connectLogs();
  checkToken();
  api("/last-published").then(({ url }) => { if (!publishing) showRepoLink(url); }).catch(() => {});
})();
