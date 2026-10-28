"""Скины: имя, автор, слова вызова, обращение, цвета, картинки, характер, свои реплики и голос.

Скин — папка со skin.json и картинками. Встроенные лежат в skins/, свои — в user_skins/ (она не затирается
при обновлении). Скин из user_skins/ с тем же id, что у встроенного, заменяет его («изменённая копия»);
удалив её, получаем встроенный обратно.

Скин — это только данные, без кода: из чужого zip ничего не исполняется. Картинки чужого скина должны лежать
в его папке; выходить из неё могут только встроенные скины (они ссылаются на общую папку assets)."""
import json
import logging
import os
import re
import shutil
import zipfile

log = logging.getLogger("capri")

BASE = os.path.dirname(os.path.abspath(__file__))
BUILTIN_DIR = os.path.join(BASE, "skins")
USER_DIR = os.path.join(BASE, "user_skins")
DEFAULT_ID = "capri"
FORMAT = 1
IMAGE_EXT = (".png", ".webp", ".jpg", ".jpeg")
VOICE_KEYS = ("engine", "voice", "rate", "pitch", "fx", "shift", "lively", "silero_voice", "silero_pitch")
MAX_ZIP_FILES, MAX_ZIP_FILE, MAX_ZIP_TOTAL = 12, 15 * 1024 * 1024, 40 * 1024 * 1024
POSE_SLOTS = 3  # сколько поз спокою можно задать в окне создания скина


def _inside(folder, path):
    folder, path = os.path.normcase(os.path.abspath(folder)), os.path.normcase(os.path.abspath(path))
    return path == folder or path.startswith(folder + os.sep)


def _strings(value):
    return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []


class Skin:
    def __init__(self, folder, data, builtin=False, overrides=False):
        self.dir = folder
        self.data = data
        self.builtin = builtin      # лежит в skins/ (встроенный)
        self.overrides = overrides  # лежит в user_skins/, но заменяет встроенный с тем же id
        self.id = str(data.get("id") or (os.path.basename(folder) if folder else DEFAULT_ID))
        self.name = str(data.get("name") or self.id).strip()
        self.author = str(data.get("author") or "").strip()
        self.based_on = str(data.get("based_on") or "")
        persona = data.get("persona") if isinstance(data.get("persona"), dict) else {}
        self.persona = {k: str(persona.get(k) or "").strip() for k in ("character", "style", "lore")}
        self.persona["gender"] = "male" if persona.get("gender") == "male" else "female"
        self.address = str(data.get("address") or "").strip()
        self.colors = data.get("colors") if isinstance(data.get("colors"), dict) else {}
        lines = data.get("lines") if isinstance(data.get("lines"), dict) else {}
        self.lines = {str(k): _strings(v) for k, v in lines.items() if _strings(v)}
        voice = data.get("voice") if isinstance(data.get("voice"), dict) else {}
        self.voice = {k: voice[k] for k in VOICE_KEYS if voice.get(k) not in (None, "")}
        words = [w.lower() for w in _strings(data.get("wake_words")) if len(w) >= 2]
        self.wake_words = words or [self.name.lower()]

    # ---- картинки ----
    @property
    def trusted(self):
        """Встроенному скину можно ссылаться на файлы за пределами своей папки (общая папка assets)."""
        return self.builtin and not self.overrides

    def _path(self, rel):
        if not self.dir or not rel or not isinstance(rel, str):
            return None
        path = os.path.normpath(os.path.join(self.dir, rel))
        if not self.trusted and not _inside(self.dir, path):
            log.warning("Скин %s: путь %r выходит за папку скина, пропущен", self.id, rel)
            return None
        return path

    def _file(self, rel):
        path = self._path(rel)
        return path if path and os.path.isfile(path) and path.lower().endswith(IMAGE_EXT) else None

    def _folder(self, rel):
        path = self._path(rel)
        return path if path and os.path.isdir(path) else None

    @property
    def images(self):
        return self.data.get("images") if isinstance(self.data.get("images"), dict) else {}

    @property
    def poses(self):
        found = [self._file(r) for r in self.images.get("poses", []) if isinstance(r, str)]
        return [p for p in found if p]

    @property
    def roam(self):
        return self._file(self.images.get("roam"))

    @property
    def greeting(self):
        """Одна картинка вместо анимации приветствия."""
        return self._file(self.images.get("greeting"))

    @property
    def greeting_anim(self):
        """Папка с кадрами анимации приветствия (у встроенной Капри)."""
        return self._folder(self.images.get("greeting_anim"))

    @property
    def thinking_anim(self):
        return self._folder(self.images.get("thinking_anim"))

    @property
    def editable_images(self):
        return {"poses": self.poses, "roam": self.roam, "greeting": self.greeting}


def _read(folder):
    path = os.path.join(folder, "skin.json")
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        if os.path.exists(path):
            log.exception("Скин %s не прочитался", folder)
        return None


def _scan(root, builtin):
    out = {}
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        folder = os.path.join(root, name)
        data = _read(folder) if os.path.isdir(folder) else None
        if data is not None:
            data.setdefault("id", name)
            out[str(data["id"])] = (folder, data, builtin)
    return out


def load_all():
    """{id: Skin}: встроенные, поверх них — свои (с тем же id они заменяют встроенный)."""
    builtin, mine = _scan(BUILTIN_DIR, True), _scan(USER_DIR, False)
    result = {}
    for sid, (folder, data, _) in builtin.items():
        result[sid] = Skin(folder, data, builtin=True)
    for sid, (folder, data, _) in mine.items():
        result[sid] = Skin(folder, data, builtin=False, overrides=sid in builtin)
    if DEFAULT_ID not in result:  # папки skins/ нет — работаем со встроенным запасным скином
        result[DEFAULT_ID] = fallback()
    return result


def fallback():
    return Skin(None, {"id": DEFAULT_ID, "name": "Капри", "author": "", "address": "чумба",
                       "wake_words": ["капри", "каприз", "капре", "кепри", "капли"],
                       "colors": {"accent1": "#ff2260", "accent2": "#28ff96", "shadow": "#9646ff",
                                  "highlight": "#00f0ff"}}, builtin=True)


def get(skin_id):
    everything = load_all()
    return everything.get(skin_id) or everything[DEFAULT_ID]


def ordered(everything=None):
    """Для окна «Скины»: сначала встроенные в порядке капри → джарвис → нокси, потом свои по имени."""
    everything = everything or load_all()
    first = [everything[i] for i in ("capri", "jarvis", "noxi") if i in everything]
    rest = sorted((s for s in everything.values() if s.id not in ("capri", "jarvis", "noxi")),
                  key=lambda s: s.name.lower())
    return first + rest


# ---------------- создание, дублирование, удаление ----------------

def slug(name, taken):
    base = re.sub(r"[^\w\-]+", "_", name.strip().lower(), flags=re.UNICODE).strip("_")[:40] or "skin"
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}_{n}", n + 1
    return candidate


def user_folder(skin_id):
    return os.path.join(USER_DIR, skin_id)


def write_user_skin(skin_id, data, files):
    """Записать свой скин. files — {имя файла в папке скина: путь к исходной картинке или папке}.
    Сначала всё собирается во временной папке, потом она заменяет прежнюю — недописанного скина не бывает."""
    os.makedirs(USER_DIR, exist_ok=True)
    final = user_folder(skin_id)
    tmp = final + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    try:
        for name, src in files.items():
            dst = os.path.join(tmp, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copyfile(src, dst)
        data = dict(data, id=skin_id, format=FORMAT)
        with open(os.path.join(tmp, "skin.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        shutil.rmtree(final, ignore_errors=True)
        os.replace(tmp, final)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return get(skin_id)


def duplicate(skin, new_name, author):
    """Копия скина как свой скин: картинки (и анимации) копируются в новую папку."""
    taken = set(load_all())
    new_id = slug(new_name, taken)
    data = json.loads(json.dumps(skin.data))
    data.update(name=new_name, author=author, based_on=skin.based_on or skin.id)
    images, files = {}, {}
    for i, path in enumerate(skin.poses):
        files[f"idle{i + 1}{os.path.splitext(path)[1].lower()}"] = path
    images["poses"] = list(files)
    for key, path in (("roam", skin.roam), ("greeting", skin.greeting)):
        if path:
            name = key + os.path.splitext(path)[1].lower()
            files[name], images[key] = path, name
    for key, path in (("greeting_anim", skin.greeting_anim), ("thinking_anim", skin.thinking_anim)):
        if path:
            files[key], images[key] = path, key
    data["images"] = images
    return write_user_skin(new_id, data, files)


def delete_user_skin(skin_id):
    folder = user_folder(skin_id)
    if _inside(USER_DIR, folder) and os.path.isdir(folder):
        shutil.rmtree(folder)


# ---------------- экспорт и импорт одним zip ----------------

def export_zip(skin, path):
    """Скин → zip (skin.json + картинки). Анимации не экспортируются: в чужом скине им не доверяем."""
    data = json.loads(json.dumps(skin.data))
    images, files = {}, {}
    for i, p in enumerate(skin.poses):
        files[f"idle{i + 1}{os.path.splitext(p)[1].lower()}"] = p
    images["poses"] = list(files)
    for key, p in (("roam", skin.roam), ("greeting", skin.greeting)):
        if p:
            name = key + os.path.splitext(p)[1].lower()
            files[name], images[key] = p, name
    data["images"] = images
    data.update(id=skin.id, format=FORMAT)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("skin.json", json.dumps(data, ensure_ascii=False, indent=2))
        for name, src in files.items():
            z.write(src, name)


def inspect_zip(path):
    """Проверка zip перед установкой. Возвращает (manifest, ошибка): ровно одно из двух None."""
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            if len(infos) > MAX_ZIP_FILES:
                return None, "В архиве слишком много файлов."
            total = 0
            for info in infos:
                name = info.filename
                if name != "skin.json" and not (name.lower().endswith(IMAGE_EXT) and "/" not in name
                                                and "\\" not in name and not name.startswith(".")):
                    return None, f"В архиве лишний файл «{name}». В скине могут быть только skin.json и картинки."
                total += info.file_size
                if info.file_size > MAX_ZIP_FILE or total > MAX_ZIP_TOTAL:
                    return None, "Архив слишком большой для скина."
            if "skin.json" not in z.namelist():
                return None, "В архиве нет skin.json."
            data = json.loads(z.read("skin.json").decode("utf-8-sig"))
    except (OSError, ValueError, zipfile.BadZipFile):
        return None, "Это не похоже на архив со скином."
    if not isinstance(data, dict) or not str(data.get("name") or "").strip():
        return None, "В skin.json нет названия скина."
    return data, None


def install_zip(path):
    """Установить проверенный zip как свой скин (под новым id, чтобы не затереть существующие)."""
    data, err = inspect_zip(path)
    if err:
        raise ValueError(err)
    data = dict(data)
    taken = set(load_all())
    new_id = slug(str(data.get("id") or data["name"]), taken)
    images = data.get("images") if isinstance(data.get("images"), dict) else {}
    images = {k: v for k, v in images.items() if k in ("poses", "roam", "greeting")}  # анимации из чужих скинов не берём
    data["images"] = images
    if data.get("based_on") != "capri":  # единственное допустимое значение: скин-потомок встроенной Капри
        data.pop("based_on", None)
    data["id"] = new_id
    tmp = os.path.join(USER_DIR, new_id + ".unzip")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    try:
        with zipfile.ZipFile(path) as z:
            z.extractall(tmp)  # имена уже проверены в inspect_zip: только корень, только картинки и skin.json
        files = {n: os.path.join(tmp, n) for n in os.listdir(tmp) if n != "skin.json"}
        return write_user_skin(new_id, data, files)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
