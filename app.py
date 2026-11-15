"""Точка входа PortfolioForge: локальный FastAPI-бэкенд + рабочее окно pywebview.

Модуль поднимает uvicorn в фоновом потоке, отдаёт фронтенд и статику через FastAPI,
проксирует логи в браузер по WebSocket и запускает публикацию при нажатии кнопки.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import deque
from pathlib import Path
from typing import Any

import uvicorn
import webview
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from github_manager import GitHubManager
from readme_generator import generate_readme

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)

APP_TITLE = "PortfolioForge"
HOST = "127.0.0.1"
PORT = 8080

app = FastAPI(title=APP_TITLE)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

logger = logging.getLogger("portfolioforge")
logger.setLevel(logging.INFO)

# --- Брокер логов: рассылает записи фронтенду через WebSocket -----------------
ws_loop: asyncio.AbstractEventLoop | None = None
ws_clients: set[WebSocket] = set()
log_buffer: deque[str] = deque(maxlen=200)


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


formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")

ws_handler = WebSocketLogHandler()
ws_handler.setFormatter(formatter)
logger.addHandler(ws_handler)

# Дублируем логи в консоль сервера
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


def log_info(message: str) -> None:
    logger.info(message)


# --- Хранилище сохранённых репозиториев ---------------------------------------
REPOS_FILE = BASE_DIR / "saved_repos.json"


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
    """Открывает системный диалог выбора папки через tkinter.filedialog."""
    import tkinter
    import tkinter.filedialog

    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    folder = tkinter.filedialog.askdirectory(title="Выберите папку с проектом")
    root.destroy()
    if folder:
        log_info(f"Выбрана папка: {folder}")
        return JSONResponse({"path": folder})
    return JSONResponse({"path": ""})


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

    if not project_name or not folder_path:
        return JSONResponse(
            {"error": "Укажите название проекта и выберите папку"}, status_code=400
        )

    def run() -> None:
        try:
            log_info("=== Начало публикации ===")

            # 1. Генерация README.md
            log_info("Генерация README.md...")
            readme_path = generate_readme(
                project_name, description, tech_stack, demo_link, Path(folder_path)
            )
            log_info(f"README.md сохранён: {readme_path}")

            # 2. Создание / апдейт репозитория и пуш кода
            manager = GitHubManager(env_path=ENV_PATH)
            manager.create_and_push_repo(
                project_name, description, folder_path, update_if_exists=update_if_exists
            )
            # Сохраняем репозиторий в список, если публикация прошла успешно
            try:
                repos = _load_repos()
                repos = [r for r in repos if r.get("name") != project_name]
                repos.insert(
                    0,
                    {
                        "name": project_name,
                        "description": description,
                        "folder_path": folder_path,
                        "updated_at": __import__("datetime").datetime.now().isoformat(),
                    },
                )
                _save_repos(repos)
                log_info("Репозиторий добавлен в список сохранённых.")
            except Exception as exc:  # noqa: BLE001
                log_info(f"Не удалось сохранить репозиторий в историю: {exc}")
        except Exception as exc:  # noqa: BLE001
            log_info(f"Критическая ошибка: {exc}")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return JSONResponse({"status": "started"})


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


def main() -> None:
    """Запускает uvicorn в фоновом потоке и открывает окно pywebview."""
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
