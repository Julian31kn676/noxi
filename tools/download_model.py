"""Ставит офлайн-модель распознавания речи Vosk в папку models/.

    python tools/download_model.py

Вызывается из setup.bat. Модель лежит в самом архиве Капри (bundled/), поэтому интернет и VPN не нужны.
Если архива модели нет — скачивает её с сайта разработчиков. Повторный запуск ничего не делает,
если модель уже на месте."""
import os
import shutil
import sys
import urllib.request
import zipfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "vosk-model-small-ru-0.22"
URL = f"https://alphacephei.com/vosk/models/{NAME}.zip"
BUNDLED = os.path.join(BASE, "bundled", NAME + ".zip")  # копия модели в репозитории (лицензия Apache 2.0)
MODELS = os.path.join(BASE, "models")
TARGET = os.path.join(MODELS, NAME)


def ready():
    return os.path.isfile(os.path.join(TARGET, "am", "final.mdl"))


def download(path):
    with urllib.request.urlopen(URL, timeout=60) as r, open(path, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 16):
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done / 2**20:.0f} / {total / 2**20:.0f} МБ", end="", flush=True)
    print()
    if total and done < total:
        raise IOError("загрузка оборвалась")


def unpack(archive):
    shutil.rmtree(TARGET, ignore_errors=True)
    with zipfile.ZipFile(archive) as z:
        z.extractall(MODELS)


def main():
    if ready():
        print("[Capri] Модель распознавания речи уже установлена.")
        return 0
    os.makedirs(MODELS, exist_ok=True)
    if os.path.isfile(BUNDLED):
        print("[Capri] Распаковываю модель распознавания речи...")
        try:
            unpack(BUNDLED)
        except (OSError, zipfile.BadZipFile) as e:
            print(f"  не получилось ({e}), попробую скачать")
    if not ready():
        tmp = os.path.join(MODELS, "ru.zip")
        print("[Capri] Скачиваю модель распознавания речи (~45 МБ)...")
        for attempt in range(3):
            try:
                download(tmp)
                break
            except Exception as e:
                print(f"  не получилось ({e}), попытка {attempt + 2} из 3..." if attempt < 2 else f"  ошибка: {e}")
        else:
            print("[Capri] Не удалось скачать модель. Скачай Капри с GitHub заново (модель лежит в архиве,")
            print("        в папке bundled) или включи VPN и запусти setup.bat ещё раз.")
            return 1
        unpack(tmp)
        os.remove(tmp)
    if not ready():
        print("[Capri] Архив распаковался, но модели в нём нет. Скачай Капри с GitHub заново.")
        return 1
    print("[Capri] Модель установлена.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
