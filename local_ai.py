"""Ответы на вопросы через локальную нейросеть (Ollama) — без ключа и интернета."""
import datetime
import difflib
import json
import logging
import os
import random
import re
import subprocess
import urllib.request

from persona import CHARACTER, SPEECH_RULES

log = logging.getLogger("capri")
URL = "http://127.0.0.1:11434"
NO_WINDOW = 0x08000000
SEARCH_MARK = "ПОИСК"

SYSTEM = f"""{CHARACTER}

{SPEECH_RULES}
Отвечай на любые вопросы о науке, истории, технике, языке, о себе, советы и просьбы рассказать что-то.
Только если вопрос про текущие события (погода сейчас, свежие новости, курсы валют, цены,
результаты недавних матчей), ответь ровно одним словом: {SEARCH_MARK}"""

FRESH = re.compile(r"погод|новост|курс (доллар|евро|рубл|валют|биткоин)|сколько стоит|цена|цены|"
                   r"счет матча|кто выиграл|расписани|пробк|сегодня в мире")


FOREIGN = re.compile(r"[　-鿿가-힯＀-￯]+")


THIRD_PERSON = re.compile(r"(одн(а|ой|у|у) прекрасн(ая|ой|ую) (я|мне|меня|мной))", re.IGNORECASE)


def drop_third_person(answer):
    """Страховка поверх промпта: Капри не говорит о себе в третьем лице. Такие предложения
    выкидываем целиком (чтобы не ломать согласование глаголов), а если других нет — меняем на «я»."""
    sentences = re.split(r"(?<=[.!?…])\s+", answer)
    clean = [s for s in sentences if not THIRD_PERSON.search(s)]
    if clean:
        return " ".join(clean)
    return THIRD_PERSON.sub("я", answer)


CHATTER_TOPICS = [
    "пожалуйся, что тебе скучно", "подразни пользователя за то, что он долго сидит за компьютером",
    "пошути про то, как тесно жить в компьютере", "сделай комплимент с подколкой",
    "пошути про его рабочий стол или файлы", "скажи что-нибудь загадочное и чуть жутковатое",
    "напомни отдохнуть, но в своём стиле", "похвастайся, что ты быстрее его процессора",
    "вспомни о небе и о том, что хочешь собственное тело",
]


SELF_TALK = re.compile(r"\bя\s*[—–-]?\s*капри\b|меня зовут капри|\bкапри (здесь|тут|на связи)|^капри\b|"
                       r"\bне (просто |какой-то |обычный |обычная )?(бот|ии|программ\w*|голос в)|"
                       r"сильнее (любого |обычного )?(бот|ии)|(называ|зови|счита)\w* меня (просто )?(бот|ии)|"
                       r"каприкорн", re.IGNORECASE)
ASKED_SELF = re.compile(r"кто ты|как тебя зовут|тво[её] имя|\bии\b|бот|программ|нейросет|о себе|про себя|"
                        r"ты кто|кто такая")


def naturalize(answer, question, recent):
    """Страховка поверх промпта — чтобы Капри звучала как собеседница, а не как персонаж,
    зацикленный на своих чертах: без самопредставлений и «я не бот» без повода, без «чумба» в каждой фразе."""
    parts = [p for p in re.split(r"(?<=[.!?…])\s+", answer) if p.strip()]
    if not ASKED_SELF.search(question.lower()):
        parts = [p for p in parts if not SELF_TALK.search(p)] or parts
    parts = [p for p in parts if not re.fullmatch(r"\W*чумба\W*", p.lower())] or parts
    text = " ".join(parts)
    # «чумба» — не чаще раза на несколько ответов
    allow = not any("чумба" in r.lower() for r in recent[-3:])
    used = []

    def drop(m):
        if allow and not used:
            used.append(1)
            return m.group(0)
        return "," if m.group(1) and m.group(2) else ""
    text = re.sub(r"(,\s*)?\bчумба\b(\s*,)?", drop, text, flags=re.IGNORECASE)
    text = re.sub(r"\s+([,.!?…])", r"\1", text)
    text = re.sub(r"(^|[.!?…]\s+)[,\s]+", r"\1", text)
    text = re.sub(r"(^|[.!?…]\s+)(\w)", lambda m: m.group(1) + m.group(2).upper(), text)
    return text.strip() or answer


def _key(sentence):
    return re.sub(r"[^\w ]", "", sentence.lower().replace("ё", "е")).strip()


def drop_repeats(answer, history):
    """Маленькая модель залипает на своих же фразах из истории («Вздыхаю…», «Иди, проверяй…»):
    выкидываем предложения, которые уже звучали (или почти так же) в прошлых ответах."""
    previous = [_key(s) for m in history if m["role"] == "assistant"
                for s in re.split(r"(?<=[.!?…])\s+", m["content"])]
    previous = [p for p in previous if len(p) >= 8]
    kept = []
    for s in re.split(r"(?<=[.!?…])\s+", answer):
        k = _key(s)
        if re.match(r"(вздыха|вздох)", k):
            continue
        if len(k) >= 8 and any(k == p or difflib.SequenceMatcher(None, k, p).ratio() > 0.8 for p in previous):
            continue
        kept.append(s)
    return " ".join(kept) or answer


def _post(path, payload, timeout):
    req = urllib.request.Request(URL + path, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class LocalAI:
    def __init__(self, cfg):
        self.model = cfg.get("local_model", "qwen3:8b")
        self.history = []

    def running(self):
        try:
            with urllib.request.urlopen(URL + "/api/tags", timeout=1.5) as r:
                names = [m["name"] for m in json.loads(r.read().decode("utf-8")).get("models", [])]
            return any(n == self.model or n.startswith(self.model + ":") for n in names)
        except Exception:
            return False

    def start_server(self):
        """Запускает Ollama, если она не запущена, и заранее грузит модель в память."""
        if not self.running():
            exe = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
            try:
                subprocess.Popen([exe if os.path.exists(exe) else "ollama", "serve"],
                                 creationflags=NO_WINDOW)
            except OSError:
                log.info("Ollama не установлена")
                return
        try:
            _post("/api/generate", {"model": self.model, "prompt": "", "keep_alive": "10m"}, 120)
            log.info("Локальная модель %s загружена", self.model)
        except Exception as e:
            log.info("Не удалось прогреть модель: %s", e)

    def _chat(self, messages, max_tokens=300):
        resp = _post("/api/chat", {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,  # Qwen3 по умолчанию «рассуждает» вслух — для голоса это лишняя задержка
            "keep_alive": "10m",
            "options": {"num_predict": max_tokens, "temperature": 0.6, "repeat_penalty": 1.15},
        }, 120)
        text = resp.get("message", {}).get("content", "")
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()

    def ask(self, question):
        """Текст ответа или None, если лучше открыть поиск."""
        if FRESH.search(question.lower()):
            return None
        now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        self.history.append({"role": "user", "content": question})
        self.history = self.history[-6:]
        messages = [{"role": "system", "content": SYSTEM + f"\nСейчас {now}."}] + self.history
        try:
            answer = self._chat(messages)
            if FOREIGN.search(answer):  # Qwen иногда срывается на китайский — пробуем ещё раз
                answer = self._chat(messages + [{"role": "system", "content":
                                    "Ответь заново, строго только русскими буквами, без иероглифов."}])
            answer = re.sub(r"\s+", " ", FOREIGN.sub("", answer)).strip()
        except Exception as e:
            log.info("Локальная модель недоступна: %s", e)
            self.history.pop()
            return None
        recent = [m["content"] for m in self.history if m["role"] == "assistant"]
        answer = naturalize(drop_repeats(drop_third_person(answer), self.history), question, recent)
        answer = re.sub(r"\s*\([^)]*\)", "", answer)                      # ремарки в скобках
        answer = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", answer)  # эмодзи
        answer = re.sub(r"\s+", " ", answer).strip()
        answer = answer[:1].upper() + answer[1:]
        broken = len(answer) < 40 and not re.search(r"[.!?…]$", answer)
        if not answer or broken or SEARCH_MARK in answer.upper()[:20]:
            self.history.pop()
            return None
        self.history.append({"role": "assistant", "content": answer})
        return answer

    def chatter(self):
        """Короткая спонтанная реплика, когда Капри появляется сама. None — если модель недоступна."""
        try:
            text = self._chat([
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content":
                 "Ты сама решила ненадолго появиться на экране. Скажи одну короткую спонтанную фразу, "
                 f"до пятнадцати слов. Тема: {random.choice(CHATTER_TOPICS)}. "
                 "Не спрашивай, чем помочь, и не упоминай команды."},
            ], max_tokens=60)
        except Exception:
            return None
        text = drop_third_person(re.sub(r"\s+", " ", FOREIGN.sub("", text)).strip().strip('"«»'))
        text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", text).strip()
        return text if 5 < len(text) < 160 and re.search(r"[.!?…]$", text) else None

    def summarize_report(self, report):
        try:
            return self._chat([
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content":
                 "Вот отчёт диагностики моего ПК. Скажи 2–4 предложения: общее состояние, главные "
                 "проблемы и что сделать. Безвредные ошибки вроде DistributedCOM не раздувай.\n\n"
                 + report[:12000]},
            ], max_tokens=400) or None
        except Exception:
            return None
