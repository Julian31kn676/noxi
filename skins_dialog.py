"""Окно «Скины» (меню в трее): карточки скинов, выбор, создание, изменение, копия, удаление, экспорт и импорт."""
import os

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QListView, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)

import skins
import theme

CARD_W, CARD_H = 130, 170


def card_icon(skin, active):
    """Превью скина: первая поза (или буква имени), две точки с его цветами и рамка у активного."""
    t = theme.from_colors(skin.colors)
    pix = QPixmap(CARD_W, CARD_H)
    pix.fill(QColor(t.panel))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    poses = skin.poses
    img = QImage(poses[0]) if poses else QImage()
    if not img.isNull():
        img = img.scaled(CARD_W - 12, CARD_H - 40, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
        p.drawImage((CARD_W - img.width()) // 2, CARD_H - 34 - img.height(), img)
    else:
        font = QFont("Consolas", 44)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(t.accent2))
        p.drawText(QRectF(0, 8, CARD_W, CARD_H - 44), int(Qt.AlignmentFlag.AlignCenter), skin.name[:1].upper())
    for i, color in enumerate((t.accent1, t.accent2)):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawEllipse(10 + i * 22, CARD_H - 26, 16, 16)
    p.setPen(QPen(QColor(t.accent1 if active else t.line), 3 if active else 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(1, 1, CARD_W - 2, CARD_H - 2)
    p.end()
    return QIcon(pix)


class SkinsDialog(QDialog):
    def __init__(self, capri, switch):
        """switch(skin_id, announce=True) — включить скин (делает main: аватар, цвета, голос, характер)."""
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.capri = capri
        self.switch = switch
        self.setWindowTitle("Нокси — скины")
        self.setStyleSheet(theme.style())
        self.list = QListWidget()
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setIconSize(QSize(CARD_W, CARD_H))
        self.list.setGridSize(QSize(CARD_W + 24, CARD_H + 56))
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setWordWrap(True)
        self.list.setSpacing(4)
        self.list.itemDoubleClicked.connect(lambda _: self.choose())
        self.list.currentItemChanged.connect(lambda *_: self._buttons())
        self.info = QLabel()
        self.info.setWordWrap(True)

        self.btn = {}
        row1, row2 = QHBoxLayout(), QHBoxLayout()
        for row, items in ((row1, (("choose", "Выбрать", self.choose), ("new", "+ Скин…", self.create),
                                   ("edit", "Изменить…", self.edit), ("copy", "Дублировать…", self.duplicate))),
                           (row2, (("delete", "Удалить", self.delete), ("export", "Экспорт…", self.export),
                                   ("import", "Импорт…", self.import_))) ):
            for key, title, fn in items:
                b = QPushButton(title)
                b.clicked.connect(fn)
                self.btn[key] = b
                row.addWidget(b)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.close)
        row2.addStretch()
        row2.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Скин — это облик, имя, цвета и характер. Двойной щелчок по карточке включает его."))
        lay.addWidget(self.list, 1)
        lay.addWidget(self.info)
        lay.addLayout(row1)
        lay.addLayout(row2)
        self.resize(680, 560)
        self.refresh()

    # ---------- список ----------
    def _active_id(self):
        return self.capri.cfg.get("skin", skins.DEFAULT_ID)

    def refresh(self, select=None):
        everything = skins.load_all()
        active = self._active_id() if self._active_id() in everything else skins.DEFAULT_ID
        self.list.clear()
        for skin in skins.ordered(everything):
            mark = "✓ " if skin.id == active else ""
            item = QListWidgetItem(card_icon(skin, skin.id == active),
                                   f"{mark}{skin.name}\n{('автор: ' + skin.author) if skin.author else ''}")
            item.setData(Qt.ItemDataRole.UserRole, skin.id)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            item.setToolTip(skin.name + (" (изменён)" if skin.overrides else " (встроенный)" if skin.builtin else ""))
            self.list.addItem(item)
            if skin.id == (select or active):
                self.list.setCurrentItem(item)
        self._buttons()

    def _selected(self):
        item = self.list.currentItem()
        return skins.load_all().get(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _buttons(self):
        skin = self._selected()
        self.btn["delete"].setText("Вернуть встроенный" if skin and skin.overrides else "Удалить")
        for key in ("choose", "edit", "copy", "export"):
            self.btn[key].setEnabled(skin is not None)
        self.btn["delete"].setEnabled(bool(skin) and not (skin.builtin and not skin.overrides))
        if skin:
            where = "изменённая копия встроенного" if skin.overrides else "встроенный" if skin.builtin else "свой"
            voice = "голос из config.json" if not skin.voice else "свой голос"
            self.info.setText(f"{skin.name} — {where}. Слова вызова: {', '.join(skin.wake_words[:4])}. {voice}.")
        else:
            self.info.setText("")

    # ---------- действия ----------
    def choose(self):
        skin = self._selected()
        if skin:
            self.switch(skin.id)
            self._restyle()
            self.refresh(select=skin.id)

    def _restyle(self):
        """Окно перекрашивается в цвета включённого скина."""
        self.setStyleSheet(theme.style())

    def create(self):
        from skin_wizard import SkinWizard
        wizard = SkinWizard(self, author=self.capri.cfg.get("skin_author", ""))
        if wizard.exec() and wizard.result_skin:
            self.capri.remember_author(wizard.result_skin.author)
            self.switch(wizard.result_skin.id)
            self._restyle()
            self.refresh(select=wizard.result_skin.id)

    def edit(self):
        skin = self._selected()
        if not skin:
            return
        from skin_wizard import SkinWizard
        wizard = SkinWizard(self, existing=skin, author=self.capri.cfg.get("skin_author", ""))
        if wizard.exec() and wizard.result_skin:
            self.capri.remember_author(wizard.result_skin.author)
            if wizard.result_skin.id == self._active_id():
                self.switch(wizard.result_skin.id, announce=False)  # правки активного скина видны сразу
                self._restyle()
            self.refresh(select=wizard.result_skin.id)

    def duplicate(self):
        skin = self._selected()
        if not skin:
            return
        name, ok = QInputDialog.getText(self, "Дублировать скин", "Название копии:", text=f"{skin.name} 2")
        name = name.strip()
        if not ok or not name:
            return
        if name.lower() in {s.name.lower() for s in skins.load_all().values()}:
            QMessageBox.warning(self, "Скин", "Скин с таким названием уже есть.")
            return
        author = self.capri.cfg.get("skin_author", "") or skin.author
        try:
            copy = skins.duplicate(skin, name, author)
        except OSError as e:
            QMessageBox.warning(self, "Скин", f"Не получилось скопировать: {e}")
            return
        self.refresh(select=copy.id)

    def delete(self):
        skin = self._selected()
        if not skin or (skin.builtin and not skin.overrides):
            return
        what = f"Вернуть встроенный скин «{skin.name}» (твои изменения пропадут)?" if skin.overrides \
            else f"Удалить скин «{skin.name}»? Это не отменить."
        box = QMessageBox(QMessageBox.Icon.Question, "Скин", what, parent=self)
        yes = box.addButton("Да", QMessageBox.ButtonRole.YesRole)
        box.addButton("Отмена", QMessageBox.ButtonRole.NoRole)
        box.exec()
        if box.clickedButton() is not yes:
            return
        was_active = skin.id == self._active_id()
        skins.delete_user_skin(skin.id)
        if was_active:
            # встроенный вернулся — включаем его заново; своего больше нет — возвращаем Капри
            self.switch(skin.id if skin.overrides else skins.DEFAULT_ID, announce=False)
            self._restyle()
        self.refresh()

    def export(self):
        skin = self._selected()
        if not skin:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить скин", os.path.join(os.path.expanduser("~"),
                                                                                  "Desktop", f"{skin.id}.zip"),
                                              "Архив скина (*.zip)")
        if not path:
            return
        try:
            skins.export_zip(skin, path)
        except OSError as e:
            QMessageBox.warning(self, "Скин", f"Не получилось сохранить: {e}")
            return
        QMessageBox.information(self, "Скин", "Готово. В архиве картинки, настройки, ник автора и реплики; "
                                              "анимации в архив не входят.")

    def import_(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбери архив со скином", os.path.expanduser("~"),
                                              "Архив скина (*.zip)")
        if not path:
            return
        data, err = skins.inspect_zip(path)
        if err:
            QMessageBox.warning(self, "Скин", err)
            return
        author = str(data.get("author") or "неизвестен")
        box = QMessageBox(QMessageBox.Icon.Question, "Скин",
                          f"Установить скин «{data.get('name')}»?\nАвтор: {author}\n\n"
                          "В скине только картинки и текст; он не запускает программы. Но текст характера "
                          "попадает в запрос к нейросети, а реплики Капри произносит вслух — ставь скины тех, "
                          "кому доверяешь.", parent=self)
        yes = box.addButton("Установить", QMessageBox.ButtonRole.YesRole)
        box.addButton("Отмена", QMessageBox.ButtonRole.NoRole)
        box.exec()
        if box.clickedButton() is not yes:
            return
        try:
            skin = skins.install_zip(path)
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "Скин", f"Не получилось установить: {e}")
            return
        self.refresh(select=skin.id)

    def closeEvent(self, e):
        super().closeEvent(e)
