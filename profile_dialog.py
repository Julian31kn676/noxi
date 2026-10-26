"""Окно «Как ко мне обращаться…» (меню в трее): как Капри называет пользователя и в каком роде говорит с ним."""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton,
                               QVBoxLayout)

from entries_dialog import STYLE

RADIO = "QRadioButton { color: #ffd2e1; } QRadioButton::indicator:checked { background: #ff2260; }"


class ProfileDialog(QDialog):
    def __init__(self, capri):
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.capri = capri
        self.setWindowTitle("Капри — как ко мне обращаться")
        self.setStyleSheet(STYLE + RADIO)
        cfg = capri.cfg
        win, pc = os.environ.get("USERNAME", ""), os.environ.get("COMPUTERNAME", "")

        self.names = QButtonGroup(self)
        self.custom_name = QLineEdit(cfg.get("user_name", ""))
        self.custom_name.setPlaceholderText("например: Дима")
        options = [("custom", "Своё имя:"), ("windows", f"Имя пользователя Windows — {win}"),
                   ("pc", f"Имя компьютера — {pc}"), ("none", "Не называть по имени")]
        lay = QVBoxLayout(self)
        lay.addWidget(self._title("Как меня называть"))
        self.mode_buttons = {}
        for mode, text in options:
            b = QRadioButton(text)
            self.names.addButton(b)
            self.mode_buttons[mode] = b
            if mode == "custom":
                row = QHBoxLayout()
                row.addWidget(b)
                row.addWidget(self.custom_name, 1)
                lay.addLayout(row)
            else:
                lay.addWidget(b)
        self.mode_buttons.get(cfg.get("user_name_mode", "none"), self.mode_buttons["none"]).setChecked(True)
        self.custom_name.textEdited.connect(lambda _: self.mode_buttons["custom"].setChecked(True))

        lay.addSpacing(8)
        lay.addWidget(self._title("Как ко мне обращаться"))
        self.genders = QButtonGroup(self)
        self.male = QRadioButton("В мужском роде («ты сказал», «скучал?»)")
        self.female = QRadioButton("В женском роде («ты сказала», «скучала?»)")
        for b in (self.male, self.female):
            self.genders.addButton(b)
            lay.addWidget(b)
        (self.female if cfg.get("user_gender") == "female" else self.male).setChecked(True)

        hint = QLabel("Капри иногда будет обращаться по имени и говорить в нужном роде — и в обычных фразах,\n"
                      "и в разговоре через нейросеть. Работает сразу.")
        lay.addWidget(hint)
        row = QHBoxLayout()
        row.addStretch()
        save, cancel = QPushButton("Сохранить"), QPushButton("Отмена")
        save.clicked.connect(self.save)
        cancel.clicked.connect(self.close)
        row.addWidget(save)
        row.addWidget(cancel)
        lay.addLayout(row)
        self.resize(460, 0)

    @staticmethod
    def _title(text):
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #28ff96; font-weight: bold;")
        return lbl

    def save(self):
        mode = next(m for m, b in self.mode_buttons.items() if b.isChecked())
        name = self.custom_name.text().strip()
        if mode == "custom" and not name:
            mode = "none"
        self.capri.set_profile(mode, name, "female" if self.female.isChecked() else "male")
        self.close()
