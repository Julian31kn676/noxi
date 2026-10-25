"""Управление тем, что сейчас играет (музыка, YouTube в браузере, плееры) через системные
мультимедиа-элементы Windows — те же, что у плашки громкости с названием трека."""
import asyncio
import ctypes
import datetime
import logging
import re
import time
import urllib.parse

log = logging.getLogger("capri")
PLAYING, PAUSED = 4, 5
TICKS = 10_000_000  # в Windows время меряется в 100-наносекундных тиках


def _run(coro):
    return asyncio.run(coro)


async def _sessions():
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as M
    mgr = await M.request_async()
    return mgr, list(mgr.get_sessions())


async def _pick(prefer_playing=True, source=None):
    """Сессия, которой управляем: та, что играет; иначе та, что Капри ставила на паузу (source);
    иначе «текущая» по мнению Windows; иначе первая."""
    mgr, sessions = await _sessions()
    if not sessions:
        return None
    if source and not prefer_playing:
        for s in sessions:
            if s.source_app_user_model_id == source:
                return s
    if prefer_playing:
        for s in sessions:
            if s.get_playback_info().playback_status == PLAYING:
                return s
    return mgr.get_current_session() or sessions[0]


def _position(s):
    """Текущая позиция в секундах с поправкой на время, прошедшее с последнего обновления."""
    tl = s.get_timeline_properties()
    pos = tl.position.total_seconds()
    if s.get_playback_info().playback_status == PLAYING:
        upd = tl.last_updated_time
        if upd.year > 1970:
            pos += max(0.0, (datetime.datetime.now(datetime.timezone.utc) - upd).total_seconds())
    return pos, tl.end_time.total_seconds()


async def _describe(s):
    p = await s.try_get_media_properties_async()
    title = (p.title or "").strip()
    artist = (p.artist or "").strip()
    return f"{artist} — {title}" if artist and artist.lower() not in ("неизв. исполнитель", "unknown artist") else title


def now_playing():
    """(описание, источник, играет ли) или None."""
    async def go():
        s = await _pick()
        if not s:
            return None
        return await _describe(s), s.source_app_user_model_id, s.get_playback_info().playback_status == PLAYING
    return _run(go())


def control(action, source=None):
    """pause / play / toggle / next / prev → (ok, описание трека, источник)."""
    async def go():
        s = await _pick(prefer_playing=action != "play", source=source)
        if not s:
            return False, None, None
        if action == "pause" and s.get_playback_info().playback_status != PLAYING:
            return False, None, None  # ничего не играет — нечего ставить на паузу
        f = {"pause": s.try_pause_async, "play": s.try_play_async, "toggle": s.try_toggle_play_pause_async,
             "next": s.try_skip_next_async, "prev": s.try_skip_previous_async}[action]
        ok = await f()
        return ok, await _describe(s), s.source_app_user_model_id
    return _run(go())


def seek(seconds=None, delta=None):
    """Перемотка: на абсолютное время (seconds) или на смещение (delta, может быть отрицательным).
    Возвращает (ok, новая позиция, источник)."""
    async def go():
        s = await _pick()
        if not s:
            return False, None, None
        pos, end = _position(s)
        target = seconds if seconds is not None else pos + (delta or 0)
        if end > 0:
            target = min(target, end - 1)
        target = max(0.0, target)
        ok = False
        if s.get_playback_info().controls.is_playback_position_enabled:
            ok = await s.try_change_playback_position_async(int(target * TICKS))
        return ok, target, s.source_app_user_model_id
    return _run(go())


# ---------------- разбор времени ----------------

def _num(text):
    from actions import parse_number
    return parse_number(text)


ORDINALS = [  # корень порядкового числа → количественное («двадцать седьмой минуты» → «двадцать семь»)
    ("одиннадцат", "одиннадцать"), ("двенадцат", "двенадцать"), ("тринадцат", "тринадцать"),
    ("четырнадцат", "четырнадцать"), ("пятнадцат", "пятнадцать"), ("шестнадцат", "шестнадцать"),
    ("семнадцат", "семнадцать"), ("восемнадцат", "восемнадцать"), ("девятнадцат", "девятнадцать"),
    ("двадцат", "двадцать"), ("тридцат", "тридцать"), ("сороков", "сорок"), ("пятидесят", "пятьдесят"),
    ("шестидесят", "шестьдесят"), ("семидесят", "семьдесят"), ("восьмидесят", "восемьдесят"),
    ("девяност", "девяносто"), ("сот", "сто"),
    ("перв", "один"), ("втор", "два"), ("трет", "три"), ("четверт", "четыре"), ("пят", "пять"),
    ("шест", "шесть"), ("седьм", "семь"), ("восьм", "восемь"), ("девят", "девять"), ("десят", "десять"),
]
ORD_END = r"(ой|ая|ую|ый|ий|ей|ья|ье|ого|ому|ом|ым|ые|ых|ьей|ьего|ьим)"


def ordinals_to_cardinals(t):
    """«с двадцать седьмой минуты» → «с двадцать семь минуты», «с 27-й минуты» → «с 27 минуты»."""
    t = re.sub(r"(\d+)-?(й|я|ю|ой|ая|ую|ий|ей|го|ого)\b", r"\1", t)
    words = []
    for w in t.split():
        for stem, card in ORDINALS:
            if re.fullmatch(stem + ORD_END, w):
                w = card
                break
        words.append(w)
    return " ".join(words)


def parse_time(text):
    """«3:14», «1:02:03», «3 минуты 14 секунд», «на две минуты», «полминуты», «на начало» → секунды."""
    t = ordinals_to_cardinals(text.lower().replace("ё", "е"))
    if re.search(r"\bнача\w*|\bсначала\b|\bзаново\b", t):
        return 0
    m = re.search(r"(\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?", t)
    if m:
        a, b, c = int(m.group(1)), int(m.group(2)), m.group(3)
        return a * 3600 + b * 60 + int(c) if c else a * 60 + b
    if "полминут" in t:
        return 30
    if "полторы минут" in t:
        return 90
    total, found = 0, False
    for unit, mult in ((r"час\w*", 3600), (r"минут\w*", 60), (r"секунд\w*|сек\b", 1)):
        um = re.search(rf"(?:(\S+(?:\s+\S+)?)\s+)?(?:{unit})", t)
        if um:
            before = um.group(1) or ""
            n = None
            # число прямо перед единицей: «3 минуты», «двадцать пять секунд», «минуту» (= 1)
            words = before.split()
            for k in (2, 1):
                if len(words) >= k:
                    n = _num(" ".join(words[-k:]))
                    if n is not None:
                        break
            total += (n if n is not None else 1) * mult
            found = True
    if found:
        return total
    nums = number_groups(t)
    if len(nums) == 2:  # «поставь на 3 14», «три четырнадцать» — минуты и секунды
        return nums[0] * 60 + nums[1]
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    if nums and nums[0] >= 100 and nums[0] % 100 < 60:  # «тайминг 314» → 3:14, «1205» → 12:05
        return nums[0] // 100 * 60 + nums[0] % 100
    return nums[0] if nums else None  # одно число без единиц — секунды


def number_groups(t):
    """Отдельные числа в тексте: «три четырнадцать» → [3, 14], «двадцать пять» → [25], «3 14» → [3, 14]."""
    from actions import NUM
    out, tens = [], None
    for w in ordinals_to_cardinals(t).split():
        if w.isdigit():
            out.append(int(w))
            tens = None
        elif w in NUM:
            v = NUM[w]
            if tens is not None and 1 <= v <= 9:  # «двадцать» + «пять»
                out[-1] += v
                tens = None
            else:
                out.append(v)
                tens = v if v in (20, 30, 40, 50, 60, 70, 80, 90) else None
        else:
            tens = None
    return out


def fmt(seconds):
    seconds = int(round(seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ---------------- запасной путь для YouTube в браузере ----------------

def _clipboard_text():
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    k.GlobalLock.restype = ctypes.c_void_p
    u.GetClipboardData.restype = ctypes.c_void_p
    if not u.OpenClipboard(0):
        return ""
    try:
        h = u.GetClipboardData(13)  # CF_UNICODETEXT
        if not h:
            return ""
        p = k.GlobalLock(ctypes.c_void_p(h))
        try:
            return ctypes.wstring_at(p) if p else ""
        finally:
            k.GlobalUnlock(ctypes.c_void_p(h))
    finally:
        u.CloseClipboard()


def _urlbar(hwnd):
    """Адресная строка браузера как элемент UI Automation (или None) и её ValuePattern."""
    import comtypes.client
    comtypes.client.GetModule("UIAutomationCore.dll")
    from comtypes.gen import UIAutomationClient as UIA
    uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
    root = uia.ElementFromHandle(hwnd)
    bar = root.FindFirst(UIA.TreeScope_Descendants,  # Firefox
                         uia.CreatePropertyCondition(UIA.UIA_AutomationIdPropertyId, "urlbar-input"))
    candidates = [bar] if bar else []
    if not candidates:  # Chrome, Edge, Яндекс: поле ввода, в котором записан адрес
        edits = root.FindAll(UIA.TreeScope_Descendants,
                             uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, UIA.UIA_EditControlTypeId))
        candidates = [edits.GetElement(i) for i in range(min(edits.Length, 8))]
    for el in candidates:
        try:
            vp = el.GetCurrentPattern(UIA.UIA_ValuePatternId).QueryInterface(UIA.IUIAutomationValuePattern)
        except Exception:
            continue
        value = vp.CurrentValue or ""
        if bar is not None or re.search(r"\.\w{2,}(/|$)", value):
            return el, vp
    return None, None


def page_url(hwnd):
    """Адрес любой открытой вкладки браузера (для «запомни этот сайт») или None."""
    try:
        _, vp = _urlbar(hwnd)
        value = ((vp.CurrentValue or "") if vp else "").strip()
    except Exception:
        log.exception("Не удалось прочитать адрес вкладки")
        return None
    if not re.match(r"^(https?://)?[\w\-]+(\.[\w\-]+)*\.[a-zа-я]{2,}(:\d+)?(/\S*)?$", value, re.IGNORECASE):
        return None
    return value if value.startswith("http") else "https://" + value


def browser_url(hwnd):
    """Адрес активной вкладки браузера — читаем адресную строку через UI Automation (без копирования)."""
    try:
        _, vp = _urlbar(hwnd)
        value = (vp.CurrentValue or "") if vp else ""
        if "youtube" in value or "youtu.be" in value:
            return value if value.startswith("http") else "https://" + value
    except Exception:
        log.exception("Не удалось прочитать адрес вкладки")
    return None


def navigate(hwnd, url):
    """Открыть адрес в текущей вкладке браузера. Фокус ставится в адресную строку через UI Automation,
    и Enter нажимается только если там ровно нужный адрес — иначе ничего не жмём (чтобы буквы и цифры
    не ушли в страницу, где на YouTube это горячие клавиши)."""
    from actions import send_keys
    import automation
    try:
        el, vp = _urlbar(hwnd)
        if not el:
            return False
        el.SetFocus()
        time.sleep(0.25)
        if not el.CurrentHasKeyboardFocus:
            send_keys(["ctrl", "l"])  # запасной способ
            time.sleep(0.4)
            if not el.CurrentHasKeyboardFocus:
                log.info("Адресная строка не получила фокус — ничего не печатаю")
                return False
        send_keys(["ctrl", "a"])
        time.sleep(0.1)
        automation.type_text(url)
        time.sleep(0.25)
        typed = (vp.CurrentValue or "").strip()
        if typed.rstrip("/") != url.rstrip("/") and typed.rstrip("/") != url.split("://", 1)[-1].rstrip("/"):
            log.info("В адресной строке не то, что нужно (%r) — не открываю", typed[:120])
            send_keys(["esc"])
            return False
        send_keys(["enter"])
        return True
    except Exception:
        log.exception("Не удалось открыть адрес")
        return False


def youtube_url_seek(seconds):
    """Перематывает видео YouTube: открывает ту же ссылку, где метка времени t заменена на нужную."""
    import automation
    from actions import send_keys
    hwnd = automation.find_window(("youtube",))
    if not hwnd or not automation.focus(hwnd):
        return False
    url = browser_url(hwnd)
    if not url:
        return False
    parts = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parts.query)
    if "youtu.be" in parts.netloc:  # короткая ссылка youtu.be/ID
        query.setdefault("v", [parts.path.strip("/")])
    if not query.get("v"):
        return False  # это не страница видео (главная, поиск)
    query.pop("t", None)  # старая метка: если оставить, YouTube возьмёт её, а не новую
    keep = {k: v[0] for k, v in query.items() if k in ("v", "list", "index")}
    new = "https://www.youtube.com/watch?" + urllib.parse.urlencode(keep) + f"&t={int(seconds)}s"
    log.info("YouTube: %s → %s", url, new)
    return navigate(hwnd, new)
