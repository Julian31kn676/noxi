"""Установка нейросети для разговора: Ollama + подходящая модель, и сразу прописать её в config.json.

    python tools/install_ai.py

Вызывается из setup_ai.bat. Модель выбирается по видеокарте и памяти, но можно выбрать и самому."""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(BASE, "config.json")
API = "http://127.0.0.1:11434/api/tags"
# (модель, описание, проверена ли с Капри, подходит ли компьютеру: f(видеопамять NVIDIA ГБ, оперативка ГБ))
MODELS = [
    ("qwen3:14b", "самая умная, ~9 ГБ", False, lambda vram, ram: vram >= 11.5),
    ("qwen3:8b", "умная, ~5 ГБ", True, lambda vram, ram: vram >= 7.5 or ram >= 16),
    ("qwen3:4b-instruct", "лёгкая, ~2,5 ГБ, для ноутбуков и слабых ПК", True, lambda vram, ram: True),
    ("qwen3:1.7b", "самая лёгкая, ~1,4 ГБ, быстрая, но отвечает глупее", False, lambda vram, ram: vram < 7.5),
]


def recommended(vram, ram):
    """Самая умная из проверенных с Капри, которая будет отвечать быстро. qwen3:14b не советуем, пока
    не проверена, — но на мощных видеокартах она есть в списке."""
    if vram >= 7.5:
        return "qwen3:8b"
    if vram >= 3.5 or ram >= 8:
        return "qwen3:4b-instruct"
    return "qwen3:1.7b"


def suitable(vram, ram):
    """[(модель, описание)] только тех, что потянет этот компьютер."""
    out = []
    for name, desc, tested, fits in MODELS:
        if not fits(vram, ram):
            continue
        if name == "qwen3:8b" and vram < 7.5:
            desc += ", без видеокарты будет думать долго"
        if not tested:
            desc += " (с Капри не проверена)"
        out.append((name, desc))
    return out


def say(text=""):
    print(text, flush=True)


def ollama_exe():
    local = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
    return shutil.which("ollama") or (local if os.path.exists(local) else None)


def server_up():
    try:
        with urllib.request.urlopen(API, timeout=2):
            return True
    except Exception:
        return False


def install_ollama():
    say("[Capri] Ollama не найдена. Устанавливаю...")
    if shutil.which("winget"):
        r = subprocess.run(["winget", "install", "-e", "--id", "Ollama.Ollama"])
        if r.returncode == 0 and ollama_exe():
            return ollama_exe()
    say("[Capri] Автоматически не вышло. Открываю страницу Ollama — скачай и установи её,")
    say("        потом вернись в это окно и нажми Enter.")
    webbrowser.open("https://ollama.com/download")
    input()
    return ollama_exe()


def gpu_memory_gb():
    """Видеопамять NVIDIA в ГБ или 0, если такой видеокарты нет."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout
        return max(int(x) for x in out.split()) / 1024
    except Exception:
        return 0


def ram_gb():
    try:
        import psutil
        return psutil.virtual_memory().total / 2**30
    except Exception:
        return 0


def choose_model(vram=None, ram=None):
    vram = gpu_memory_gb() if vram is None else vram
    ram = ram_gb() if ram is None else ram
    say(f"[Capri] Видеокарта NVIDIA: {f'{vram:.0f} ГБ' if vram else 'нет'}, оперативная память: {ram:.0f} ГБ")
    options = suitable(vram, ram)
    best = recommended(vram, ram)
    say("[Capri] Модели, которые потянет этот компьютер:")
    for i, (name, desc) in enumerate(options, 1):
        say(f"   {i} — {name}: {desc}{'   <- советую' if name == best else ''}")
    numbers = ", ".join(str(i) for i in range(1, len(options) + 1))
    choice = input(f"Нажми Enter (будет {best}) или введи номер ({numbers}): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(options):
        return options[int(choice) - 1][0]
    return best


def save_model(name):
    """Прописать модель в config.json, не трогая остальные настройки."""
    data = {}
    if os.path.exists(CONFIG):
        try:
            with open(CONFIG, encoding="utf-8-sig") as f:
                text = f.read()
            data = json.loads(text) if text.strip() else {}
        except ValueError:
            say("[Capri] В config.json ошибка, не могу туда записать. Впиши вручную:")
            say(f'        "local_model": "{name}",')
            return False
    data["local_model"] = name
    data["local_ai"] = True
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return True


def main():
    exe = ollama_exe() or install_ollama()
    if not exe:
        say("[Capri] Ollama так и не нашлась. Установи её с https://ollama.com/download и запусти setup_ai.bat ещё раз.")
        return 1
    if not server_up():
        subprocess.Popen([exe, "serve"], creationflags=0x08000000)
        for _ in range(30):
            time.sleep(0.5)
            if server_up():
                break
    if not server_up():
        say("[Capri] Ollama не запускается. Открой её из меню «Пуск» и запусти setup_ai.bat ещё раз.")
        return 1
    model = choose_model()
    say(f"\n[Capri] Скачиваю {model}. Это несколько гигабайт, может занять время.")
    say("        Если загрузка не идёт — включи VPN и запусти setup_ai.bat ещё раз.\n")
    if subprocess.run([exe, "pull", model]).returncode != 0:
        say("\n[Capri] Модель не скачалась. Проверь интернет (или включи VPN) и запусти setup_ai.bat ещё раз.")
        return 1
    if save_model(model):
        say(f"\n[Capri] Готово! Модель {model} прописана в config.json.")
    say("[Capri] Перезапусти Капри (значок в трее -> «Выход», затем run.bat) — и можно болтать.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
