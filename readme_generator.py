"""Генератор красивого README.md с бейджами Shields.io и инструкцией по установке.

Сформированный файл сохраняется в выбранную пользователем папку проекта.
"""

from __future__ import annotations

from pathlib import Path


def generate_readme_content(
    project_name: str,
    description: str,
    tech_stack: str,
    demo_link: str,
    private: bool = False,
) -> str:
    """Генерирует содержимое README.md на основе введённых данных.

    Args:
        project_name: Название проекта — становится заголовком README.
        description: Краткое описание проекта.
        tech_stack: Стек технологий (строка, разделение запятыми).
        demo_link: Ссылка на демо (может быть пустой).
        private: Приватный репозиторий или нет (для бейджа).

    Returns:
        Содержимое README.md в виде строки.
    """
    visibility = "Приватный" if private else "Публичный"
    technologies = [t.strip() for t in tech_stack.replace(";", ",").split(",") if t.strip()]

    # Бейджи Shields.io
    badges = (
        "![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)\n"
        "![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688?logo=fastapi)\n"
        "![pywebview](https://img.shields.io/badge/pywebview-Desktop-2C2C2C?logo=python)\n"
    )
    visibility_badge = (
        "![Private](https://img.shields.io/badge/Visibility-Private-red)"
        if private
        else "![Public](https://img.shields.io/badge/Visibility-Public-green)"
    )
    badges += visibility_badge + "\n"
    for tech in technologies:
        badge_url = f"https://img.shields.io/badge/{tech}-used-green"
        badges += f"![{tech}]({badge_url})\n"

    demo_section = ""
    if demo_link:
        demo_section = f"""## 🚀 Демо

Посмотреть работу проекта можно по ссылке: [{demo_link}]({demo_link})

"""

    quote_line = f"> {description}" if description else ""
    techs_line = ", ".join(technologies) if technologies else "Не указан"

    sections: list[str | None] = [
        f"# {project_name}",
        "",
        badges,
        "",
        quote_line,
        "",
        "## 📖 Описание",
        "",
        description or "Описание не добавлено.",
        "",
        demo_section,
        "## 🛠 Стек технологий",
        "",
        techs_line,
        "",
        "## 🔒 Видимость",
        "",
        visibility,
        "",
        "## 📦 Установка",
        "",
        "```bash",
        "# Клонируйте репозиторий",
        f"git clone https://github.com/USERNAME/{project_name}.git",
        f"cd {project_name}",
        "",
        "# Создайте виртуальное окружение",
        "python -m venv venv",
        "",
        "# Активируйте окружение",
        "# Windows:",
        "venv\\Scripts\\activate",
        "",
        "# macOS / Linux:",
        "source venv/bin/activate",
        "",
        "# Установите зависимости",
        "pip install -r requirements.txt",
        "```",
        "",
        "## 🚀 Быстрый старт",
        "",
        "```bash",
        "python app.py",
        "```",
        "",
        "## 🤝 Вклад",
        "",
        "Pull request'ы приветствуются! Перед большими изменениями, пожалуйста,",
        "откройте issue для обсуждения.",
        "",
        "## 📄 Лицензия",
        "",
        "Этот проект распространяется под лицензией MIT.",
        "",
        "---",
        "*README сгенерирован автоматически с помощью PortfolioForge*",
    ]

    return "\n".join(line for line in sections if line is not None)


def generate_readme(
    project_name: str,
    description: str,
    tech_stack: str,
    demo_link: str,
    output_path: Path,
    private: bool = False,
) -> Path:
    """Создаёт файл README.md на основе введённых пользователем данных.

    Args:
        project_name: Название проекта — становится заголовком README.
        description: Краткое описание проекта.
        tech_stack: Стек технологий (строка, разделение запятыми).
        demo_link: Ссылка на демо (может быть пустой).
        output_path: Папка, в которую сохранить README.md.
        private: Приватный репозиторий или нет.

    Returns:
        Путь к созданному файлу README.md.
    """
    content = generate_readme_content(
        project_name, description, tech_stack, demo_link, private
    )
    readme_path = output_path / "README.md"
    readme_path.write_text(content, encoding="utf-8")
    return readme_path


def load_existing_readme(folder_path: str) -> str | None:
    """Загружает существующий README.md из папки проекта, если он есть.

    Args:
        folder_path: Путь к папке с проектом.

    Returns:
        Содержимое README.md в виде строки, или None, если файла нет.
    """
    readme_path = Path(folder_path) / "README.md"
    if readme_path.is_file():
        return readme_path.read_text(encoding="utf-8")
    return None
