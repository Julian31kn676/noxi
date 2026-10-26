"""Окно «Мои сайты и программы» (меню в трее): список, добавление и удаление без правки config.json руками."""
import os
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QTabWidget, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout)

STYLE = """
QDialog { background: #0a0612; color: #ffd2e1; }
QLabel { color: #ffd2e1; }
QTabWidget::pane { border: 1px solid #ff2260; }
QTabBar::tab { background: #1a0a1e; color: #ffd2e1; padding: 6px 14px; border: 1px solid #ff2260; }
QTabBar::tab:selected { background: #ff2260; color: #0a0612; }
QTreeWidget, QLineEdit { background: #120818; color: #ffd2e1; border: 1px solid #5a2a50;
                         selection-background-color: #ff2260; selection-color: #0a0612; }
QHeaderView::section { background: #1a0a1e; color: #28ff96; border: 0; padding: 4px; }
QPushButton { background: #1a0a1e; color: #ffd2e1; border: 1px solid #ff2260; padding: 5px 14px; }
QPushButton:hover { background: #ff2260; color: #0a0612; }
"""
URL_RE = re.compile(r"^(https?://)?[\w\-]+(\.[\w\-]+)*\.[a-zа-я]{2,}(:\d+)?(/\S*)?$", re.IGNORECASE)


def _clipboard_url():
    text = (QGuiApplication.clipboard().text() or "").strip()
    return text if URL_RE.match(text) else ""


class SiteForm(QDialog):
    """Название + адрес сайта. Адрес подставляется из буфера обмена, если там ссылка."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Новый сайт")
        self.setStyleSheet(STYLE)
        self.name = QLineEdit()
        self.name.setPlaceholderText("например: музыка")
        self.url = QLineEdit(_clipboard_url())
        self.url.setPlaceholderText("например: https://music.yandex.ru")
        form = QFormLayout(self)
        form.addRow(QLabel("Скопируй адрес сайта из браузера и придумай, как будешь его называть."))
        form.addRow("Название:", self.name)
        form.addRow("Адрес:", self.url)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self._check)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.resize(460, 0)

    def _check(self):
        url = self.url.text().strip()
        if not self.name.text().strip():
            QMessageBox.warning(self, "Капри", "Напиши название — то, что скажешь после «открой».")
        elif not URL_RE.match(url):
            QMessageBox.warning(self, "Капри", "Это не похоже на адрес сайта. Скопируй его из адресной строки браузера.")
        else:
            self.accept()

    def values(self):
        url = self.url.text().strip()
        return self.name.text().strip(), url if url.startswith("http") else "https://" + url


class ReplyForm(QDialog):
    """Своя фраза и ответ Капри на неё."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Новый ответ")
        self.setStyleSheet(STYLE)
        self.phrase = QLineEdit()
        self.phrase.setPlaceholderText("например: твой голос это проблема")
        self.answer = QLineEdit()
        self.answer.setPlaceholderText("например: Ну и иди ты.")
        form = QFormLayout(self)
        form.addRow(QLabel("Что ты говоришь Капри (после её имени) и что она ответит."))
        form.addRow("Фраза:", self.phrase)
        form.addRow("Ответ:", self.answer)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self._check)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.resize(460, 0)

    def _check(self):
        if not self.phrase.text().strip() or not self.answer.text().strip():
            QMessageBox.warning(self, "Капри", "Заполни и фразу, и ответ.")
        else:
            self.accept()

    def values(self):
        return self.phrase.text().strip(), self.answer.text().strip()


class EntriesDialog(QDialog):
    def __init__(self, actions):
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.actions = actions
        self.setWindowTitle("Капри — мои сайты, программы и ответы")
        self.setStyleSheet(STYLE)
        self.tabs = QTabWidget()
        self.trees = {}
        for section, title, first, column in (("sites", "Сайты", "Название", "Адрес"),
                                              ("apps", "Программы", "Название", "Что открывает"),
                                              ("replies", "Ответы", "Фраза", "Ответ Капри")):
            tree = QTreeWidget()
            tree.setHeaderLabels([first, column])
            tree.setRootIsDecorated(False)
            tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            self.trees[section] = tree
            self.tabs.addTab(tree, title)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.tabs.currentChanged.connect(self._update_hint)
        self._update_hint()
        hint = self.hint
        add, remove, close = QPushButton("Добавить…"), QPushButton("Удалить"), QPushButton("Закрыть")
        add.clicked.connect(self.add)
        remove.clicked.connect(self.remove)
        close.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch()
        row.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addWidget(hint)
        lay.addWidget(self.tabs)
        lay.addLayout(row)
        self.resize(640, 520)
        self.refresh()

    def _book(self, section):
        return {"sites": self.actions.sites, "apps": self.actions.apps, "replies": self.actions.replies}[section]

    def refresh(self):
        for section, tree in self.trees.items():
            book = self._book(section)
            tree.clear()
            for name in sorted(book):
                tree.addTopLevelItem(QTreeWidgetItem([name, str(book[name])]))

    def _section(self):
        return ("sites", "apps", "replies")[self.tabs.currentIndex()]

    def _update_hint(self, *_):
        self.hint.setText(
            "Фраза — что ты говоришь Капри (можно чуть иначе), ответ — что она скажет в ответ. Работает сразу.\n"
            "Голосом: «Капри, когда я скажу „как дела“, отвечай „лучше всех“»."
            if self._section() == "replies" else
            "Название — то, что говоришь после «Капри, открой …». Изменения работают сразу.")

    def _save(self, section, name, target):
        err = self.actions.remember(section, name, target)
        if err:
            QMessageBox.warning(self, "Капри", "Не получилось записать: " + err)
            return False
        self.refresh()
        return True

    def add(self):
        if self._section() == "replies":
            form = ReplyForm(self)
            if form.exec():
                self._save("replies", *form.values())
            return
        if self._section() == "sites":
            form = SiteForm(self)
            if form.exec():
                self._save("sites", *form.values())
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбери программу или её ярлык", os.path.join(os.path.expanduser("~"), "Desktop"),
            "Программы и ярлыки (*.exe *.lnk *.url *.bat *.cmd);;Все файлы (*)")
        if not path:
            return
        guess = os.path.splitext(os.path.basename(path))[0].lower()
        name, ok = _ask_name(self, guess)
        if ok and name:
            self._save("apps", name, os.path.normpath(path))

    def remove(self):
        tree = self.trees[self._section()]
        item = tree.currentItem()
        if not item:
            QMessageBox.information(self, "Капри", "Сначала выбери строку в списке.")
            return
        name = item.text(0)
        box = QMessageBox(QMessageBox.Icon.Question, "Капри", f"Забыть «{name}»?", parent=self)
        yes = box.addButton("Забыть", QMessageBox.ButtonRole.YesRole)
        box.addButton("Отмена", QMessageBox.ButtonRole.NoRole)
        box.exec()
        if box.clickedButton() is yes:
            self._save(self._section(), name, None)


def _ask_name(parent, guess):
    from PySide6.QtWidgets import QInputDialog
    name, ok = QInputDialog.getText(parent, "Название",
                                    "Как ты будешь её называть? (то, что скажешь после «открой»)", text=guess)
    return name.strip(), ok
