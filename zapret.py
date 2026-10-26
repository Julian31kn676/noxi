"""zapret (winws.exe) и голос Капри. Стратегии zapret иногда ломают соединение с сервером голоса Microsoft
(speech.platform.bing.com) — тогда Капри говорит голосом Windows. Лечится исключениями в папке lists сборки zapret:
bing.com в list-exclude.txt (по имени сайта) и адреса сервера голоса в ipset-exclude.txt (по IP — их учитывают
все стратегии, даже те, где исключение по имени не срабатывает), и перезапуском zapret."""
import os
import re
import socket

import psutil

VOICE_SERVER = "speech.platform.bing.com"
VOICE_HOST = "bing.com"
# подсети сервера голоса на случай, если DNS отдаст другой адрес из той же сети
VOICE_NETS = ["150.171.27.0/24", "150.171.28.0/24", "2620:1ec:33::/48"]
# ошибки сети, а не настроек: сервер не отвечает, соединение оборвали
NETWORK_ERROR = re.compile(r"cannot connect|сетев|getaddrinfo|reset|ssl|timed? ?out|disconnect|winerror 64|"
                           r"connection", re.IGNORECASE)


def running():
    """Запущен ли zapret. Имя процесса видно даже без прав администратора, путь к нему — нет."""
    return any((p.info["name"] or "").lower() == "winws.exe" for p in psutil.process_iter(["name"]))


def find_all_lists():
    """Папки lists всех сборок zapret (рядом с bin\\winws.exe). Ищем там, куда их обычно кладут: сам zapret
    запущен от администратора, и путь к нему из процесса не узнать. Копий бывает несколько (старая в «Загрузках»,
    рабочая в другом месте) — поэтому возвращаем все."""
    home = os.path.expanduser("~")
    bases = [os.path.join(home, d) for d in ("Desktop", "Downloads", "Documents", r"OneDrive\Desktop")]
    bases += [home] + [f"{d}:\\" for d in "CDEF" if os.path.exists(f"{d}:\\")]
    found = []
    for base in bases:
        try:
            candidates = [base] + [os.path.join(base, n) for n in os.listdir(base)]
        except OSError:
            continue
        for folder in candidates:
            lists = os.path.join(folder, "lists")
            if (os.path.isfile(os.path.join(folder, "bin", "winws.exe")) and os.path.isdir(lists)
                    and os.path.normcase(lists) not in map(os.path.normcase, found)):
                found.append(lists)
    return found


def find_lists():
    found = find_all_lists()
    return found[0] if found else None


def voice_addresses():
    """Адреса сервера голоса: текущие из DNS плюс подсети на случай смены адреса."""
    out = []
    try:
        out = sorted({a[4][0] for a in socket.getaddrinfo(VOICE_SERVER, 443)})
    except OSError:
        pass
    return out + VOICE_NETS


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return ""


def _lines(path):
    return {line.strip().lower() for line in _read(path).splitlines()}


def excluded(lists):
    """Есть ли оба исключения: по имени сайта и по адресам."""
    names = _lines(os.path.join(lists, "list-exclude.txt"))
    ips = _lines(os.path.join(lists, "ipset-exclude.txt"))
    by_name = VOICE_HOST in names or VOICE_SERVER in names
    by_ip = all(net in ips for net in VOICE_NETS[:2])
    return by_name and by_ip


def _append(path, items):
    have = _lines(path)
    new = [i for i in items if i.lower() not in have]
    if new:
        text = _read(path)
        with open(path, "a", encoding="utf-8") as f:
            f.write(("" if not text or text.endswith("\n") else "\n") + "\n".join(new) + "\n")
    return new


def add_exclude(lists):
    """Дописать bing.com в list-exclude.txt и адреса сервера голоса в ipset-exclude.txt."""
    _append(os.path.join(lists, "list-exclude.txt"), [VOICE_HOST])
    _append(os.path.join(lists, "ipset-exclude.txt"), voice_addresses())
    return lists
