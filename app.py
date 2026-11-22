"""Точка входа PortfolioForge: локальный FastAPI-бэкенд + рабочее окно pywebview.

Модуль поднимает uvicorn в фоновом потоке, отдаёт фронтенд и статику через FastAPI,
проксирует логи в браузер по WebSocket и запускает публикацию при нажатии кнопки.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import re
import subprocess
import threading
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import uvicorn
import webview
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from github_manager import GitHubManager, GitPushConflictError, _safe_github_call
from readme_generator import generate_readme, generate_readme_content, load_existing_readme

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)

APP_TITLE = "PortfolioForge"
HOST = "127.0.0.1"
PORT = int(os.getenv("PORT", "8081"))

# Имя репозитория GitHub: латиница, цифры, точка, дефис, подчёркивание.
REPO_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")

# Имя ветки Git: латиница, цифры, точка, дефис, подчёркивание, слэш.
BRANCH_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-/]+$")

# URL последнего опубликованного репозитория (для кнопки «Перейти к репозиторию»)
last_published_repo_url: str | None = None

# Флаг отмены текущей публикации (взаимодействие между потоками)
publish_cancel_event: threading.Event | None = None

app = FastAPI(title=APP_TITLE)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

logger = logging.getLogger("portfolioforge")
logger.setLevel(logging.INFO)

# --- Брокер логов: рассылает записи фронтенду через WebSocket -----------------
ws_loop: asyncio.AbstractEventLoop | None = None
ws_clients: set[WebSocket] = set()
log_buffer: deque[str] = deque(maxlen=200)
_ws_lock = asyncio.Lock()


class WebSocketLogHandler(logging.Handler):
    """Лог-обработчик: пересылает каждую запись всем подключённым клиентам."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:
            return
        log_buffer.append(message)
        if ws_loop is None or not ws_clients:
            return
        payload = json.dumps({"type": "log", "message": message})
        disconnected: list[WebSocket] = []
        for client in list(ws_clients):
            try:
                asyncio.run_coroutine_threadsafe(client.send_text(payload), ws_loop)
            except Exception:
                disconnected.append(client)
        for client in disconnected:
            ws_clients.discard(client)


async def _broadcast_to_clients(payload: str) -> None:
    """Thread-safe broadcast to all WebSocket clients."""
    if ws_loop is None or not ws_clients:
        return
    async with _ws_lock:
        disconnected: list[WebSocket] = []
        for client in list(ws_clients):
            try:
                await client.send_text(payload)
            except Exception:
                disconnected.append(client)
        for client in disconnected:
            ws_clients.discard(client)


formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")

ws_handler = WebSocketLogHandler()
ws_handler.setFormatter(formatter)
logger.addHandler(ws_handler)

# Дублируем логи в консоль сервера
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# --- Файловое логирование в папку logs/ --------------------------------------
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

file_handler = RotatingFileHandler(
    LOGS_DIR / "app.log",
    maxBytes=5 * 1024 * 1024,  # 5 МБ на файл
    backupCount=5,             # хранить 5 старых файлов
    encoding="utf-8",
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


def log_info(message: str) -> None:
    logger.info(message)


async def broadcast_progress(percent: int, message: str) -> None:
    """Отправляет прогресс-обновление всем подключённым WebSocket-клиентам."""
    payload = json.dumps({"type": "progress", "percent": percent, "message": message})
    await _broadcast_to_clients(payload)


# --- Хранилище сохранённых репозиториев ---------------------------------------
REPOS_FILE = BASE_DIR / "saved_repos.json"

# --- Хранилище последней выбранной папки -------------------------------------
LAST_FOLDER_FILE = BASE_DIR / "last_folder.json"


def _load_last_folder() -> str | None:
    """Возвращает последний выбранный пользователем путь к папке проекта."""
    if not LAST_FOLDER_FILE.exists():
        return None
    try:
        data = json.loads(LAST_FOLDER_FILE.read_text(encoding="utf-8"))
        return data.get("folder")
    except (json.JSONDecodeError, OSError):
        return None


def _save_last_folder(folder_path: str) -> None:
    """Сохраняет последний выбранный путь к папке между запусками приложения."""
    LAST_FOLDER_FILE.write_text(
        json.dumps({"folder": folder_path}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_repos() -> list[dict[str, Any]]:
    """Загружает список сохранённых репозиториев из JSON."""
    if not REPOS_FILE.exists():
        return []
    try:
        return json.loads(REPOS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_repos(repos: list[dict[str, Any]]) -> None:
    """Сохраняет список репозиториев в JSON."""
    REPOS_FILE.write_text(json.dumps(repos, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_last_published_url() -> str | None:
    """Возвращает URL последнего опубликованного репозитория из сохранённых."""
    repos = _load_repos()
    if not repos:
        return None
    # Берём самый новый по updated_at
    repos_sorted = sorted(
        repos,
        key=lambda r: r.get("updated_at", ""),
        reverse=True
    )
    return repos_sorted[0].get("url")


@app.on_event("startup")
async def _startup() -> None:
    """Запоминает запущенный event loop uvicorn для межпоточной отправки логов."""
    global ws_loop
    ws_loop = asyncio.get_running_loop()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Отдаёт главную страницу UI."""
    return templates.TemplateResponse(
        "index.html", {"request": request, "title": APP_TITLE}
    )


@app.post("/select-folder")
async def select_folder() -> JSONResponse:
    """Открывает системный диалог выбора папки.

    Сначала пытается использовать pywebview (работает на headless Linux с X11/Wayland),
    затем fallback на tkinter.
    """
    folder = None

    # Попытка 1: pywebview (нативный диалог ОС, работает без tkinter)
    try:
        import webview
        # Создаем невидимое окно для диалога
        window = webview.create_window(
            "Выберите папку с проектом",
            hidden=True,
            frameless=True
        )
        # pywebview не имеет встроенного folder dialog, используем tkinter через webview
        # Но webview может вызвать JS dialog... проще: используем tkinter в отдельном процессе
    except Exception:
        pass

    # Попытка 2: tkinter (Windows/macOS с GUI)
    try:
        import tkinter
        import tkinter.filedialog

        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = tkinter.filedialog.askdirectory(title="Выберите папку с проектом")
        root.destroy()
    except Exception as e:
        log_info(f"tkinter недоступен: {e}")
        folder = None

    # Попытка 3: zenity/kdialog (Linux headless с GUI)
    if folder is None:
        import subprocess
        for cmd in [["zenity", "--file-selection", "--directory", "--title=Выберите папку с проектом"],
                    ["kdialog", "--getexistingdirectory", "--title", "Выберите папку с проектом"]]:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0 and result.stdout.strip():
                    folder = result.stdout.strip()
                    break
            except Exception:
                continue

    if folder:
        folder_path = Path(folder).resolve()
        log_info(f"Выбрана папка: {folder}")
        _save_last_folder(str(folder_path))

        # Название репозитория — имя выбранной папки
        repo_name = folder_path.name
        return JSONResponse({"path": str(folder_path), "repo_name": repo_name})
    return JSONResponse({"path": "", "error": "Диалог выбора папки недоступен или отменён пользователем"})


@app.post("/generate-readme")
async def generate_readme_endpoint(request: Request) -> JSONResponse:
    """Генерирует содержимое README.md для предпросмотра и редактирования."""
    data: dict[str, Any] = await request.json()
    project_name = (data.get("project_name") or "").strip()
    description = (data.get("description") or "").strip()
    tech_stack = (data.get("tech_stack") or "").strip()
    demo_link = (data.get("demo_link") or "").strip()
    private = bool(data.get("private"))

    if not project_name:
        return JSONResponse({"error": "Укажите название проекта"}, status_code=400)

    content = generate_readme_content(
        project_name, description, tech_stack, demo_link, private
    )
    return JSONResponse({"content": content})


@app.post("/validate-token")
async def validate_token(request: Request) -> JSONResponse:
    """Проверяет работоспособность переданного GitHub-токена."""
    data: dict[str, Any] = await request.json()
    token = (data.get("token") or "").strip()
    manager = GitHubManager(env_path=ENV_PATH)
    ok, message = manager.validate_token(token)
    return JSONResponse({"ok": ok, "message": message})


@app.post("/save-token")
async def save_token(request: Request) -> JSONResponse:
    """Сохраняет токен в .env и переинициализирует менеджер."""
    data: dict[str, Any] = await request.json()
    token = (data.get("token") or "").strip()
    if not token:
        return JSONResponse({"ok": False, "message": "Токен не может быть пустым."}, status_code=400)

    manager = GitHubManager(env_path=ENV_PATH)
    try:
        manager.save_token(token)
        ok, message = manager.validate_token(token)
        if not ok:
            return JSONResponse({"ok": False, "message": message}, status_code=400)
        log_info("GITHUB_TOKEN сохранён в .env и прошёл валидацию.")
        return JSONResponse({"ok": True, "message": "Токен сохранён и подтверждён."})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "message": f"Не удалось сохранить токен: {exc}"}, status_code=500)


@app.get("/repos")
async def list_repos() -> JSONResponse:
    """Возвращает список сохранённых репозиториев."""
    return JSONResponse(_load_repos())


@app.post("/repos")
async def add_repo(request: Request) -> JSONResponse:
    """Сохраняет информацию об опубликованном репозитории."""
    data: dict[str, Any] = await request.json()
    repos = _load_repos()
    # Не дублируем по имени
    repos = [r for r in repos if r.get("name") != data.get("name")]
    repos.insert(0, data)
    _save_repos(repos)
    return JSONResponse({"ok": True, "repos": repos})


@app.delete("/repos/{name}")
async def delete_repo(name: str) -> JSONResponse:
    """Удаляет репозиторий из списка сохранённых."""
    repos = [r for r in _load_repos() if r.get("name") != name]
    _save_repos(repos)
    return JSONResponse({"ok": True})


@app.get("/last-published")
async def get_last_published() -> JSONResponse:
    """Возвращает URL последнего опубликованного репозитория."""
    return JSONResponse({"url": _get_last_published_url()})


@app.get("/last-folder")
async def get_last_folder() -> JSONResponse:
    """Возвращает последний выбранный путь к папке проекта."""
    return JSONResponse({"folder": _load_last_folder()})


@app.get("/user-repos")
async def list_user_repos() -> JSONResponse:
    """Возвращает список репозиториев пользователя из GitHub API."""
    manager = GitHubManager(env_path=ENV_PATH)
    if not manager.github or not manager.token:
        return JSONResponse({"repos": [], "error": "Токен не задан"}, status_code=400)
    try:
        user = manager.github.get_user()
        repos = []
        for repo in user.get_repos():
            repos.append(
                {
                    "name": repo.name,
                    "full_name": repo.full_name,
                    "description": repo.description or "",
                    "url": repo.html_url,
                    "private": repo.private,
                }
            )
        return JSONResponse({"repos": repos})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"repos": [], "error": str(exc)}, status_code=500)


@app.post("/repos/manual")
async def add_manual_repo(request: Request) -> JSONResponse:
    """Добавляет репозиторий в библиотеку вручную по ссылке с GitHub."""
    data: dict[str, Any] = await request.json()
    url = (data.get("url") or "").strip()
    if not url:
        return JSONResponse({"ok": False, "message": "Укажите ссылку на репозиторий"}, status_code=400)

    # Парсим ссылку вида https://github.com/owner/repo
    parts = url.rstrip("/").split("/")
    if len(parts) < 5 or parts[2] != "github.com":
        return JSONResponse(
            {"ok": False, "message": "Неверная ссылка. Ожидается https://github.com/owner/repo"},
            status_code=400,
        )
    owner = parts[3]
    repo_name = parts[4]
    full_name = f"{owner}/{repo_name}"

    # Пытаемся получить описание через GitHub API
    description = ""
    try:
        manager = GitHubManager(env_path=ENV_PATH)
        if manager.github and manager.token:
            repo = _safe_github_call(manager.github.get_repo, full_name)
            description = repo.description or ""
    except Exception:
        pass

    repos = _load_repos()
    repos = [r for r in repos if r.get("full_name") != full_name]
    repos.insert(
        0,
        {
            "name": repo_name,
            "full_name": full_name,
            "description": description,
            "url": url,
            "private": False,
            "manual": True,
            "added_at": datetime.datetime.now().isoformat(),
        },
    )
    _save_repos(repos)
    return JSONResponse({"ok": True, "repos": repos})


@app.get("/repos/{name}/details")
async def get_repo_details(name: str) -> JSONResponse:
    """Возвращает детали репозитория для автозаполнения формы."""
    repos = _load_repos()
    for repo in repos:
        if repo.get("name") == name or repo.get("full_name") == name:
            # Дополняем данными из GitHub API, если возможно
            full_name = repo.get("full_name", "")
            description = repo.get("description", "")
            if full_name and "/" in full_name:
                try:
                    manager = GitHubManager(env_path=ENV_PATH)
                    if manager.github and manager.token:
                        gh_repo = _safe_github_call(manager.github.get_repo, full_name)
                        description = gh_repo.description or description
                except Exception:
                    pass
            return JSONResponse({
                "ok": True,
                "repo": {
                    "name": repo.get("name", ""),
                    "full_name": full_name,
                    "description": description,
                    "url": repo.get("url", ""),
                    "private": repo.get("private", False),
                }
            })
    return JSONResponse({"ok": False, "message": "Репозиторий не найден в библиотеке"}, status_code=404)


@app.post("/readme/load")
async def readme_load(request: Request) -> JSONResponse:
    """Загружает существующий README.md из выбранной папки проекта."""
    data: dict[str, Any] = await request.json()
    folder_path = (data.get("folder_path") or "").strip()
    if not folder_path:
        return JSONResponse({"content": None})
    content = load_existing_readme(folder_path)
    return JSONResponse({"content": content})


@app.post("/git/pull-rebase")
async def git_pull_rebase(request: Request) -> JSONResponse:
    """Выполняет git pull --rebase в указанной папке.

    Перед пулом делает git stash, если есть несохранённые изменения,
    а после пула — git stash pop, чтобы вернуть изменения обратно.
    """
    import subprocess

    data: dict[str, Any] = await request.json()
    folder_path = (data.get("folder_path") or "").strip()
    if not folder_path:
        return JSONResponse({"error": "Укажите папку"}, status_code=400)

    folder = Path(folder_path).resolve()
    if not folder.is_dir():
        return JSONResponse({"error": f"Папка не найдена: {folder}"}, status_code=400)

    try:
        # Скрываем несохранённые изменения, если они есть
        stash_result = subprocess.run(
            ["git", "stash", "push", "-m", "PortfolioForge auto-stash before pull --rebase"],
            cwd=str(folder),
            capture_output=True,
            text=True,
        )
        stashed = "No local changes to save" not in stash_result.stdout

        # Выполняем pull --rebase
        pull_result = subprocess.run(
            ["git", "pull", "--rebase"],
            cwd=str(folder),
            capture_output=True,
            text=True,
        )
        if pull_result.returncode != 0:
            # Если есть изменения в stash, пытаемся вернуть их
            if stashed:
                subprocess.run(
                    ["git", "stash", "pop"],
                    cwd=str(folder),
                    capture_output=True,
                    text=True,
                )
            return JSONResponse(
                {"error": pull_result.stderr.strip() or "Ошибка pull --rebase"},
                status_code=500,
            )

        # Возвращаем спрятанные изменения, если они были
        if stashed:
            pop_result = subprocess.run(
                ["git", "stash", "pop"],
                cwd=str(folder),
                capture_output=True,
                text=True,
            )
            if pop_result.returncode != 0:
                # stash pop тоже дал конфликт — возвращаем ошибку пользователю с подробностями
                log_info(f"git stash pop конфликт в {folder}: {pop_result.stderr.strip()}")
                return JSONResponse(
                    {
                        "error": "stash_pop_conflict",
                        "message": f"Не удалось вернуть спрятанные изменения после pull --rebase: {pop_result.stderr.strip()}",
                        "output": pop_result.stdout.strip(),
                    },
                    status_code=500,
                )
            log_info(f"git stash pop в {folder}: {pop_result.stdout.strip()}")

        # После successful pull --rebase делаем коммит всех изменений, чтобы пуш прошёл
        commit_result = subprocess.run(
            ["git", "add", "-A"],
            cwd=str(folder),
            capture_output=True,
            text=True,
        )
        log_info(f"git add -A после rebase в {folder}: {commit_result.stdout.strip()} {commit_result.stderr.strip()}")

        commit_result2 = subprocess.run(
            ["git", "commit", "-m", "Merge remote changes via PortfolioForge"],
            cwd=str(folder),
            capture_output=True,
            text=True,
        )
        if commit_result2.returncode != 0 and "nothing to commit" not in commit_result2.stdout.lower():
            log_info(f"git commit после rebase в {folder}: {commit_result2.stderr.strip()}")
        else:
            log_info(f"git commit после rebase в {folder}: {commit_result2.stdout.strip()}")

        log_info(f"git pull --rebase выполнен в {folder}: {pull_result.stdout.strip()}")
        return JSONResponse({"ok": True, "output": pull_result.stdout.strip()})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=500)


async def broadcast_push_conflict(project_name: str, folder_path: str) -> None:
    """Отправляет фронтенду сообщение о конфликте пуша через WebSocket."""
    payload = json.dumps({
        "type": "push_conflict",
        "project_name": project_name,
        "folder_path": folder_path,
    })
    await _broadcast_to_clients(payload)


@app.post("/publish")
async def publish(request: Request) -> JSONResponse:
    """Запускает генерацию README и публикацию на GitHub в фоновом потоке.

    Возвращает управление фронтенду сразу, а сама работа идёт в отдельном
    потоке, чтобы не блокировать event loop uvicorn.
    """
    data: dict[str, Any] = await request.json()
    project_name = (data.get("project_name") or "").strip()
    description = (data.get("description") or "").strip()
    tech_stack = (data.get("tech_stack") or "").strip()
    demo_link = (data.get("demo_link") or "").strip()
    folder_path = (data.get("folder_path") or "").strip()
    update_if_exists = bool(data.get("update_if_exists"))
    private = bool(data.get("private"))
    readme_content_override = data.get("readme_content")
    branch = (data.get("branch") or "main").strip() or "main"

    if not project_name or not folder_path:
        return JSONResponse(
            {"error": "Укажите название проекта и выберите папку"}, status_code=400
        )

    if not REPO_NAME_RE.fullmatch(project_name):
        return JSONResponse(
            {
                "error": "Некорректное название репозитория. Разрешены латинские буквы, цифры, точки, дефисы и подчёркивания."
            },
            status_code=400,
        )

    if not BRANCH_NAME_RE.fullmatch(branch):
        return JSONResponse(
            {
                "error": "Некорректное имя ветки. Разрешены латинские буквы, цифры, точки, дефисы, подчёркивания и слэши."
            },
            status_code=400,
        )

    global publish_cancel_event
    publish_cancel_event = threading.Event()

    def run() -> None:
        try:
            log_info("=== Начало публикации ===")

            def cancelled() -> bool:
                return publish_cancel_event is not None and publish_cancel_event.is_set()

            if cancelled():
                log_info("Публикация отменена пользователем перед запуском.")
                return

            # 1. Генерация или сохранение README.md
            log_info("Генерация README.md...")
            if readme_content_override:
                readme_path = Path(folder_path) / "README.md"
                readme_path.write_text(readme_content_override, encoding="utf-8")
                log_info(f"README.md сохранён (отредактированный): {readme_path}")
            else:
                readme_path = generate_readme(
                    project_name, description, tech_stack, demo_link,
                    Path(folder_path), private
                )
                log_info(f"README.md сохранён: {readme_path}")

            # 2. Создание / апдейт репозитория и пуш кода
            manager = GitHubManager(env_path=ENV_PATH)

            def progress_cb(percent: int, message: str) -> None:
                log_info(message)
                # Отправляем прогресс фронтенду
                import asyncio as _asyncio
                try:
                    _asyncio.run_coroutine_threadsafe(
                        broadcast_progress(percent, message), ws_loop
                    )
                except Exception:
                    pass

            if cancelled():
                log_info("Публикация отменена пользователем перед отправкой на GitHub.")
                return

            manager.create_and_push_repo(
                project_name,
                description,
                folder_path,
                update_if_exists=update_if_exists,
                private=private,
                branch=branch,
                progress_callback=progress_cb,
                cancel_event=publish_cancel_event,
            )

            if cancelled():
                log_info("Публикация отменена пользователем во время отправки на GitHub.")
                return
            global last_published_repo_url
            last_published_repo_url = manager.last_repo_url
            log_info(f"Опубликовано: {manager.last_repo_url}")

            # Сохраняем репозиторий в список, если публикация прошла успешно
            try:
                repos = _load_repos()
                repos = [r for r in repos if r.get("name") != project_name]
                repos.insert(
                    0,
                    {
                        "name": project_name,
                        "full_name": project_name,
                        "description": description,
                        "url": manager.last_repo_url or "",
                        "folder_path": folder_path,
                        "private": private,
                        "updated_at": datetime.datetime.now().isoformat(),
                    },
                )
                _save_repos(repos)
                log_info("Репозиторий добавлен в список сохранённых.")
            except Exception as exc:  # noqa: BLE001
                log_info(f"Не удалось сохранить репозиторий в историю: {exc}")
        except GitPushConflictError as exc:
            log_info(f"Конфликт пуша: {exc}")
            # Отправляем WebSocket-сообщение фронтенду о конфликте
            import asyncio as _asyncio
            try:
                _asyncio.run_coroutine_threadsafe(
                    broadcast_push_conflict(project_name, folder_path), ws_loop
                )
            except Exception:
                pass
        except Exception as exc:  # noqa: BLE001
            log_info(f"Критическая ошибка публикации: {exc}")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return JSONResponse({"status": "started"})


@app.post("/publish/cancel")
async def publish_cancel() -> JSONResponse:
    """Запрашивает отмену текущей публикации (устанавливает флаг отмены)."""
    global publish_cancel_event
    if publish_cancel_event is None:
        return JSONResponse(
            {"ok": False, "message": "Активная публикация не найдена"}, status_code=400
        )
    publish_cancel_event.set()
    log_info("Пользователь запросил отмену публикации.")
    return JSONResponse({"ok": True, "message": "Отмену запрошено."})


@app.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket) -> None:
    """WebSocket-канал для стриминга логов в правую панель UI."""
    await websocket.accept()
    ws_clients.add(websocket)
    # Присылаем буфер последних логов новому клиенту
    for message in list(log_buffer):
        try:
            await websocket.send_text(
                json.dumps({"type": "log", "message": message})
            )
        except Exception:
            break
    try:
        while True:
            await websocket.receive_text()  # держим соединение живым
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(websocket)


def parse_cli_args():
    """Парсит аргументы командной строки для автоматизации."""
    import argparse
    parser = argparse.ArgumentParser(description="PortfolioForge — публикация проектов на GitHub")
    parser.add_argument("--folder", type=str, help="Путь к папке проекта")
    parser.add_argument("--project-name", type=str, help="Название проекта")
    parser.add_argument("--description", type=str, default="", help="Описание проекта")
    parser.add_argument("--tech-stack", type=str, default="", help="Стек технологий (через запятую)")
    parser.add_argument("--demo-link", type=str, default="", help="Ссылка на демо")
    parser.add_argument("--private", action="store_true", help="Приватный репозиторий")
    parser.add_argument("--update-if-exists", action="store_true", help="Обновить существующий репозиторий")
    parser.add_argument("--token", type=str, help="GitHub Personal Access Token")
    parser.add_argument("--no-gui", action="store_true", help="Запуск без GUI (headless режим)")
    parser.add_argument("--host", type=str, default=HOST, help="Хост для сервера")
    parser.add_argument("--port", type=int, default=PORT, help="Порт для сервера")
    return parser.parse_args()


async def publish_headless(args) -> int:
    """Публикация в headless режиме без GUI."""
    import httpx

    # Сохраняем токен если передан
    if args.token:
        manager = GitHubManager(env_path=ENV_PATH)
        ok, msg = manager.validate_token(args.token)
        if not ok:
            log_info(f"Невалидный токен: {msg}")
            return 1
        manager.save_token(args.token)
        log_info("Токен сохранён")

    if not args.folder or not args.project_name:
        log_info("Ошибка: --folder и --project-name обязательны для headless режима")
        return 1

    folder_path = Path(args.folder).resolve()
    if not folder_path.exists():
        log_info(f"Папка не найдена: {folder_path}")
        return 1

    # Проверяем токен
    manager = GitHubManager(env_path=ENV_PATH)
    if not manager.token:
        log_info("GITHUB_TOKEN не задан. Укажите --token или сохраните через GUI")
        return 1

    # Генерируем/сохраняем README
    log_info("Генерация README.md...")
    if args.description or args.tech_stack or args.demo_link:
        readme_path = generate_readme(
            args.project_name, args.description, args.tech_stack, args.demo_link,
            folder_path, args.private
        )
        log_info(f"README.md сохранён: {readme_path}")

    # Публикуем
    def progress_cb(percent: int, message: str) -> None:
        log_info(f"[{percent}%] {message}")

    try:
        manager.create_and_push_repo(
            args.project_name,
            args.description,
            str(folder_path),
            update_if_exists=args.update_if_exists,
            private=args.private,
            progress_callback=progress_cb,
        )
        log_info(f"Опубликовано: {manager.last_repo_url}")
        return 0
    except GitPushConflictError as exc:
        log_info(f"Конфликт пуша: {exc}")
        return 2
    except Exception as exc:
        log_info(f"Ошибка: {exc}")
        return 1


def main() -> None:
    """Запускает uvicorn в фоновом потоке и открывает окно pywebview."""
    import sys
    args = parse_cli_args()

    # Обновляем хост/порт из CLI
    global HOST, PORT
    HOST = args.host
    PORT = args.port

    if args.no_gui:
        # Headless режим
        import asyncio
        exit_code = asyncio.run(publish_headless(args))
        sys.exit(exit_code)

    # GUI режим
    server_thread = threading.Thread(
        target=lambda: uvicorn.run(
            app, host=HOST, port=PORT, log_level="warning"
        ),
        daemon=True,
    )
    server_thread.start()

    webview.create_window(
        APP_TITLE,
        url=f"http://{HOST}:{PORT}/",
        width=1250,
        height=850,
        min_size=(1000, 700),
        resizable=True,
    )
    webview.start()


if __name__ == "__main__":
    main()
