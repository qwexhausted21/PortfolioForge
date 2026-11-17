"""Менеджер работы с GitHub API через PyGithub.

Инкапсулирует весь сценарий публикации проекта:
  * проверка и валидация GITHUB_TOKEN;
  * создание публичного репозитория;
  * локальная инициализация Git, коммит и пуш;
  * апдейт существующего репозитория.
"""

from __future__ import annotations

import logging
import os
import subprocess
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
        progress_callback: Callable[[int, str], None] | None = None,
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

        try:
            if not self.token:
                raise ValueError("GITHUB_TOKEN не найден. Укажите токен в настройках.")

            if not self.github:
                raise RuntimeError("Клиент PyGithub не инициализирован")

            folder = Path(folder_path).resolve()
            if not folder.is_dir():
                raise FileNotFoundError(f"Папка не найдена: {folder}")

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

            clone_url = repo.clone_url  # https://github.com/владелец/имя.git

            # --- Локальный Git ---
            # Удаляем старый .git, если есть — иначе токен из прошлых коммитов
            # попадёт в новую историю и GitHub заблокирует пуш через Secret Scanning.
            old_git = folder / ".git"
            if old_git.exists():
                log("Удаление старого локального репозитория Git (.git)...")
                import shutil
                shutil.rmtree(old_git, ignore_errors=True)

            progress(50, "Инициализация локального репозитория Git (git init)...")
            self._run_git(folder, ["init"], log)

            progress(55, "Настройка локальной идентичности Git (user.name / user.email)...")
            self._run_git(
                folder,
                ["config", "user.name", "PortfolioForge"],
                log,
            )
            self._run_git(
                folder,
                ["config", "user.email", "portfolioforge@localhost"],
                log,
            )

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

            log("Добавление всех файлов в индекс (git add -A)...")
            self._run_git(folder, ["add", "-A"], log)

            # Гарантированно исключаем .env из индекса, даже если он был добавлен ранее
            log("Исключение .env из отслеживания Git (защита токена)...")
            self._run_git(
                folder,
                ["rm", "--cached", "--ignore-unmatch", ".env"],
                log,
                check=False,
            )

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

            progress(75, "Переключение на главную ветку main...")
            self._run_git(folder, ["branch", "-M", "main"], log)

            progress(80, "Добавление удалённого репозитория origin...")
            self._run_git(folder, ["remote", "remove", "origin"], log, check=False)
            self._run_git(folder, ["remote", "add", "origin", clone_url], log)

            progress(90, "Отправка кода на GitHub (git push -u origin main)...")
            try:
                self._run_git(folder, ["push", "-u", "origin", "main"], log)
            except subprocess.CalledProcessError:
                # При апдейте существующего репозитория push может быть не fast-forward.
                # Пробуем force push только если включён режим апдейта.
                if update_if_exists:
                    log("Обычный push не прошёл. Пробую force push (режим апдейта)...")
                    self._run_git(folder, ["push", "-u", "origin", "main", "--force"], log)
                else:
                    raise

            progress(100, f"Готово! Проект опубликован: {repo.html_url}")
            log(f"Готово! Проект опубликован: {repo.html_url}")
            self.last_repo_url = repo.html_url
            return logs

        except Exception as exc:  # noqa: BLE001 — любая ошибка сети/API попадает в лог
            log(f"ОШИБКА: {exc}")
            raise

            clone_url = repo.clone_url  # https://github.com/владелец/имя.git

            # --- Локальный Git ---
            # Удаляем старый .git, если есть — иначе токен из прошлых коммитов
            # попадёт в новую историю и GitHub заблокирует пуш через Secret Scanning.
            old_git = folder / ".git"
            if old_git.exists():
                log("Удаление старого локального репозитория Git (.git)...")
                import shutil
                shutil.rmtree(old_git, ignore_errors=True)

            log("Инициализация локального репозитория Git (git init)...")
            self._run_git(folder, ["init"], log)

            log("Настройка локальной идентичности Git (user.name / user.email)...")
            self._run_git(
                folder,
                ["config", "user.name", "PortfolioForge"],
                log,
            )
            self._run_git(
                folder,
                ["config", "user.email", "portfolioforge@localhost"],
                log,
            )

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

            log("Добавление всех файлов в индекс (git add -A)...")
            self._run_git(folder, ["add", "-A"], log)

            # Гарантированно исключаем .env из индекса, даже если он был добавлен ранее
            log("Исключение .env из отслеживания Git (защита токена)...")
            self._run_git(
                folder,
                ["rm", "--cached", "--ignore-unmatch", ".env"],
                log,
                check=False,
            )

            # Проверяем, есть ли что коммитить
            status_result = self._run_git(folder, ["status", "--porcelain"], log, check=False)
            if not status_result.stdout.strip():
                log("Нет изменений для коммита — пропускаю создание коммита.")
            else:
                log("Создание коммита...")
                try:
                    self._run_git(folder, ["commit", "-m", "Initial commit"], log)
                except subprocess.CalledProcessError:
                    # Возможно, коммит уже был — пробуем продолжить пуш
                    log("Коммит не создан (возможно, уже существует). Продолжаю...")

            log("Переключение на главную ветку main...")
            self._run_git(folder, ["branch", "-M", "main"], log)

            log("Добавление удалённого репозитория origin...")
            self._run_git(folder, ["remote", "remove", "origin"], log, check=False)
            self._run_git(folder, ["remote", "add", "origin", clone_url], log)

            log("Отправка кода на GitHub (git push -u origin main)...")
            try:
                self._run_git(folder, ["push", "-u", "origin", "main"], log)
            except subprocess.CalledProcessError:
                # При апдейте существующего репозитория push может быть не fast-forward.
                # Пробуем force push только если включён режим апдейта.
                if update_if_exists:
                    log("Обычный push не прошёл. Пробую force push (режим апдейта)...")
                    self._run_git(folder, ["push", "-u", "origin", "main", "--force"], log)
                else:
                    raise

            log(f"Готово! Проект опубликован: {repo.html_url}")
            self.last_repo_url = repo.html_url
            return logs

        except Exception as exc:  # noqa: BLE001 — любая ошибка сети/API попадает в лог
            log(f"ОШИБКА: {exc}")
            raise

    @staticmethod
    def _run_git(
        folder: Path,
        args: List[str],
        log,
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """Выполняет git-команду в папке проекта и логирует её вывод."""
        cmd = ["git"] + args
        log(f"$ {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                cwd=str(folder),
                capture_output=True,
                text=True,
                check=check,
            )
            if result.stdout.strip():
                log(result.stdout.strip())
            if result.stderr.strip():
                log(result.stderr.strip())
            return result
        except subprocess.CalledProcessError as exc:
            if exc.stdout:
                log(exc.stdout.strip())
            if exc.stderr:
                log(exc.stderr.strip())
            raise
