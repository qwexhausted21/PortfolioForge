# PortfolioForge

[![Русский](https://img.shields.io/badge/Язык-Русский-blue)](README.md#russian)
[![English](https://img.shields.io/badge/Language-English-blue)](README.md#english)

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688?logo=fastapi)
![pywebview](https://img.shields.io/badge/pywebview-Desktop-2C2C2C?logo=python)

Desktop-инструмент для автоматизации публикации проектов на GitHub.

---

## 🇷🇺 Русский

<a name="russian"></a>

### Описание

PortfolioForge — это десктопное приложение на Python, которое помогает автоматически публиковать проекты на GitHub. Оно сочетает локальный бэкенд на FastAPI, десктопное окно через pywebview и простой фронтенд на HTML/CSS/JS.

### Основные возможности

- **Генерация README.md** — создаёт красивый файл с бейджами Shields.io, описанием, стеком технологий и инструкцией по установке
- **Публикация на GitHub** — создаёт публичный или приватный репозиторий, инициализирует Git, делает коммит и пушит код
- **Выбор папки** — системный диалог для указания папки с проектом
- **Редактор README.md** — можно отредактировать сгенерированный файл перед публикацией
- **Автозагрузка README** — если в папке уже есть README.md, приложение подтянет его автоматически
- **Библиотека репозиториев** — загрузка списка репозиториев из вашего аккаунта GitHub или ручное добавление по ссылке
- **Выезжающий сайдбар библиотеки** — не занимает место на основной форме
- **Кнопка «Перейти к репозиторию»** — открывает опубликованный репозиторий в браузере
- **Прогресс-бар** — показывает этапы публикации в реальном времени
- **Консоль логов** — скрыта по умолчанию, включается одной кнопкой
- **Токен GitHub** — вводится и сохраняется в .env, не попадает в коммиты

### Стек технологий

- Python 3.11+
- FastAPI — локальный бэкенд
- PyGithub — работа с GitHub API
- pywebview — десктопное окно
- python-dotenv — хранение токена
- HTML5, CSS, Vanilla JS — фронтенд
- TailwindCSS (CDN) — стили

### Установка

```bash
# Клонируйте репозиторий
git clone https://github.com/qwexhausted21/PortfolioForge.git
cd PortfolioForge

# Создайте виртуальное окружение
python -m venv venv

# Активируйте его
# Windows:
venv\Scripts\activate

# macOS / Linux:
source venv/bin/activate

# Установите зависимости
pip install -r requirements.txt
```

### Быстрый старт

```bash
# Windows
run.bat

# macOS / Linux
./run.sh
```

После запуска откроется окно приложения. Вставьте GitHub Personal Access Token (права `repo`), заполните форму, выберите папку и нажмите «Опубликовать на GitHub».

### Лицензия

MIT

---

## 🇬🇧 English

<a name="english"></a>

### Description

PortfolioForge is a desktop application written in Python that helps automatically publish projects to GitHub. It combines a FastAPI backend, a pywebview desktop window, and a simple HTML/CSS/JS frontend.

### Key Features

- **README.md generation** — creates a beautiful file with Shields.io badges, description, tech stack, and installation instructions
- **Publish to GitHub** — creates a public or private repository, initializes Git, commits, and pushes code
- **Folder selection** — system dialog to choose the project folder
- **README.md editor** — edit the generated file before publishing
- **Auto-load README** — if README.md already exists in the folder, it's loaded automatically
- **Repository library** — load repositories from your GitHub account or add manually by link
- **Slide-out library sidebar** — doesn't take space on the main form
- **Go to repository button** — opens the published repository in the browser
- **Progress bar** — shows publishing stages in real time
- **Logs console** — hidden by default, toggle with one button
- **GitHub token** — entered and saved in .env, never committed

### Tech Stack

- Python 3.11+
- FastAPI — local backend
- PyGithub — GitHub API
- pywebview — desktop window
- python-dotenv — token storage
- HTML5, CSS, Vanilla JS — frontend
- TailwindCSS (CDN) — styling

### Installation

```bash
# Clone the repository
git clone https://github.com/qwexhausted21/PortfolioForge.git
cd PortfolioForge

# Create virtual environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate

# macOS / Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Quick Start

```bash
# Windows
run.bat

# macOS / Linux
./run.sh
```

After launch, the app window will open. Insert your GitHub Personal Access Token (repo scope), fill the form, select a folder, and click «Publish to GitHub».

### License

MIT

---

*README generated with PortfolioForge*
