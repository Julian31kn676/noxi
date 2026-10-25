"""Установка Капри: библиотеки из requirements.txt и модель распознавания речи.

    python tools/install.py

Вызывается из setup.bat. Все сообщения здесь, а не в .bat: cmd плохо читает русский текст в батниках."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import download_model  # noqa: E402

BASE = download_model.BASE


def main():
    print(f"[Capri] Python {sys.version.split()[0]}")
    if sys.version_info >= (3, 15):
        print("[Capri] Внимание: с Python 3.15 и новее голос Капри не работает, будет голос Windows.")
        print("        Поставь Python 3.13: https://www.python.org/ftp/python/3.13.17/python-3.13.17-amd64.exe")
    print("[Capri] Устанавливаю библиотеки...", flush=True)
    r = subprocess.run([sys.executable, "-m", "pip", "install", "-r", os.path.join(BASE, "requirements.txt")])
    if r.returncode:
        print()
        print("[Capri] Библиотеки не установились. Проверь интернет и что Python поставлен")
        print("        с галочкой «Add python.exe to PATH», затем запусти setup.bat ещё раз.")
        return 1
    print()
    if download_model.main():
        return 1
    print()
    print("[Capri] Готово. Запускай run.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
