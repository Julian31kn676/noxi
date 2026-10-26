"""zapret (winws.exe) и голос Капри. Стратегии zapret иногда ломают соединение с сервером голоса Microsoft
(speech.platform.bing.com) — тогда Капри говорит голосом Windows. Лечится исключением bing.com в списке
zapret lists/list-exclude.txt и перезапуском zapret."""
import os
import re

import psutil

VOICE_HOST = "bing.com"
# ошибки сети, а не настроек: сервер не отвечает, соединение оборвали
NETWORK_ERROR = re.compile(r"cannot connect|сетев|getaddrinfo|reset|ssl|timed? ?out|disconnect|winerror 64|"
                           r"connection", re.IGNORECASE)


def running():
    """Запущен ли zapret. Имя процесса видно даже без прав администратора, путь к нему — нет."""
    return any((p.info["name"] or "").lower() == "winws.exe" for p in psutil.process_iter(["name"]))


def find_lists():
    """Папка lists сборки zapret (рядом с bin\\winws.exe) или None. Ищем там, куда её обычно кладут:
    сам zapret запущен от администратора, и путь к нему из процесса не узнать."""
    home = os.path.expanduser("~")
    bases = [os.path.join(home, d) for d in ("Desktop", "Downloads", "Documents", r"OneDrive\Desktop")]
    bases += [home] + [f"{d}:\\" for d in "CDEF" if os.path.exists(f"{d}:\\")]
    for base in bases:
        try:
            candidates = [base] + [os.path.join(base, n) for n in os.listdir(base)]
        except OSError:
            continue
        for folder in candidates:
            if os.path.isfile(os.path.join(folder, "bin", "winws.exe")) and os.path.isdir(os.path.join(folder, "lists")):
                return os.path.join(folder, "lists")
    return None


def excluded(lists):
    try:
        with open(os.path.join(lists, "list-exclude.txt"), encoding="utf-8", errors="ignore") as f:
            names = {line.strip().lower() for line in f}
    except OSError:
        return False
    return VOICE_HOST in names or "speech.platform.bing.com" in names


def add_exclude(lists):
    """Дописать bing.com в lists/list-exclude.txt (zapret не трогает домены оттуда и их поддомены)."""
    path = os.path.join(lists, "list-exclude.txt")
    text = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="ignore") as f:
            text = f.read()
    with open(path, "a", encoding="utf-8") as f:
        f.write(("" if not text or text.endswith("\n") else "\n") + VOICE_HOST + "\n")
    return path
