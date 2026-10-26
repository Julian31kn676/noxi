"""Печать текста и цепочки действий в окнах: «открой телеграм, первый чат, напиши привет»."""
import ctypes
import logging
import os
import re
import time
from ctypes import wintypes

log = logging.getLogger("capri")
u = ctypes.windll.user32

# ---------------- ввод текста ----------------

ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004


def type_text(text, delay=0.012):
    """Печатает любой текст (в т.ч. русский) в активное окно — независимо от раскладки клавиатуры."""
    for ch in text:
        if ch == "\n":
            ch = "\r"
        for unit in ch.encode("utf-16-le").decode("utf-16-le"):
            code = ord(unit)
            down = INPUT(type=1, u=_INPUTUNION(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, 0)))
            up = INPUT(type=1, u=_INPUTUNION(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)))
            arr = (INPUT * 2)(down, up)
            u.SendInput(2, arr, ctypes.sizeof(INPUT))
        time.sleep(delay)


# ---------------- окна ----------------

def window_title(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    u.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def foreground_title():
    hwnd = u.GetForegroundWindow()
    return window_title(hwnd) if hwnd else ""


def process_window(exe_names):
    """Главное видимое окно процесса (по имени exe). Нужно для программ, у которых заголовок окна —
    не их название: у Telegram Desktop это название открытого чата."""
    import psutil
    exe_names = {n.lower() for n in exe_names}
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        if u.IsWindowVisible(hwnd) and window_title(hwnd):
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                if psutil.Process(pid.value).name().lower() in exe_names:
                    found.append(hwnd)
            except Exception:
                pass
        return True
    u.EnumWindows(cb, 0)
    return found[0] if found else None


PROCESS_OF = {"telegram": ("telegram.exe",), "discord": ("discord.exe",), "whatsapp": ("whatsapp.exe",)}


def find_window(keywords):
    for k in keywords:  # у некоторых программ ищем окно по процессу, а не по заголовку
        if k in PROCESS_OF:
            hwnd = process_window(PROCESS_OF[k])
            if hwnd:
                return hwnd
    return _find_by_title(keywords)


def _find_by_title(keywords):
    """Видимое окно, в заголовке которого есть одно из слов. Если подходит активное окно — берём его;
    иначе предпочитаем окно, чей заголовок начинается со слова (сам «Telegram», а не вкладку браузера
    со словом telegram)."""
    fg = u.GetForegroundWindow()
    if fg and any(k in window_title(fg).lower() for k in keywords):
        return fg
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        if u.IsWindowVisible(hwnd):
            t = window_title(hwnd).lower()
            if t and any(k in t for k in keywords):
                exact = any(t.startswith(k) for k in keywords)
                found.append((0 if exact else 1, hwnd))
        return True
    u.EnumWindows(cb, 0)
    return min(found, key=lambda x: x[0])[1] if found else None


def is_foreground(hwnd):
    """Активно ли окно hwnd (или его дочернее/владеющее — у браузеров это может быть другое окно того же
    процесса)."""
    fg = u.GetForegroundWindow()
    if not fg:
        return False
    if fg == hwnd or u.GetAncestor(fg, 2) == hwnd:  # GA_ROOT
        return True
    p1, p2 = wintypes.DWORD(), wintypes.DWORD()
    u.GetWindowThreadProcessId(fg, ctypes.byref(p1))
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(p2))
    return p1.value == p2.value and window_title(fg) == window_title(hwnd)


def focus(hwnd):
    """Сделать окно активным. Windows не даёт фоновой программе забирать фокус, поэтому по очереди:
    «пустой» Alt, присоединение к потоку активного окна, а если не вышло — свернуть и развернуть окно.
    Возвращает True, только если окно действительно стало активным."""
    k = ctypes.windll.kernel32
    for attempt in range(3):
        if u.IsIconic(hwnd):
            u.ShowWindow(hwnd, 9)  # SW_RESTORE
        fg = u.GetForegroundWindow()
        me, fg_tid = k.GetCurrentThreadId(), u.GetWindowThreadProcessId(fg, None)
        attached = bool(fg_tid and fg_tid != me and u.AttachThreadInput(me, fg_tid, True))
        u.keybd_event(0x12, 0, 0, 0)
        u.keybd_event(0x12, 0, 2, 0)
        u.BringWindowToTop(hwnd)
        u.SetForegroundWindow(hwnd)
        if attached:
            u.AttachThreadInput(me, fg_tid, False)
        time.sleep(0.3)
        if is_foreground(hwnd):
            return True
        if attempt == 0:  # SwitchToThisWindow — то, чем пользуется Alt+Tab; часто проходит там, где другое нет
            u.SwitchToThisWindow(hwnd, True)
            time.sleep(0.3)
            if is_foreground(hwnd):
                return True
        if attempt == 1:  # крайний способ: развёрнутое из свёрнутого окно Windows активирует сама
            u.ShowWindow(hwnd, 6)   # SW_MINIMIZE
            time.sleep(0.2)
            u.ShowWindow(hwnd, 9)   # SW_RESTORE
            time.sleep(0.4)
            if is_foreground(hwnd):
                return True
    log.info("Не удалось активировать окно «%s»", window_title(hwnd))
    return False


def wait_and_focus(keywords, timeout=10.0):
    """Ждём, пока появится окно (например, только что запущенный Telegram), и делаем его активным."""
    end = time.time() + timeout
    while time.time() < end:
        hwnd = find_window(keywords)
        if hwnd:
            if is_foreground(hwnd):  # нужное окно уже активно — ничего не переключаем
                return hwnd
            time.sleep(0.6)  # даём окну дорисоваться
            return hwnd if focus(hwnd) else None
        time.sleep(0.4)
    return None


# ---------------- прокрутка ----------------

def _content_point(hwnd):
    """Точка в середине окна, чуть ниже центра — там обычно основное содержимое, а не меню и вкладки."""
    r = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left + r.right) // 2, r.top + int((r.bottom - r.top) * 0.58), r.bottom - r.top


def _own(hwnd):
    """Окно самой Капри (аватар, молния, окна настроек)?"""
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value == os.getpid()


def target_window():
    """Окно, которое листать: активное, а если активна сама Капри (по ней кликнули) — следующее под ней."""
    hwnd = u.GetForegroundWindow()
    while hwnd and (_own(hwnd) or not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd)):
        hwnd = u.GetWindow(hwnd, 2)  # GW_HWNDNEXT — следующее окно ниже по z-порядку
    return hwnd


def _visible_point(hwnd):
    """Точка внутри окна, где под курсором именно это окно, а не Капри поверх него (она стоит поверх всех
    окон и может закрывать середину страницы). Колесо мыши получает окно под курсором."""
    r = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    for fx, fy in ((0.5, 0.58), (0.3, 0.58), (0.7, 0.58), (0.5, 0.4), (0.5, 0.75), (0.2, 0.4), (0.8, 0.4),
                   (0.2, 0.75), (0.8, 0.75), (0.35, 0.3), (0.65, 0.3)):
        x, y = r.left + int(w * fx), r.top + int(h * fy)
        under = u.WindowFromPoint(wintypes.POINT(x, y))
        if under and u.GetAncestor(under, 2) == hwnd:  # GA_ROOT — верхнее окно, которому принадлежит точка
            return x, y
    x, y, _ = _content_point(hwnd)
    return x, y


def scroll(notches, hwnd=None, delay=0.012):
    """Крутит колёсико над содержимым активного окна (notches > 0 — вниз). Курсор возвращается на место.
    Колесо, а не клавиши: прокручивает страницу, даже если фокус ввода стоит в каком-нибудь поле."""
    hwnd = hwnd or target_window()
    if not hwnd:
        return False
    x, y = _visible_point(hwnd)
    old = wintypes.POINT()
    u.GetCursorPos(ctypes.byref(old))
    u.SetCursorPos(x, y)
    step = -120 if notches > 0 else 120  # WHEEL_DELTA: «минус» — вниз
    for _ in range(abs(int(notches))):
        u.mouse_event(0x0800, 0, 0, ctypes.c_uint32(step & 0xFFFFFFFF).value, 0)  # MOUSEEVENTF_WHEEL
        time.sleep(delay)
    time.sleep(0.05)
    u.SetCursorPos(old.x, old.y)
    return True


def screen_notches(hwnd=None):
    """Сколько щелчков колеса примерно равно одному экрану (щелчок ≈ 3 строки ≈ 60 px)."""
    hwnd = hwnd or target_window()
    if not hwnd:
        return 8
    _, _, height = _content_point(hwnd)
    return max(3, int(height * 0.8 / 60))


# ---------------- разбор цепочки ----------------

APP_WINDOWS = {  # как опознать окно приложения по заголовку
    "telegram": ("telegram",), "телеграм": ("telegram",), "телега": ("telegram",),
    "ютуб": ("youtube",), "youtube": ("youtube",),
    "блокнот": ("блокнот", "notepad"), "notepad": ("notepad", "блокнот"),
    "дискорд": ("discord",), "discord": ("discord",),
    "ватсап": ("whatsapp",), "whatsapp": ("whatsapp",),
    "вк": ("вконтакте", "vk"), "вконтакте": ("вконтакте", "vk"),
    "браузер": ("firefox", "chrome", "edge", "opera", "яндекс", "brave"),
}
TYPE_VERBS = r"напиши|напечатай|введи|набери|вбей|впиши|пиши"
NOT_TYPING = r"(стих\w*|стишок|рассказ\w*|истори\w*|сказк\w*|шутк\w*|анекдот\w*|песн\w*|сочинени\w*|эссе)\b"
ORDINALS = {"первый": 1, "первую": 1, "второй": 2, "вторую": 2, "третий": 3, "третью": 3, "четвертый": 4,
            "четвёртый": 4, "пятый": 5, "шестой": 6, "седьмой": 7, "восьмой": 8, "девятый": 9, "десятый": 10}
STEP_START = re.compile(
    r"\b(?<!нажми на )(?<!нажми )(?<!перейди )(?<!перейди в )(?<!поставь курсор в )"
    r"(?:и\s+|потом\s+|затем\s+|после\s+этого\s+)?"
    r"(?=(?:открой|запусти|зайди|перейди|нажми на поиск|нажми поиск|поиск|в поиск|найди|поищи|"
    r"прокрути|пролистай|листай|полистай|скролль|промотай страниц|"
    rf"{TYPE_VERBS}|отправь|(?:{'|'.join(ORDINALS)}) (?:чат|диалог|переписк)|"
    r"(?:в |открой )?(?:чат\w*|chat|диалог\w*|переписк\w*|контакт\w*) )\b)")


def split_chain(cmd):
    """«открой телеграм первый чат напиши привет» → ['открой телеграм', 'первый чат', 'напиши привет'].
    Всё после «напиши» — это текст (кроме хвоста «и отправь»). None — если шаг один."""
    c = cmd.strip()
    m = re.search(rf"\b({TYPE_VERBS})\b", c)
    head, tail = (c[:m.start()], c[m.start():]) if m else (c, "")
    parts = [p.strip(" ,.") for p in STEP_START.split(head) if p and p.strip(" ,.")]
    parts = [re.sub(r"\s+(и|потом|затем)$", "", re.sub(r"^(и|потом|затем|после этого)\s+", "", p))
             for p in parts]
    if tail:
        parts.append(tail.strip(" ,."))
    parts = [p for p in parts if p]
    merged = []
    for p in parts:
        # «найди в телеграм» / «зайди в телеграм» в начале цепочки = открыть Telegram
        p = re.sub(r"^(найди|зайди|перейди|открой)( в)? (телеграм\w*|telegram|телег\w*)$", "открой телеграм", p)
        if merged and (merged[-1] in ORDINALS or merged[-1] in ("открой", "зайди", "перейди", "найди", "зайди в",
                                                                 "перейди в", "открой мне")):
            merged[-1] = merged[-1] + " " + p  # «третий» + «чат», «открой» + «чат с мамой»
        else:
            merged.append(p)
    return merged if len(merged) >= 2 else None


def parse_type(step):
    """«напиши привет и отправь» → ('привет', True). None — если это не печать."""
    m = re.match(rf"^({TYPE_VERBS})\s+(?P<t>.+)$", step.strip())
    if not m:
        return None
    text = m.group("t").strip()
    if re.match(NOT_TYPING, text):
        return None
    # «напиши» — печатает и отправляет (Enter), «напечатай / введи / набери» — только печатает
    send = None if m.group(1) in ("напиши", "пиши", "впиши") else False
    end = re.search(r"\s+(и\s+)?(отправь|отправить|нажми энтер|нажми enter|и энтер)$", text)
    if end:
        text, send = text[:end.start()].strip(), True
    text = re.sub(r"^(текст|сообщение|фразу|слово)\s+", "", text)
    return text, send


def focus_search(title):
    """Поставить курсор в поиск текущего окна: YouTube — «/», Telegram — Esc, браузер — адресная строка."""
    from actions import send_keys
    t = title.lower()
    if "youtube" in t:
        send_keys(["esc"])
        type_text("/")  # «/» на YouTube = фокус в поиск (символом, чтобы не зависеть от раскладки)
        return "youtube"
    if "telegram" in t:
        send_keys(["esc"])
        time.sleep(0.15)
        send_keys(["esc"])
        return "telegram"
    send_keys(["ctrl", "l"])  # адресная строка браузера = поиск
    return "browser"


MESSENGERS = {"telegram.exe", "discord.exe", "whatsapp.exe", "viber.exe"}


def foreground_process():
    import psutil
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(u.GetForegroundWindow(), ctypes.byref(pid))
    try:
        return psutil.Process(pid.value).name().lower()
    except Exception:
        return ""


def window_exe(hwnd):
    """Полный путь к программе, которой принадлежит окно, или None."""
    import psutil
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        return psutil.Process(pid.value).exe()
    except Exception:
        return None


def input_text(text):
    """Ввести текст в активное окно: в мессенджерах — вставкой (там посимвольная печать теряет буквы),
    в остальных программах — печатью."""
    if foreground_process() in MESSENGERS:
        paste_text(text)
    else:
        type_text(text)


def set_clipboard(text):
    """Положить текст в буфер обмена."""
    k = ctypes.windll.kernel32
    k.GlobalAlloc.restype = ctypes.c_void_p
    k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalLock.argtypes = [ctypes.c_void_p]
    k.GlobalUnlock.argtypes = [ctypes.c_void_p]
    u.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    data = text.encode("utf-16-le") + b"\x00\x00"
    for _ in range(5):
        if u.OpenClipboard(0):
            break
        time.sleep(0.05)
    else:
        return False
    try:
        u.EmptyClipboard()
        h = k.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
        p = k.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        k.GlobalUnlock(h)
        u.SetClipboardData(13, h)  # CF_UNICODETEXT
        return True
    finally:
        u.CloseClipboard()


def paste_text(text):
    """Вставить текст через буфер обмена (Ctrl+V) и вернуть буферу прежнее содержимое.
    Надёжнее посимвольной печати в программах вроде Telegram, где отдельные символы могут потеряться."""
    from actions import send_keys
    from media import _clipboard_text
    old = _clipboard_text()
    if not set_clipboard(text):
        type_text(text, delay=0.05)
        return
    time.sleep(0.05)
    send_keys(["ctrl", "v"])
    time.sleep(0.7)  # программа может обработать вставку не сразу — возвращаем буфер только после
    if old:
        set_clipboard(old)


def _telegram_search_field(hwnd):
    """Поле «Поиск» над списком чатов Telegram (через UI Automation) или None."""
    try:
        import comtypes.client
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as UIA
        uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
        edits = uia.ElementFromHandle(hwnd).FindAll(
            UIA.TreeScope_Descendants,
            uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, UIA.UIA_EditControlTypeId))
        for i in range(edits.Length):
            e = edits.GetElement(i)
            if e.CurrentIsKeyboardFocusable and (e.CurrentName or "").lower() in ("поиск", "search"):
                return e
    except Exception:
        log.exception("Поле поиска Telegram не найдено")
    return None


def telegram_open_chat(index=None, name=None):
    """Открыть чат в Telegram Desktop: по имени (через поле «Поиск») или по номеру в списке.
    Успех проверяем по заголовку окна — у Telegram это название открытого чата."""
    from actions import send_keys
    hwnd = wait_and_focus(("telegram",), timeout=8)
    if not hwnd:
        return False
    before = window_title(hwnd)
    field = _telegram_search_field(hwnd)
    if field is not None:
        field.SetFocus()
        time.sleep(0.25)
    else:  # запасной путь: Esc закрывает чат, курсор уходит в поиск
        send_keys(["esc"])
        time.sleep(0.3)
        send_keys(["esc"])
        time.sleep(0.3)
    send_keys(["ctrl", "a"])  # очистить то, что уже было в поиске
    time.sleep(0.1)
    if name:
        paste_text(name)
        time.sleep(1.5)  # Telegram ищет по мере ввода
        send_keys(["enter"])  # первый результат
    else:
        send_keys(["backspace"])
        time.sleep(0.3)
        for _ in range(max(1, index or 1)):
            send_keys(["down"])
            time.sleep(0.1)
        send_keys(["enter"])
    for _ in range(10):
        time.sleep(0.3)
        title = window_title(hwnd).replace("‎", "").lower()
        if name and any(title.startswith(w) or f" {w}" in title for w in name.lower().split()):
            return True
        if not name and title != before.replace("‎", "").lower():
            return True
    log.info("Чат не открылся: заголовок окна «%s»", window_title(hwnd))
    return False
