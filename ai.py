"""Ответы на вопросы через Claude (с веб-поиском для свежих фактов)."""
import datetime
import logging
import os

from persona import CHARACTER, SPEECH_RULES, user_context

log = logging.getLogger("capri")

SYSTEM = f"""{CHARACTER}

{SPEECH_RULES}
Для свежих фактов (погода, новости, курсы, расписания) используй веб-поиск.
Командами ПК (открыть сайт/приложение, громкость, яркость, диагностика) занимается отдельный модуль;
если просят то, чего ты сделать не можешь, скажи, какую команду произнести, например «Капри, открой ютуб»."""


class AI:
    def __init__(self, cfg):
        self.model = cfg.get("model", "claude-opus-5-5")
        self.history = []
        self.client = None
        key = cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")
        if key:
            import anthropic
            self.client = anthropic.Anthropic(api_key=key, timeout=60, max_retries=2)

    @property
    def available(self):
        return self.client is not None

    def _call(self, system, messages, tools):
        """Запрос с серверным фолбэком при отказе и продолжением при pause_turn."""
        msgs = list(messages)
        extra = {"tools": tools} if tools else {}
        for _ in range(4):
            resp = self.client.beta.messages.create(
                model=self.model,
                max_tokens=2000,
                system=system,
                messages=msgs,
                **extra,
                output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"],
                extra_body={"fallbacks": "default"},
            )
            if resp.stop_reason == "pause_turn":
                msgs.append({"role": "assistant", "content": resp.content})
                continue
            if resp.stop_reason == "refusal":
                return "На это я ответить не могу."
            text = " ".join(b.text for b in resp.content if b.type == "text").strip()
            return text or "Хм, пустой ответ. Спроси ещё раз."
        return "Поиск затянулся, попробуй переформулировать."

    def ask(self, question):
        if not self.available:
            return ("Чтобы я отвечала на вопросы, впиши ключ Anthropic API в config.json, "
                    "в поле anthropic_api_key.")
        import anthropic
        now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        self.history.append({"role": "user", "content": f"[{now}] {question}"})
        self.history = self.history[-12:]
        while self.history and self.history[0]["role"] != "user":
            self.history.pop(0)
        try:
            answer = self._call(SYSTEM + "\n" + user_context(), self.history,
                                [{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}])
        except anthropic.AuthenticationError:
            self.history.pop()
            return "Ключ API не подходит. Проверь anthropic_api_key в config.json."
        except anthropic.RateLimitError:
            self.history.pop()
            return "Слишком много запросов, подожди немного."
        except anthropic.APIConnectionError:
            self.history.pop()
            return "Нет связи с сервером. Проверь интернет."
        except anthropic.APIStatusError as e:
            self.history.pop()
            log.error("API error %s: %s", e.status_code, e.message)
            return "Сервер вернул ошибку, попробуй позже."
        self.history.append({"role": "assistant", "content": answer})
        return answer

    def summarize_report(self, report):
        if not self.available:
            return None
        try:
            return self._call(
                SYSTEM + "\n" + user_context(),
                [{"role": "user", "content":
                  "Вот отчёт диагностики моего ПК. Скажи голосом 2–4 предложения: общее состояние, "
                  "главные проблемы и что конкретно сделать. Ошибки, которые обычно безвредны "
                  "(например, DistributedCOM), не раздувай.\n\n" + report[:30000]}],
                [],
            )
        except Exception:
            log.exception("summarize_report")
            return None
