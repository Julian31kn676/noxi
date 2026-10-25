"""Капри — голосовой ассистент для Windows.
Запуск: run.bat (или pythonw main.py)."""
import json
import logging
import os
import queue
import random
import re
import sys
import tempfile
import threading
import time

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QInputDialog, QMenu, QSystemTrayIcon

from actions import Actions, Reply
from ai import AI
from local_ai import LocalAI
from persona import line
from avatar import Avatar
from voice import (Listener, Speaker, default_input_name, google_stt, input_devices, make_glitch_sound,
                   play_sound_async)

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "config.json")

logging.basicConfig(filename=os.path.join(BASE, "capri.log"), level=logging.INFO, encoding="utf-8",
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("capri")

DEFAULTS = {
    "enable_ai": False,
    "local_ai": True,
    "local_model": "qwen3:8b",
    "barge_in": True,
    "mic_device": None,
    "chatter": True,
    "chatter_min_minutes": 15,
    "chatter_max_minutes": 40,
    "roam_chance": 0.5,
    "teleport_on_answer": True,
    "anthropic_api_key": "",
    "model": "claude-opus-5-5",
    "wake_words": ["капри", "каприз", "капре", "кепри", "капли"],
    "use_google_stt": True,
    "voice": "ru-RU-SvetlanaNeural",
    "tts_engine": "edge",
    "voice_rate": "+10%",
    "voice_pitch": "+15Hz",
    "voice_shift": 0,
    "voice_lively": False,
    "voice_fx": 1.0,
    "listen_window_seconds": 8,
    "followup_seconds": 6,
    "hide_after_seconds": 12,
    "greet_on_start": True,
    "vosk_model": "models/vosk-model-small-ru-0.22",
    "sites": {
        "ютуб": "https://www.youtube.com", "youtube": "https://www.youtube.com",
        "гугл": "https://www.google.com", "google": "https://www.google.com",
        "яндекс": "https://ya.ru", "вк": "https://vk.com", "вконтакте": "https://vk.com",
        "почту": "https://mail.google.com", "почта": "https://mail.google.com",
        "гитхаб": "https://github.com", "твич": "https://www.twitch.tv",
        "википедию": "https://ru.wikipedia.org", "википедия": "https://ru.wikipedia.org",
        "переводчик": "https://translate.google.com", "карты": "https://yandex.ru/maps",
        "погоду": "https://yandex.ru/pogoda", "chatgpt": "https://chatgpt.com",
        "клод": "https://claude.ai", "кинопоиск": "https://www.kinopoisk.ru",
        "авито": "https://www.avito.ru", "озон": "https://www.ozon.ru",
        "вайлдберриз": "https://www.wildberries.ru"
    },
    "apps": {
        "блокнот": "notepad", "калькулятор": "calc", "проводник": "explorer",
        "диспетчер задач": "taskmgr", "параметры": "ms-settings:", "настройки": "ms-settings:",
        "панель управления": "control", "командную строку": "cmd", "командная строка": "cmd",
        "терминал": "wt", "пейнт": "mspaint", "paint": "mspaint", "ворд": "winword",
        "эксель": "excel", "браузер": "https://www.google.com",
        "настройки звука": "ms-settings:sound", "настройки экрана": "ms-settings:display",
        "корзину": "shell:RecycleBinFolder", "загрузки": "shell:Downloads"
    },
    "app_aliases": {
        "хром": "chrome", "гугл хром": "google chrome", "стим": "steam", "дискорд": "discord",
        "телеграм": "telegram", "телеграмм": "telegram", "спотифай": "spotify",
        "опера": "opera", "яндекс браузер": "yandex", "вс код": "visual studio code",
        "визуал студио код": "visual studio code", "обс": "obs", "эпик геймс": "epic games",
        "ватсап": "whatsapp", "зум": "zoom", "фотошоп": "photoshop", "майнкрафт": "minecraft"
    }
}


def save_setting(key, value):
    """Записать одну настройку в config.json, не трогая остальные."""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    data[key] = value
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_config():
    cfg = json.loads(json.dumps(DEFAULTS))
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                user = json.load(f)
            for k, v in user.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        except Exception:
            log.exception("config.json повреждён, использую настройки по умолчанию")
    else:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULTS, f, ensure_ascii=False, indent=2)
    return cfg


STOP_RE = re.compile(r"\b(стоп|хватит|молчи|замолчи|помолчи|достаточно|подожди|остановись|перестань|"
                     r"заткнись|умолкни)\b")


def fullscreen_app_active():
    """Открыта игра или видео на весь экран — тогда не лезем со спонтанными репликами."""
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        hwnd = u.GetForegroundWindow()
        if not hwnd:
            return False
        cls = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(hwnd, cls, 64)
        if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
            return False  # рабочий стол
        r = wintypes.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(r))
        return (r.right - r.left) >= u.GetSystemMetrics(0) and (r.bottom - r.top) >= u.GetSystemMetrics(1)
    except Exception:
        return False


class Capri(QObject):
    summon = Signal()
    vanish = Signal()
    mode = Signal(str, float)
    subtitle = Signal(str)
    quit_app = Signal()
    anim = Signal(str)
    roam = Signal()
    hop = Signal()
    move_to = Signal(str)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        words = sorted(cfg["wake_words"], key=len, reverse=True)
        self.wake_re = re.compile(r"(^|\s)(" + "|".join(map(re.escape, words)) + r")(?=\s|$|[,.!?])",
                                  re.IGNORECASE)
        self.ai = AI(cfg)
        self.local = LocalAI(cfg) if cfg.get("local_ai") else None
        self.actions = Actions(cfg, BASE, self.ai)
        self.actions.local = self.local
        self.speaker = Speaker(cfg)
        self.jobs = queue.Queue()
        self.awake_until = 0.0
        self.last_partial_wake = 0.0
        self.speaking = False
        self.interrupted = False
        self.speech_words = set()
        self.speech_end = 0.0
        self.last_activity = time.time()
        self.recent_chatter = []
        self.listener = None
        self.glitch_wav = os.path.join(tempfile.gettempdir(), "capri_glitch.wav")
        try:
            make_glitch_sound(self.glitch_wav)
        except Exception:
            self.glitch_wav = None

    def start(self):
        threading.Thread(target=self._worker, daemon=True).start()
        if self.local:
            threading.Thread(target=self.local.start_server, daemon=True).start()
        model =os.path.join(BASE, self.cfg["vosk_model"])
        if os.path.isdir(model):
            self.listener = Listener(model, self.on_final, self.on_partial, self.on_listener_error,
                                     device_name=self.cfg.get("mic_device") or None)
            self.listener.start()
        else:
            self.jobs.put(("say", line("no_model")))
            return
        # вступление: анимация capri + приветствие
        self.jobs.put(("say", line("greet") if self.cfg.get("greet_on_start") else "", "capri"))
        if self.cfg.get("chatter"):
            threading.Thread(target=self._chatter_loop, daemon=True).start()

    # ----- спонтанные появления -----
    def _chatter_loop(self):
        def next_delay():
            lo, hi = self.cfg["chatter_min_minutes"], self.cfg["chatter_max_minutes"]
            return random.uniform(lo, max(lo, hi)) * 60
        due = time.time() + next_delay()
        while True:
            time.sleep(15)
            now = time.time()
            if now < due:
                continue
            quiet = now - self.last_activity > 120 and self.jobs.empty() and not self.speaking
            if quiet and not fullscreen_app_active():
                self.jobs.put(("chatter",))
                due = now + next_delay()
            else:
                due = now + 60  # занят или в игре/фильме — попробуем позже

    def chatter_line(self):
        hour = time.localtime().tm_hour
        text = None
        if 0 <= hour < 5 and random.random() < 0.5:
            text = line("chatter_night")
        elif 6 <= hour < 11 and random.random() < 0.3:
            text = line("chatter_morning")
        elif self.local and random.random() < 0.4:
            text = self.local.chatter()
        for _ in range(5):
            if text and text not in self.recent_chatter:
                break
            text = line("chatter")
        self.recent_chatter = (self.recent_chatter + [text])[-6:]
        return text

    # ----- события микрофона (поток слушателя) -----
    def has_wake(self, text):
        return bool(self.wake_re.search(text.lower()))

    def strip_wake(self, text):
        t = text.lower()
        last = None
        for last in self.wake_re.finditer(t):
            pass
        if last and t[last.end():].strip(" ,.!?"):
            t = t[last.end():]  # берём то, что сказано после имени (до него могло быть эхо)
        t = self.wake_re.sub(" ", t)
        return re.sub(r"^[\s,.!?]+|[\s,.!?]+$", "", t)

    def appear(self, seconds):
        if self.glitch_wav:
            play_sound_async(self.glitch_wav)
        self.summon.emit()
        self.mode.emit("listening", float(seconds))

    # ----- перебивание -----
    def is_echo(self, text):
        """Микрофон слышит голос самой Капри: все слова фразы есть в том, что она говорит."""
        words = text.lower().replace("ё", "е").split()
        return bool(words) and all(w in self.speech_words for w in words)

    def wants_interrupt(self, text):
        t = text.lower()
        return (self.has_wake(t) or STOP_RE.search(t)) and not self.is_echo(t)

    def interrupt(self):
        if not self.speaking or self.interrupted:
            return
        self.interrupted = True
        self.speaker.stop()
        self.awake_until = time.time() + self.cfg["listen_window_seconds"]
        self.mode.emit("listening", float(self.cfg["listen_window_seconds"]))
        self.subtitle.emit(line("listen"))
        log.info("Капри перебили")

    def on_partial(self, text):
        now = time.time()
        if self.speaking:
            if self.cfg.get("barge_in") and self.wants_interrupt(text):
                self.interrupt()
            return
        if now - self.last_partial_wake > 3 and now > self.awake_until and self.has_wake(text):
            self.last_partial_wake = now
            self.appear(self.cfg["listen_window_seconds"])

    def on_final(self, text, audio):
        now = time.time()
        if self.actions.autoscroll_active() and STOP_RE.search(text.lower()) and not self.is_echo(text):
            # во время автопрокрутки «стоп» слышим и без имени
            self.actions.stop_background()
            self.subtitle.emit(line("scroll_stop"))
            return
        if self.speaking and not self.interrupted:
            if not (self.cfg.get("barge_in") and self.wants_interrupt(text)):
                return  # эхо собственной речи
            self.interrupt()
        if now - self.speech_end < 1.0 and self.is_echo(text):
            return
        woke = self.has_wake(text)
        if not woke and now > self.awake_until:
            return
        cmd = self.strip_wake(text) if woke else text
        if STOP_RE.match(cmd.strip()) and len(cmd.split()) <= 3:
            # «Капри, стоп» — замолчать, остановить автопрокрутку и слушать дальше
            self.awake_until = now + self.cfg["listen_window_seconds"]
            if self.actions.stop_background():
                self.subtitle.emit(line("scroll_stop"))
            return
        if len(cmd) < 2:
            self.awake_until = now + self.cfg["listen_window_seconds"]
            self.subtitle.emit("")
            if now - self.last_partial_wake > 3:
                self.appear(self.cfg["listen_window_seconds"])
            return
        self.awake_until = 0
        self.jobs.put(("voice", cmd, audio, woke))

    def on_listener_error(self, err):
        self.jobs.put(("say", line("no_mic")))

    # ----- кнопки -----
    # ----- микрофон -----
    def current_mic(self):
        if self.listener and self.listener.active_name:
            return self.listener.active_name
        return self.cfg.get("mic_device") or default_input_name()

    def set_mic(self, name, announce=True):
        """Сменить устройство ввода на ходу и запомнить выбор (None — как в Windows по умолчанию)."""
        self.cfg["mic_device"] = name
        save_setting("mic_device", name)
        if self.listener:
            self.listener.set_device(name)
        log.info("Выбран микрофон: %s", name or "по умолчанию")
        if announce:
            self.jobs.put(("say", line("mic_set", t=name or "микрофон Windows по умолчанию")))

    def mic_command(self, action):
        if action == "mic_info":
            return Reply(line("mic_info", t=self.current_mic()))
        devices = [n for n, _ in input_devices()]
        if len(devices) < 2:
            return Reply(line("mic_only_one", t=self.current_mic()))
        cur = self.cfg.get("mic_device") or self.current_mic()
        idx = next((i for i, n in enumerate(devices) if n == cur or cur.startswith(n) or n.startswith(cur)), -1)
        nxt = devices[(idx + 1) % len(devices)]
        self.set_mic(nxt, announce=False)
        return Reply(line("mic_set", t=nxt))

    def call_from_click(self):
        if self.speaking:
            self.interrupt()
            return
        self.awake_until = time.time() + self.cfg["listen_window_seconds"]
        self.appear(self.cfg["listen_window_seconds"])
        self.subtitle.emit(line("listen"))

    def text_command(self, text):
        self.summon.emit()
        self.jobs.put(("text", text))

    # ----- рабочий поток -----
    def _worker(self):
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass
        while True:
            job = self.jobs.get()
            try:
                self._process(job)
            except Exception:
                log.exception("Ошибка обработки %s", job[0])
                self.say(line("crash"))

    def _process(self, job):
        kind = job[0]
        if kind == "chatter":
            text = self.chatter_line()
            if random.random() < self.cfg.get("roam_chance", 0.5):
                self.roam.emit()          # гуляет по экрану, окно с текстом сверху
                time.sleep(1.5)
            else:
                self.summon.emit()
            if not self.say(text):
                self.mode.emit("idle", 0.0)
            return
        self.last_activity = time.time()
        if kind == "say":
            self.summon.emit()
            if len(job) > 2:
                self.anim.emit(job[2])
            if not job[1]:
                self.mode.emit("idle", 0.0)
                return
            if not self.say(job[1]):
                self.mode.emit("idle", 0.0)
            return
        if kind == "voice":
            _, cmd, audio, woke = job
            self.summon.emit()
            self.mode.emit("thinking", 0.0)
            self.subtitle.emit("> " + cmd)
            if self.cfg.get("use_google_stt"):
                better = google_stt(audio)
                if better:
                    better = better.lower()
                    if len(better) >= 2:
                        cmd = better
        else:
            cmd = job[1]
        if self.has_wake(cmd):
            # имя могло остаться в тексте («капри нажми …»), если Капри уже слушала без него
            stripped = self.strip_wake(cmd)
            if len(stripped) < 2:
                # просто позвали по имени — не болтаем, а слушаем
                self.awake_until = time.time() + self.cfg["listen_window_seconds"]
                self.mode.emit("listening", float(self.cfg["listen_window_seconds"]))
                self.subtitle.emit(line("listen"))
                return
            cmd = stripped
        log.info("Команда: %s", cmd)
        self.mode.emit("thinking", 0.0)
        self.subtitle.emit("> " + cmd)

        reply = self.actions.handle(cmd)
        if reply is not None and reply.action in ("mic_info", "mic_next"):
            reply = self.mic_command(reply.action)
        if reply is None:
            if self.cfg.get("enable_ai") and self.ai.available:
                reply = Reply(self.ai.ask(cmd), "answer")
            else:
                answer = self.local.ask(cmd) if self.local else None
                reply = Reply(answer, "answer") if answer else self.actions.fallback(cmd, force_search=bool(self.local))
        if reply.action == "answer" and self.cfg.get("teleport_on_answer"):
            self.hop.emit()  # отвечает, скача по экрану красной молнией
        if reply.action == "wave":
            self.anim.emit("capri")
        elif reply.action and reply.action.startswith("move:"):
            self.move_to.emit(reply.action[5:])
        elif reply.action == "roam":
            self.vanish.emit()
            time.sleep(0.8)
            self.roam.emit()
            time.sleep(1.5)
        if self.say(reply.text):
            return  # перебили — уже слушаем новую команду

        if reply.action == "quit":
            self.quit_app.emit()
        elif reply.action == "hide":
            self.vanish.emit()
        else:
            follow = float(self.cfg["followup_seconds"])
            self.awake_until = time.time() + follow
            self.mode.emit("listening", follow)

    def say(self, text):
        """Озвучивает текст. Возвращает True, если Капри перебили."""
        log.info("Капри: %s", text)
        self.subtitle.emit(text)
        self.mode.emit("speaking", 0.0)
        barge_in = self.cfg.get("barge_in") and self.listener
        if self.listener and not barge_in:
            self.listener.muted.set()
        self.speech_words = set(re.findall(r"\w+", text.lower().replace("ё", "е")))
        self.interrupted = False
        self.speaking = True
        try:
            self.speaker.say(text)
        finally:
            self.speaking = False
            self.speech_end = time.time()
            if barge_in and not self.interrupted:
                self.listener.reset_req.set()  # выбрасываем эхо её голоса
            if self.listener and not barge_in:
                time.sleep(0.25)
                self.listener.muted.clear()
        return self.interrupted


def tray_icon():
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(255, 34, 96))
    p.setPen(QPen(QColor(150, 70, 255), 4))
    p.drawEllipse(4, 4, 56, 56)
    p.setBrush(QColor(6, 24, 20))
    p.setPen(QPen(QColor(40, 255, 150), 4))
    p.drawEllipse(14, 22, 36, 20)
    p.setBrush(QColor(40, 255, 150))
    p.drawEllipse(27, 27, 10, 10)
    p.end()
    return QIcon(pm)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    cfg = load_config()

    avatar = Avatar(os.path.join(BASE, "assets"))
    avatar.hide_after = float(cfg["hide_after_seconds"])
    capri = Capri(cfg)
    capri.summon.connect(avatar.summon)
    capri.vanish.connect(avatar.vanish)
    capri.mode.connect(avatar.set_mode)
    capri.subtitle.connect(avatar.set_subtitle)
    capri.quit_app.connect(app.quit)
    capri.anim.connect(avatar.play_anim)
    capri.roam.connect(avatar.start_roam)
    capri.hop.connect(avatar.start_hopping)
    capri.move_to.connect(avatar.move_to_named)
    avatar.clicked.connect(capri.call_from_click)

    def ask_text():
        text, ok = QInputDialog.getText(None, "Капри", "Команда или вопрос:")
        if ok and text.strip():
            capri.text_command(text.strip())

    menu = QMenu()
    for title, fn in (("Позвать Капри", capri.call_from_click),
                      ("Замолчать", capri.interrupt),
                      ("Написать команду…", ask_text),
                      ("Проверить ПК", lambda: capri.text_command("проверь компьютер")),
                      ("Спрятать", avatar.vanish),
                      ("MIC", None),
                      ("Открыть config.json", lambda: os.startfile(CONFIG_PATH)),
                      (None, None),
                      ("Выход", app.quit)):
        if title is None:
            menu.addSeparator()
            continue
        if title == "MIC":
            mic_menu = menu.addMenu("Микрофон")

            def fill_mics(m=mic_menu):
                """Список устройств ввода строится при каждом открытии — чтобы видеть только что подключённые."""
                m.clear()
                chosen = capri.cfg.get("mic_device")
                options = [(None, f"По умолчанию (как в Windows: {default_input_name()})")]
                try:
                    options += [(n, n) for n, _ in input_devices()]
                except Exception:
                    log.exception("Не удалось получить список микрофонов")
                for value, label in options:
                    a = QAction(label, m)
                    a.setCheckable(True)
                    a.setChecked(value == chosen or (value is None and not chosen))
                    a.triggered.connect(lambda _=False, v=value: capri.set_mic(v))
                    m.addAction(a)
            mic_menu.aboutToShow.connect(fill_mics)
            continue
        act = QAction(title, menu)
        act.triggered.connect(fn)
        menu.addAction(act)

    tray = QSystemTrayIcon(tray_icon())
    tray.setToolTip("Капри — голосовой ассистент")
    tray.setContextMenu(menu)
    tray.activated.connect(lambda r: capri.call_from_click()
                           if r == QSystemTrayIcon.ActivationReason.Trigger else None)
    tray.show()
    avatar.menu_requested.connect(lambda pos: menu.popup(pos))

    capri.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
