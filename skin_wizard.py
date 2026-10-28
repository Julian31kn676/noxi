"""Мастер «Новый скин» / «Изменить скин»: имя и автор → картинки → цвета → характер → готово.
Голос в мастере пока не выбирается: блок voice в skin.json остаётся пустым, и скин говорит голосом из config.json."""
import copy
import os
import shutil
import tempfile

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QButtonGroup, QColorDialog, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QStackedWidget,
                               QVBoxLayout, QWidget)

import skins
import theme

MAX_SIDE = 1400  # картинки больше этого размера уменьшаем: больше аватару всё равно не нужно
IMAGE_FILTER = "Картинки (*.png *.webp *.jpg *.jpeg);;Все файлы (*)"
STEPS = ("Имя и автор", "Картинки", "Цвета", "Характер", "Готово")


class ImageSlot(QWidget):
    """Одна картинка: превью, «Выбрать…» и «Убрать»."""

    def __init__(self, title, hint=""):
        super().__init__()
        self.path = None
        self.preview = QLabel()
        self.preview.setFixedSize(96, 128)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel(title)
        self.hint = QLabel(hint)
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("font-size: 9pt;")
        choose, clear = QPushButton("Выбрать…"), QPushButton("Убрать")
        choose.clicked.connect(self.choose)
        clear.clicked.connect(lambda: self.set_path(None))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.title, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self.preview, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(choose)
        lay.addWidget(clear)
        lay.addWidget(self.hint)
        self.set_path(None)

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбери картинку", os.path.expanduser("~"), IMAGE_FILTER)
        if path:
            self.set_path(path)

    def set_path(self, path):
        self.path = path
        pix = QPixmap(path) if path else QPixmap()
        t = theme.current()
        if pix.isNull():
            self.path = None
            self.preview.setPixmap(QPixmap())
            self.preview.setText("нет")
            self.preview.setStyleSheet(f"border: 1px dashed {t.line}; color: {t.line};")
        else:
            self.preview.setText("")
            self.preview.setPixmap(pix.scaled(94, 126, Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation))
            self.preview.setStyleSheet(f"border: 1px solid {t.accent1};")


class ColorButton(QPushButton):
    """Круглая кнопка выбора цвета."""

    def __init__(self, color, on_change):
        super().__init__()
        self.color = color
        self.on_change = on_change
        self.setFixedSize(56, 56)
        self.clicked.connect(self.pick)
        self._paint()

    def _paint(self):
        self.setStyleSheet(f"QPushButton {{ background: {self.color}; border: 3px solid #ffffff; "
                           f"border-radius: 28px; }} QPushButton:hover {{ border-color: #bbbbbb; }}")

    def pick(self):
        chosen = QColorDialog.getColor(QColor(self.color), self, "Выбери цвет")
        if chosen.isValid():
            self.color = chosen.name()
            self._paint()
            self.on_change()


class PalettePreview(QWidget):
    """Мини-окошко в цветах будущего скина: примерно так будет выглядеть панель под персонажем."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(300, 90)
        self.name = "ИМЯ"
        self.theme = theme.derive("#ff2260", "#28ff96")

    def show_colors(self, c1, c2, name):
        self.theme, self.name = theme.derive(c1, c2), name.upper() or "ИМЯ"
        self.update()

    def paintEvent(self, _):
        t = self.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(t.bg))
        w, h = self.width(), self.height()
        panel = QPolygonF([QPointF(6, 6), QPointF(w - 22, 6), QPointF(w - 6, 22), QPointF(w - 6, h - 6),
                           QPointF(22, h - 6), QPointF(6, h - 22)])
        p.setPen(QPen(QColor(t.accent1), 2))
        p.setBrush(QColor(t.panel))
        p.drawPolygon(panel)
        p.setPen(QColor(t.accent2))
        p.drawText(18, 32, f"// {self.name} :: СЛУШАЮ")
        p.setPen(QColor(t.text))
        p.drawText(18, 56, "Так выглядит текст ответа.")
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(10):
            p.setBrush(QColor(t.accent1 if i % 3 else t.highlight))
            bar = 4 + (i * 7) % 14
            p.drawRect(QRectF(w - 120 + i * 9, 40 - bar + 18, 6, bar))
        p.end()


class SkinWizard(QDialog):
    def __init__(self, parent, existing=None, author=""):
        """existing — skins.Skin, если скин изменяется (иначе создаётся новый). author — ник по умолчанию."""
        super().__init__(parent)
        self.existing = existing
        self.result_skin = None
        self.setWindowTitle("Изменить скин" if existing else "Новый скин")
        self.setStyleSheet(theme.style())
        self.step = 0
        self.names = {s.name.lower(): s.id for s in skins.load_all().values()}

        e = existing
        base_theme = theme.from_colors(e.colors) if e else theme.derive("#a855ff", "#2de2e6")
        # --- шаг 1: имя и автор
        self.name = QLineEdit(e.name if e else "")
        self.name.setPlaceholderText("например: Нова")
        self.author = QLineEdit((e.author if e and e.author else author) or "")
        self.author.setPlaceholderText("твой ник")
        page1 = QWidget()
        f1 = QFormLayout(page1)
        f1.addRow(QLabel("Как зовут персонажа и кто его автор. Ник покажется на карточке скина\n"
                         "и уйдёт вместе с ним, если ты поделишься им в архиве."))
        f1.addRow("Название:", self.name)
        f1.addRow("Автор (ник):", self.author)

        # --- шаг 2: картинки
        poses = e.poses if e else []
        self.idle = [ImageSlot(f"Поза {i + 1}", "обязательна" if i == 0 else "по желанию")
                     for i in range(skins.POSE_SLOTS)]
        for slot, path in zip(self.idle, poses):
            slot.set_path(path)
        greet_hint = "заменяет анимацию приветствия"
        if e and e.greeting_anim and not e.greeting:
            greet_hint = "сейчас у скина анимация; выбери картинку, чтобы заменить её"
        self.greeting = ImageSlot("Приветствие", greet_hint)
        self.greeting.set_path(e.greeting if e else None)
        self.roam = ImageSlot("Прогулка", "по желанию; без неё берётся поза 1")
        self.roam.set_path(e.roam if e else None)
        page2 = QWidget()
        v2 = QVBoxLayout(page2)
        v2.addWidget(QLabel("Позы покоя сменяют друг друга, пока персонаж стоит на экране. Лучше всего подходят PNG с прозрачным фоном:\n"
                            "картинки автоматически вписываются в окно персонажа."))
        row = QHBoxLayout()
        for slot in self.idle:
            row.addWidget(slot)
        v2.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(self.greeting)
        row2.addWidget(self.roam)
        row2.addStretch()
        v2.addLayout(row2)

        # --- шаг 3: цвета
        self.c1 = ColorButton(base_theme.accent1, self._colors_changed)
        self.c2 = ColorButton(base_theme.accent2, self._colors_changed)
        self.preview = PalettePreview()
        page3 = QWidget()
        v3 = QVBoxLayout(page3)
        v3.addWidget(QLabel("Два основных цвета. Из них получится вся палитра: аватар, молнии, окна и значок в трее."))
        row3 = QHBoxLayout()
        for caption, btn in (("Главный:", self.c1), ("Второй:", self.c2)):
            row3.addWidget(QLabel(caption))
            row3.addWidget(btn)
            row3.addSpacing(24)
        row3.addStretch()
        v3.addLayout(row3)
        v3.addWidget(self.preview)

        # --- шаг 4: характер
        self.address = QLineEdit(e.address if e else "")
        self.address.setPlaceholderText("например: босс, сэр, чумба — можно оставить пустым")
        self.wake = QLineEdit(", ".join(e.wake_words) if e else "")
        self.wake.setPlaceholderText("по умолчанию — название")
        self.male, self.female = QRadioButton("в мужском роде"), QRadioButton("в женском роде")
        group = QButtonGroup(self)
        for b in (self.male, self.female):
            group.addButton(b)
        (self.male if e and e.persona.get("gender") == "male" else self.female).setChecked(True)
        self.style_edit = QPlainTextEdit(e.persona.get("style", "") if e else "")
        self.style_edit.setPlaceholderText("Как персонаж говорит: например, «коротко и с иронией, иногда подкалывает, "
                                           "никогда не извиняется»")
        self.lore_edit = QPlainTextEdit(e.persona.get("lore", "") if e else "")
        self.lore_edit.setPlaceholderText("Предыстория: например, «дух старой радиолы, который скучает по эфиру»")
        page4 = QWidget()
        f4 = QFormLayout(page4)
        f4.addRow(QLabel("Это увидит нейросеть, когда ты просишь рассказать что-нибудь или поболтать."))
        f4.addRow("Обращение к тебе:", self.address)
        f4.addRow("Слова вызова:", self.wake)
        gender_row = QHBoxLayout()
        gender_row.addWidget(self.male)
        gender_row.addWidget(self.female)
        gender_row.addStretch()
        f4.addRow("Говорит о себе:", gender_row)
        f4.addRow("Стиль общения:", self.style_edit)
        f4.addRow("Лор:", self.lore_edit)

        # --- шаг 5: итог
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        page5 = QWidget()
        v5 = QVBoxLayout(page5)
        v5.addWidget(self.summary)
        v5.addStretch()

        self.stack = QStackedWidget()
        for page in (page1, page2, page3, page4, page5):
            self.stack.addWidget(page)
        self.title = QLabel()
        self.title.setStyleSheet(theme.title_style())
        self.back, self.next = QPushButton("Назад"), QPushButton("Далее")
        cancel = QPushButton("Отмена")
        self.back.clicked.connect(self.go_back)
        self.next.clicked.connect(self.go_next)
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(cancel)
        buttons.addStretch()
        buttons.addWidget(self.back)
        buttons.addWidget(self.next)
        lay = QVBoxLayout(self)
        lay.addWidget(self.title)
        lay.addWidget(self.stack, 1)
        lay.addLayout(buttons)
        self.resize(560, 520)
        self._colors_changed()
        self._show_step()

    # ---------- навигация ----------
    def _show_step(self):
        self.stack.setCurrentIndex(self.step)
        self.title.setText(f"Шаг {self.step + 1} из {len(STEPS)}: {STEPS[self.step]}")
        self.back.setEnabled(self.step > 0)
        last = self.step == len(STEPS) - 1
        self.next.setText("Сохранить" if last else "Далее")
        if last:
            self._fill_summary()
        if self.step == 3 and not self.wake.text().strip():
            self.wake.setText(self.name.text().strip().lower())

    def go_back(self):
        self.step = max(0, self.step - 1)
        self._show_step()

    def go_next(self):
        problem = self._check(self.step)
        if problem:
            QMessageBox.warning(self, "Скин", problem)
            return
        if self.step == len(STEPS) - 1:
            self._save()
            return
        self.step += 1
        self._show_step()

    def _check(self, step):
        if step == 0:
            name = self.name.text().strip()
            if not name:
                return "Напиши название скина."
            owner = self.names.get(name.lower())
            if owner and (not self.existing or owner != self.existing.id):
                return "Скин с таким названием уже есть. Придумай другое."
            if not self.author.text().strip():
                return "Напиши свой ник: он покажется на карточке скина."
        if step == 1 and not any(s.path for s in self.idle):
            return "Нужна хотя бы одна поза. Выбери картинку в первом окошке."
        if step == 3 and not self._wake_words():
            return "Напиши хотя бы одно слово вызова."
        return None

    def _colors_changed(self):
        self.preview.show_colors(self.c1.color, self.c2.color, self.name.text().strip())

    def _wake_words(self):
        words = [w.strip().lower() for w in self.wake.text().replace(";", ",").split(",")]
        return [w for w in words if len(w) >= 2] or ([self.name.text().strip().lower()]
                                                      if len(self.name.text().strip()) >= 2 else [])

    def _fill_summary(self):
        t = theme.derive(self.c1.color, self.c2.color)
        poses = sum(1 for s in self.idle if s.path)
        extra = ", есть картинка приветствия" if self.greeting.path else ""
        self.summary.setText(
            f"<p style='font-size:14pt'><b style='color:{t.accent1}'>{self.name.text().strip()}</b>"
            f" <span style='color:{t.accent2}'>— автор: {self.author.text().strip()}</span></p>"
            f"<p>Поз: {poses}{extra}.<br>Слова вызова: {', '.join(self._wake_words())}.<br>"
            f"Обращение: {self.address.text().strip() or 'нет'}.</p>"
            f"<p>Голос пока общий — тот, что в config.json. Выбор голоса для скина появится позже.</p>")

    # ---------- сохранение ----------
    def _own_image(self, path):
        """Картинка уже принадлежит редактируемому скину — копируем как есть, без пережатия."""
        e = self.existing
        return bool(e) and path in [p for p in e.poses] + [e.roam, e.greeting]

    def _prepare(self, path, base, tmp):
        """(имя файла в папке скина, путь к файлу-источнику). Новые картинки пережимаются в PNG."""
        if self._own_image(path):
            return base + os.path.splitext(path)[1].lower(), path
        img = QImage(path)
        if img.isNull():
            raise ValueError(f"Не удалось открыть картинку {os.path.basename(path)}")
        if max(img.width(), img.height()) > MAX_SIDE:
            img = img.scaled(MAX_SIDE, MAX_SIDE, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        dst = os.path.join(tmp, base + ".png")
        if not img.save(dst, "PNG"):
            raise ValueError(f"Не удалось сохранить картинку {os.path.basename(path)}")
        return base + ".png", dst

    def _save(self):
        e = self.existing
        tmp = tempfile.mkdtemp(prefix="skin_")
        try:
            files, images = {}, {}
            poses = []
            for slot in (s for s in self.idle if s.path):
                name, src = self._prepare(slot.path, f"idle{len(poses) + 1}", tmp)
                files[name], poses = src, poses + [name]
            images["poses"] = poses
            for key, slot in (("roam", self.roam), ("greeting", self.greeting)):
                if slot.path:
                    name, src = self._prepare(slot.path, key, tmp)
                    files[name], images[key] = src, name
            if e:  # анимации прежнего скина сохраняем; свою картинку приветствия ставим вместо анимации
                if e.thinking_anim:
                    files["thinking_anim"], images["thinking_anim"] = e.thinking_anim, "thinking_anim"
                if e.greeting_anim and "greeting" not in images:
                    files["greeting_anim"], images["greeting_anim"] = e.greeting_anim, "greeting_anim"

            data = copy.deepcopy(e.data) if e else {}
            c1, c2 = self.c1.color, self.c2.color
            same = bool(e) and e.colors.get("accent1", "").lower() == c1 and e.colors.get("accent2", "").lower() == c2
            style, lore = self.style_edit.toPlainText().strip(), self.lore_edit.toPlainText().strip()
            persona = {"style": style, "lore": lore,
                       "gender": "male" if self.male.isChecked() else "female"}
            if e and e.persona.get("character") and (style, lore) == (e.persona.get("style", ""),
                                                                       e.persona.get("lore", "")):
                persona["character"] = e.persona["character"]  # свой полный текст характера, если его не меняли
            data.update(name=self.name.text().strip(), author=self.author.text().strip(),
                        wake_words=self._wake_words(), address=self.address.text().strip(),
                        colors=dict(e.colors) if same else {"accent1": c1, "accent2": c2},
                        images=images, persona=persona)
            data.setdefault("voice", {})
            taken = set(skins.load_all())
            skin_id = e.id if e else skins.slug(data["name"], taken)
            self.result_skin = skins.write_user_skin(skin_id, data, files)
        except Exception as err:
            QMessageBox.warning(self, "Скин", f"Не получилось сохранить скин: {err}")
            return
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.accept()
