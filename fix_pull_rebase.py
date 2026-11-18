with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''@app.post("/git/pull-rebase")
async def git_pull_rebase(request: Request) -> JSONResponse:
    """Выполняет git fetch + git merge origin/main в указанной папке.

    Перед слиянием делает git stash push -u (включая неотслеживаемые файлы),
    а после слияния — git stash pop, чтобы вернуть изменения обратно.
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
        # Скрываем ВСЕ изменения, включая неотслеживаемые файлы (-u)
        stash_result = subprocess.run(
            ["git", "stash", "push", "-u", "-m", "PortfolioForge auto-stash before merge"],
            cwd=str(folder),
            capture_output=True,
            text=True,
        )
        stashed = "No local changes to save" not in stash_result.stdout
        log_info(f"git stash push -u в {folder}: {stash_result.stdout.strip()}")

        # Скачиваем изменения с удалённого репозитория
        fetch_result = subprocess.run(
            ["git", "fetch", "origin"],
            cwd=str(folder),
            capture_output=True,
            text=True,
        )
        log_info(f"git fetch origin в {folder}: {fetch_result.stdout.strip()} {fetch_result.stderr.strip()}")

        # Сливаем удалённые изменения с локальными
        merge_result = subprocess.run(
            ["git", "merge", "origin/main"],
            cwd=str(folder),
            capture_output=True,
            text=True,
        )
        if merge_result.returncode != 0:
            # Если конфликт слияния — пытаемся вернуть stash
            if stashed:
                pop_result = subprocess.run(
                    ["git", "stash", "pop"],
                    cwd=str(folder),
                    capture_output=True,
                    text=True,
                )
                log_info(f"git stash pop после ошибки merge в {folder}: {pop_result.stdout.strip()} {pop_result.stderr.strip()}")
            return JSONResponse(
                {"error": merge_result.stderr.strip() or "Ошибка git merge origin/main"},
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
                # stash pop тоже дал конфликт — возвращаем ошибку пользователю
                log_info(f"git stash pop конфликт в {folder}: {pop_result.stderr.strip()}")
                return JSONResponse(
                    {
                        "error": "stash_pop_conflict",
                        "message": f"Не удалось вернуть спрятанные изменения после слияния: {pop_result.stderr.strip()}",
                        "output": pop_result.stdout.strip(),
                    },
                    status_code=500,
                )
            log_info(f"git stash pop в {folder}: {pop_result.stdout.strip()}")

        # Делаем коммит всех изменений после слияния, чтобы пуш прошёл
        add_result = subprocess.run(
            ["git", "add", "-A"],
            cwd=str(folder),
            capture_output=True,
            text=True,
        )
        log_info(f"git add -A после merge в {folder}: {add_result.stdout.strip()} {add_result.stderr.strip()}")

        commit_result2 = subprocess.run(
            ["git", "commit", "-m", "Merge remote changes via PortfolioForge"],
            cwd=str(folder),
            capture_output=True,
            text=True,
        )
        if commit_result2.returncode != 0 and "nothing to commit" not in commit_result2.stdout.lower():
            log_info(f"git commit после merge в {folder}: {commit_result2.stdout.strip()} {commit_result2.stderr.strip()}")
        else:
            log_info(f"git commit после merge в {folder}: ничего нового для коммита")

        log_info(f"git merge origin/main выполнен в {folder}: {merge_result.stdout.strip()}")
        return JSONResponse({"ok": True, "output": merge_result.stdout.strip()})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=500)'''

new = '''@app.post("/git/pull-rebase")
async def git_pull_rebase(request: Request) -> JSONResponse:
    """Выполняет git fetch + git reset --hard origin/main в указанной папке.

    Перед сбросом делает git stash push -u (включая неотслеживаемые файлы),
    а после сброса — git stash pop, чтобы вернуть изменения обратно.
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
        # Скрываем ВСЕ изменения, включая неотслеживаемые файлы (-u)
        stash_result = subprocess.run(
            ["git", "stash", "push", "-u", "-m", "PortfolioForge auto-stash before reset"],
            cwd=str(folder),
            capture_output=True,
            text=True,
        )
        stashed = "No local changes to save" not in stash_result.stdout
        log_info(f"git stash push -u в {folder}: {stash_result.stdout.strip()}")

        # Скачиваем изменения с удалённого репозитория
        fetch_result = subprocess.run(
            ["git", "fetch", "origin"],
            cwd=str(folder),
            capture_output=True,
            text=True,
        )
        log_info(f"git fetch origin в {folder}: {fetch_result.stdout.strip()} {fetch_result.stderr.strip()}")

        # Сбрасываем локальную ветку в состояние удалённой (убирает все локальные изменения)
        reset_result = subprocess.run(
            ["git", "reset", "--hard", "origin/main"],
            cwd=str(folder),
            capture_output=True,
            text=True,
        )
        if reset_result.returncode != 0:
            if stashed:
                pop_result = subprocess.run(
                    ["git", "stash", "pop"],
                    cwd=str(folder),
                    capture_output=True,
                    text=True,
                )
                log_info(f"git stash pop после ошибки reset в {folder}: {pop_result.stdout.strip()} {pop_result.stderr.strip()}")
            return JSONResponse(
                {"error": reset_result.stderr.strip() or "Ошибка git reset --hard origin/main"},
                status_code=500,
            )
        log_info(f"git reset --hard origin/main в {folder}: {reset_result.stdout.strip()}")

        # Возвращаем спрятанные изменения, если они были
        if stashed:
            pop_result = subprocess.run(
                ["git", "stash", "pop"],
                cwd=str(folder),
                capture_output=True,
                text=True,
            )
            if pop_result.returncode != 0:
                # stash pop не удался — пробуем сбросить локальные изменения в отслеживаемых файлах и повторить pop
                reset_checkout = subprocess.run(
                    ["git", "checkout", "--", "."],
                    cwd=str(folder),
                    capture_output=True,
                    text=True,
                )
                log_info(f"git checkout -- . после ошибки stash pop в {folder}: {reset_checkout.stdout.strip()} {reset_checkout.stderr.strip()}")
                pop_result = subprocess.run(
                    ["git", "stash", "pop"],
                    cwd=str(folder),
                    capture_output=True,
                    text=True,
                )
                if pop_result.returncode != 0:
                    # stash pop всё равно не удался — возвращаем ошибку пользователю
                    log_info(f"git stash pop конфликт в {folder}: {pop_result.stderr.strip()}")
                    return JSONResponse(
                        {
                            "error": "stash_pop_conflict",
                            "message": f"Не удалось вернуть спрятанные изменения после слияния: {pop_result.stderr.strip()}",
                            "output": pop_result.stdout.strip(),
                        },
                        status_code=500,
                    )
                log_info(f"git stash pop в {folder} (повтор после checkout): {pop_result.stdout.strip()}")
            else:
                log_info(f"git stash pop в {folder}: {pop_result.stdout.strip()}")

        # Делаем коммит всех изменений после слияния, чтобы пуш прошёл
        add_result = subprocess.run(
            ["git", "add", "-A"],
            cwd=str(folder),
            capture_output=True,
            text=True,
        )
        log_info(f"git add -A после merge в {folder}: {add_result.stdout.strip()} {add_result.stderr.strip()}")

        commit_result2 = subprocess.run(
            ["git", "commit", "-m", "Merge remote changes via PortfolioForge"],
            cwd=str(folder),
            capture_output=True,
            text=True,
        )
        if commit_result2.returncode != 0 and "nothing to commit" not in commit_result2.stdout.lower():
            log_info(f"git commit после merge в {folder}: {commit_result2.stdout.strip()} {commit_result2.stderr.strip()}")
        else:
            log_info(f"git commit после merge в {folder}: ничего нового для коммита")

        log_info(f"git merge origin/main выполнен в {folder}")
        return JSONResponse({"ok": True, "output": "Слияние выполнено успешно"})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=500)'''

if old in content:
    content = content.replace(old, new)
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Replacement successful')
else:
    print('Old string not found in file')
    idx = content.find('@app.post("/git/pull-rebase")')
    if idx >= 0:
        print('Found function at index', idx)
        print(repr(content[idx:idx+100]))
    else:
        print('Function not found at all')
