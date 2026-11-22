"""Менеджер работы с GitHub API через PyGithub.

Инкапсулирует весь сценарий публикации проекта:
  * проверка и валидация GITHUB_TOKEN;
  * создание публичного репозитория;
  * локальная инициализация Git, коммит и пуш;
  * апдейт существующего репозитория.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

from dotenv import load_dotenv, set_key
from github import (
    BadCredentialsException,
    Github,
    GithubException,
    RateLimitExceededException,
)

logger = logging.getLogger("portfolioforge.github")


class GitPushConflictError(Exception):
    """Исключение при конфликте пуша — на удалённом репозитории есть изменения,
    которых нет локально. Требует решения пользователем: слить или перезаписать."""
    pass


# Таймаут на любую git-команду (сек). 5 минут достаточно для инициализации,
# коммита и большинства пушей; длительный пуш по медленному каналу прервётся.
GIT_TIMEOUT_SECONDS = 300


def _safe_github_call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Выполняет вызов GitHub API, безопасно обрабатывая не-ASCII символы.

    GitHub API ожидает latin-1 совместимые строки; при передаче кириллицы
    PyGithub может упасть с UnicodeEncodeError. В этом случае повторяем вызов
    с очищенным описанием.
    """
    try:
        return fn(*args, **kwargs)
    except UnicodeEncodeError:
        # Убираем не-ASCII символы из аргументов и пробуем ещё раз
        cleaned_kwargs: dict[str, Any] = {}
        for key, value in kwargs.items():
            if isinstance(value, str):
                cleaned_kwargs[key] = value.encode("ascii", errors="ignore").decode("ascii")
            else:
                cleaned_kwargs[key] = value
        cleaned_args = [
            a.encode("ascii", errors="ignore").decode("ascii") if isinstance(a, str) else a
            for a in args
        ]
        return fn(*cleaned_args, **cleaned_kwargs)



class GitHubManager:
    """Создаёт репозиторий на GitHub и отправляет в него проект из локальной папки."""

    def __init__(self, env_path: str | Path = ".env") -> None:
        """Загружает токен из .env и инициализирует клиент PyGithub.

        Args:
            env_path: Путь к файлу .env относительно рабочей директории приложения.
        """
        self.env_path = Path(env_path).resolve()
        load_dotenv(self.env_path)
        self.token: str | None = os.getenv("GITHUB_TOKEN")
        self.github: Github | None = Github(self.token) if self.token else None
        self.last_repo_url: str | None = None
        self.last_repo_full_name: str | None = None

    # ------------------------------------------------------------------ #
    # Публичные методы
    # ------------------------------------------------------------------ #

    def validate_token(self, token: Optional[str] = None) -> Tuple[bool, str]:
        """Проверяет работоспособность GitHub-токена.

        Args:
            token: Токен для проверки. Если не передан — используется из .env.

        Returns:
            (успех, сообщение). При успехе message содержит логин пользователя.
        """
        token = token or self.token
        if not token:
            return False, "Токен не указан."

        github = Github(token)
        try:
            user = github.get_user()
            user.login  # forces реальный запрос к API — валидирует токен
            return True, f"Токен валиден. Пользователь: {user.login}"
        except BadCredentialsException:
            return False, "Неверный токен. Проверьте, что он скопирован верно и не просрочен."
        except RateLimitExceededException as exc:
            return False, f"Лимит запросов GitHub API исчерпан: {exc}"
        except GithubException as exc:
            return False, f"Ошибка GitHub API ({exc.status}): {exc}"

    def save_token(self, token: str) -> None:
        """Сохраняет токен в файл .env (создаёт файл, если нет)."""
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        set_key(str(self.env_path), "GITHUB_TOKEN", token, quote_mode="never")
        # Обновляем текущее состояние экземпляра
        self.token = token
        self.github = Github(token)

    def create_and_push_repo(
        self,
        repo_name: str,
        description: str,
        folder_path: str,
        *,
        update_if_exists: bool = False,
        private: bool = False,
        branch: str = "main",
        progress_callback: Callable[[int, str], None] | None = None,
        cancel_event: Event | None = None,
        force_push: bool = False,
    ) -> List[str]:
        """Создаёт репозиторий на GitHub и пушит в него код из папки.

        Если репозиторий с таким именем уже существует:
        * при ``update_if_exists=True`` — используется существующий репозиторий
          и код пушится в него (апдейт);
        * при ``update_if_exists=False`` — возвращается ошибка.

        Args:
            repo_name: Название репозитория.
            description: Описание репозитория.
            folder_path: Путь к папке с проектом.
            update_if_exists: Разрешить апдейт существующего репозитория.
            private: Приватный репозиторий (True) или публичный (False).
            progress_callback: Функция обратного вызова для прогресса (процент, сообщение).
            cancel_event: Событие отмены — если установлено, публикация прерывается.

        Returns:
            Список строк-лога с пошаговым описанием действий и ошибок.
        """
        logs: List[str] = []

        def log(message: str) -> None:
            logger.info(message)
            logs.append(message)

        def progress(percent: int, message: str) -> None:
            log(message)
            if progress_callback:
                progress_callback(percent, message)

        def is_cancelled() -> bool:
            return cancel_event is not None and cancel_event.is_set()

        def check_cancelled() -> None:
            if is_cancelled():
                log("Публикация отменена пользователем.")
                raise _PublishCancelledError()

        class _PublishCancelledError(Exception):
            """Внутренний маркер отмены публикации пользователем."""
            pass

        try:
            if not self.token:
                raise ValueError("GITHUB_TOKEN не найден. Укажите токен в настройках.")

            if not self.github:
                raise RuntimeError("Клиент PyGithub не инициализирован")

            folder = Path(folder_path).resolve()
            if not folder.is_dir():
                raise FileNotFoundError(f"Папка не найдена: {folder}")

            # На Windows добавляем папку в git safe.directory, иначе Git блокирует
            # операции с репозиторием, созданным другим пользователем
            if sys.platform == "win32":
                self._run_git(
                    folder,
                    ["config", "--global", "--add", "safe.directory", str(folder)],
                    log,
                    check=False,
                )

            progress(10, "Проверка токена GitHub...")
            try:
                user = self.github.get_user()
                user.login  # валидация через реальный запрос к API
            except BadCredentialsException:
                raise ValueError(
                    "Неверный GITHUB_TOKEN. Проверьте, что токен скопирован верно и не просрочен."
                )
            except RateLimitExceededException as exc:
                raise RuntimeError(f"Лимит запросов GitHub API исчерпан: {exc}")
            progress(10, f"Токен валиден. Пользователь: {user.login}")
            check_cancelled()

            # Санитизируем имя репозитория для GitHub API (только ASCII,
            # иначе PyGithub падает с UnicodeEncodeError на латине-1)
            safe_repo_name = repo_name.encode("ascii", errors="ignore").decode("ascii") or repo_name

            # Проверяем, не существует ли репозиторий уже
            repo = None
            try:
                repo = _safe_github_call(user.get_repo, safe_repo_name)
                log(f"Репозиторий '{repo.full_name}' уже найден.")
            except GithubException as exc:
                if exc.status != 404:
                    raise
                repo = None

            if repo is None:
                if not update_if_exists:
                    log(f"Создание репозитория '{repo_name}'...")
                else:
                    log(f"Репозитория '{repo_name}' не найдено. Создаю новый...")
                if description:
                    safe_description = description.encode("ascii", errors="ignore").decode("ascii")
                else:
                    safe_description = ""
                repo = _safe_github_call(
                    user.create_repo,
                    name=safe_repo_name,
                    description=safe_description,
                    private=private,
                    auto_init=False,
                )
                log(f"Репозиторий создан: {repo.html_url}")
                progress(40, f"Репозиторий создан: {repo.html_url}")
            else:
                log(f"Использую существующий репозиторий: {repo.html_url}")
                # Обновим описание и可见ность, если передано
                if description:
                    try:
                        safe_description = description.encode("ascii", errors="ignore").decode("ascii")
                        _safe_github_call(repo.edit, description=safe_description)
                        log("Описание репозитория обновлено.")
                    except GithubException as exc:
                        log(f"Не удалось обновить описание: {exc}")
                try:
                    _safe_github_call(repo.edit, private=private)
                    log(f"Видимость репозитория обновлена: {'приватный' if private else 'публичный'}")
                except GithubException as exc:
                    log(f"Не удалось обновить видимость: {exc}")
                progress(40, f"Используется существующий репозиторий: {repo.html_url}")

            check_cancelled()

            clone_url = repo.clone_url  # https://github.com/владелец/имя.git

            # --- Локальный Git ---
            # Не удаляем существующий .git, чтобы не zerstörить локальную историю.
            # git init в существующем репозитории безопасен и идемпотентен.
            old_git = folder / ".git"
            if old_git.exists():
                log("Локальный репозиторий Git (.git) уже существует — используем его.")

            progress(50, "Инициализация локального репозитория Git (git init)...")
            self._run_git(folder, ["init"], log)
            check_cancelled()

            progress(55, "Настройка локальной идентичности Git (user.name / user.email)...")
            name_result = self._run_git(
                folder,
                ["config", "user.name", "PortfolioForge"],
                log,
                check=False,
            )
            email_result = self._run_git(
                folder,
                ["config", "user.email", "portfolioforge@localhost"],
                log,
                check=False,
            )
            if name_result.returncode != 0 or email_result.returncode != 0:
                log("Предупреждение: не удалось настроить локальную идентичность Git. Продолжаю без неё.")

            log("Создание .gitignore (исключаем .env, venv, кэш)...")
            gitignore_content = (
                "# Environment variables (содержит GITHUB_TOKEN — не коммитить)\n"
                ".env\n"
                "# Виртуальное окружение\n"
                "venv/\n"
                ".venv/\n"
                "# Python кэш\n"
                "__pycache__/\n"
                "*.py[cod]\n"
                "$py.cache/\n"
                "# OS\n"
                ".DS_Store\n"
                "Thumbs.db\n"
            )
            (folder / ".gitignore").write_text(gitignore_content, encoding="utf-8")

            # Гарантированно исключаем .env из отслеживания Git ДО добавления файлов (защита токена)
            log("Исключение .env из отслеживания Git (защита токена)...")
            self._run_git(
                folder,
                ["rm", "--cached", "--ignore-unmatch", ".env"],
                log,
                check=False,
            )

            check_cancelled()

            log("Добавление всех файлов в индекс (git add -A)...")
            self._run_git(folder, ["add", "-A"], log)

            # Проверяем, есть ли что коммитить
            status_result = self._run_git(folder, ["status", "--porcelain"], log, check=False)
            if not status_result.stdout.strip():
                log("Нет изменений для коммита — пропускаю создание коммита.")
            else:
                progress(65, "Создание коммита...")
                try:
                    self._run_git(folder, ["commit", "-m", "Initial commit"], log)
                except subprocess.CalledProcessError:
                    # Возможно, коммит уже был — пробуем продолжить пуш
                    log("Коммит не создан (возможно, уже существует). Продолжаю...")

            progress(75, f"Переключение на ветку {branch}...")
            self._run_git(folder, ["branch", "-M", branch], log)

            progress(80, "Добавление удалённого репозитория origin...")
            self._run_git(folder, ["remote", "remove", "origin"], log, check=False)
            self._run_git(folder, ["remote", "add", "origin", clone_url], log)

            check_cancelled()

            progress(90, f"Отправка кода на GitHub (git push -u origin {branch})...")
            try:
                self._run_git(folder, ["push", "-u", "origin", branch], log)
            except subprocess.CalledProcessError as exc:
                # При апдейте существующего репозитория push может быть не fast-forward.
                # Проверяем stderr на наличие признаков конфликта (rejected / non-fast-forward).
                stderr_output = (exc.stderr or "").lower()
                is_conflict = "rejected" in stderr_output or "non-fast-forward" in stderr_output

                if is_conflict:
                    if force_push:
                        log("Конфликт пуша — выполняю force push (перезапись)...")
                        self._run_git(
                            folder,
                            ["push", "-u", "origin", branch, "--force"],
                            log,
                        )
                    else:
                        log("ОШИБКА: Конфликт пуша — на GitHub есть новые изменения.")
                        raise GitPushConflictError(
                            "На GitHub есть изменения, которых нет локально. "
                            "Нужно сначала слить их или выполнить force push."
                        )

                if update_if_exists and not force_push:
                    log("Обычный push не прошёл. Пробую force push (режим апдейта)...")
                    self._run_git(
                        folder,
                        ["push", "-u", "origin", branch, "--force"],
                        log,
                    )
                elif not force_push:
                    raise

            progress(100, f"Готово! Проект опубликован: {repo.html_url}")
            log(f"Готово! Проект опубликован: {repo.html_url}")
            self.last_repo_url = repo.html_url
            self.last_repo_full_name = repo.full_name
            return logs

        except _PublishCancelledError:
            log("Публикация отменена пользователем.")
            return logs

        except Exception as exc:  # noqa: BLE001 — любая ошибка сети/API попадает в лог
            log(f"ОШИБКА: {exc}")
            raise

    def delete_repo(self, full_name: str) -> Tuple[bool, str]:
        """Удаляет репозиторий с GitHub.

        Args:
            full_name: Полное имя репозитория в формате owner/repo.

        Returns:
            (успех, сообщение).
        """
        if not self.github:
            return False, "Клиент PyGithub не инициализирован"

        try:
            repo = _safe_github_call(self.github.get_repo, full_name)
            repo.delete()
            log(f"Репозиторий '{full_name}' удалён с GitHub.")
            return True, f"Репозиторий '{full_name}' удалён с GitHub."
        except GithubException as exc:
            log(f"Ошибка удаления репозитория '{full_name}': {exc}")
            return False, f"Ошибка GitHub API ({exc.status}): {exc}"

    def create_release(
        self,
        tag: str,
        description: str,
        release_url: str | None = None,
    ) -> Tuple[bool, str]:
        """Создаёт тег и релиз на GitHub.

        Args:
            tag: Имя тега (например, v0.1.0).
            description: Описание релиза.
            release_url: URL репозитория (для логирования).

        Returns:
            (успех, сообщение).
        """
        if not self.github:
            return False, "Клиент PyGithub не инициализирован"
        if not self.last_repo_full_name:
            return False, "Репозиторий не опубликован в этой сессии"

        try:
            repo = _safe_github_call(self.github.get_repo, self.last_repo_full_name)
            release_name = f"Release {tag}"
            _safe_github_call(
                repo.create_git_tag_and_release,
                tag,
                tag_message=f"Version {tag}",
                release_name=release_name,
                release_message=description or f"Выпуск {tag}",
            )
            logger.info(f"Тег и релиз '{tag}' созданы в {self.last_repo_full_name}.")
            return True, f"Тег '{tag}' и релиз созданы."
        except GithubException as exc:
            logger.info(f"Ошибка создания тега/релиза '{tag}': {exc}")
            return False, f"Ошибка GitHub API ({exc.status}): {exc}"

    def _resolve_full_name(self, name: str) -> str:
        """Разрешает короткое имя репозитория в owner/repo.

        Если в имени уже есть слэш, возвращает как есть. Иначе получает логин
        аутентифицированного пользователя и формирует login/name.
        """
        if "/" in name:
            return name
        if not self.github:
            return name
        try:
            user = self.github.get_user()
            user.login  # forces API call
            return f"{user.login}/{name}"
        except GithubException:
            return name

    def get_tags(self, full_name: str) -> Tuple[bool, list[dict[str, str]] | str]:
        """Получает список тегов репозитория.

        Args:
            full_name: Полное имя репозитория (owner/repo) или короткое имя.

        Returns:
            (успех, список тегов или сообщение об ошибке).
        """
        if not self.github:
            return False, "Клиент PyGithub не инициализирован"

        full_name = self._resolve_full_name(full_name)
        try:
            repo = _safe_github_call(self.github.get_repo, full_name)
            tags = []
            for tag in repo.get_tags():
                tags.append({
                    "name": tag.name,
                    "sha": tag.commit.sha if tag.commit else "",
                })
            logger.info(f"Получено {len(tags)} тегов для {full_name}.")
            return True, tags
        except GithubException as exc:
            logger.info(f"Ошибка получения тегов для {full_name}: {exc}")
            return False, f"Ошибка GitHub API ({exc.status}): {exc}"

    def get_release(self, full_name: str, tag: str) -> Tuple[bool, dict[str, str] | str]:
        """Получает информацию о релизе по тегу.

        Args:
            full_name: Полное имя репозитория (owner/repo) или короткое имя.
            tag: Имя тега релиза.

        Returns:
            (успех, данные релиза или сообщение об ошибке).
        """
        if not self.github:
            return False, "Клиент PyGithub не инициализирован"

        full_name = self._resolve_full_name(full_name)
        try:
            repo = _safe_github_call(self.github.get_repo, full_name)
            release = _safe_github_call(repo.get_release, tag)
            return True, {
                "tag_name": release.tag_name,
                "name": release.title or release.tag_name,
                "body": release.body or "",
                "html_url": release.html_url,
                "published_at": str(release.published_at) if release.published_at else "",
                "assets": [
                    {"name": a.name, "url": a.browser_download_url, "size": a.size}
                    for a in release.get_assets()
                ],
            }
        except GithubException as exc:
            logger.info(f"Ошибка получения релиза {tag} для {full_name}: {exc}")
            return False, f"Ошибка GitHub API ({exc.status}): {exc}"

    def update_release_body(
        self,
        full_name: str,
        tag: str,
        body: str,
    ) -> Tuple[bool, str]:
        """Обновляет описание (ChangeLog) существующего релиза.

        Args:
            full_name: Полное имя репозитория (owner/repo) или короткое имя.
            tag: Имя тега релиза.
            body: Новый текст описания в формате Markdown.

        Returns:
            (успех, сообщение).
        """
        if not self.github:
            return False, "Клиент PyGithub не инициализирован"

        full_name = self._resolve_full_name(full_name)
        try:
            repo = _safe_github_call(self.github.get_repo, full_name)
            release = _safe_github_call(repo.get_release, tag)
            _safe_github_call(release.edit, body=body)
            logger.info(f"Описание релиза '{tag}' обновлено в {full_name}.")
            return True, f"ChangeLog релиза '{tag}' обновлён."
        except GithubException as exc:
            logger.info(f"Ошибка обновления описания релиза '{tag}': {exc}")
            return False, f"Ошибка GitHub API ({exc.status}): {exc}"

    def upload_release_asset(
        self,
        full_name: str,
        tag: str,
        file_path: str,
        asset_name: str | None = None,
    ) -> Tuple[bool, str]:
        """Загружает файл (asset) на существующий релиз.

        Args:
            full_name: Полное имя репозитория (owner/repo) или короткое имя.
            tag: Имя тега релиза.
            file_path: Локальный путь к файлу.
            asset_name: Имя для отображения на GitHub (по умолчанию имя файла).

        Returns:
            (успех, сообщение).
        """
        if not self.github:
            return False, "Клиент PyGithub не инициализирован"

        full_name = self._resolve_full_name(full_name)
        path = Path(file_path)
        if not path.is_file():
            return False, f"Файл не найден: {path}"

        try:
            repo = _safe_github_call(self.github.get_repo, full_name)
            release = _safe_github_call(repo.get_release, tag)
            name = asset_name or path.name
            import mimetypes
            content_type, _ = mimetypes.guess_type(str(path))
            content_type = content_type or "application/octet-stream"
            _safe_github_call(
                release.upload_asset,
                str(path),
                content_type=content_type,
                name=name,
            )
            logger.info(f"Файл '{name}' загружен на релиз '{tag}' в {full_name}.")
            return True, f"Файл '{name}' загружен на релиз '{tag}'."
        except GithubException as exc:
            logger.info(f"Ошибка загрузки файла на релиз '{tag}': {exc}")
            return False, f"Ошибка GitHub API ({exc.status}): {exc}"

    @staticmethod
    def _run_git(
        folder: Path,
        args: List[str],
        log,
        *,
        check: bool = True,
        timeout: float = GIT_TIMEOUT_SECONDS,
    ) -> subprocess.CompletedProcess:
        """Выполняет git-команду в папке проекта и логирует её вывод.

        При превышении таймаута команда прерывается и логируется как ошибка,
        чтобы приложение не висело бесконечно (например, на git push без сети).
        На Windows скрывает всплывающее консольное окно git.
        """
        cmd = ["git"] + args
        log(f"$ {' '.join(cmd)}")
        # На Windows скрываем консольное окно git, иначе оно мигает при каждой команде.
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            result = subprocess.run(
                cmd,
                cwd=str(folder),
                capture_output=True,
                text=True,
                check=check,
                timeout=timeout,
                creationflags=creationflags,
            )
            if result.stdout.strip():
                log(result.stdout.strip())
            if result.stderr.strip():
                log(result.stderr.strip())
            return result
        except subprocess.TimeoutExpired as exc:
            log(f"Таймаут git-команды ({timeout}с): {' '.join(cmd)}")
            if exc.stdout:
                log(exc.stdout.strip())
            if exc.stderr:
                log(exc.stderr.strip())
            raise
        except subprocess.CalledProcessError as exc:
            if exc.stdout:
                log(exc.stdout.strip())
            if exc.stderr:
                log(exc.stderr.strip())
            raise
