# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT
import os

BASE = os.path.abspath(".")

# Включаем шаблоны и статику в собранное приложение
datas = [
    (os.path.join(BASE, "templates"), "templates"),
    (os.path.join(BASE, "static"), "static"),
    (os.path.join(BASE, ".env.example"), "."),
]

hiddenimports = [
    "fastapi",
    "fastapi.routing",
    "fastapi.templating",
    "fastapi.staticfiles",
    "fastapi.exceptions",
    "fastapi.requests",
    "fastapi.responses",
    "fastapi.websockets",
    "uvicorn",
    "uvicorn.config",
    "uvicorn.server",
    "jinja2",
    "jinja2.ext",
    "starlette",
    "starlette.routing",
    "starlette.templating",
    "starlette.staticfiles",
    "starlette.applications",
    "starlette.middleware",
    "starlette.middleware.base",
    "anyio",
    "pydantic",
    "pydantic.fields",
    "python_multipart",
    "email_validator",
    "websockets",
    "httptools",
    "watchfiles",
    "python_dotenv",
    "github",
    "github.MainClass",
    "github.Repository",
    "github.NamedUser",
    "webview",
]

a = Analysis(
    ["app.py"],
    pathex=[BASE],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="PortfolioForge-v0.3.1-beta",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # без консольного окна
    icon=None,
    version_file=None,
    manifest=None,
)

app = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PortfolioForge-v0.3.1-beta",
)
