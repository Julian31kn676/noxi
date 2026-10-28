"""Окно «Звук Капри» (меню в трее): громкость её голоса, громкость и чувствительность микрофона для неё.
Общие настройки звука Windows не меняются."""
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

import theme
from theme import style, title_style
from voice import GATE_MAX

DIM = QColor(90, 60, 90)


class LevelMeter(QWidget):
    """Полоска громкости с микрофона и отметка порога: что левее отметки — Капри считает тишиной."""

    def __init__(self):
        super().__init__()
        self.level = 0.0
        self.gate = 0.0
        self.setMinimumHeight(22)

    def paintEvent(self, _):
        t = theme.current()
        pink, green = QColor(t.accent1), QColor(t.accent2)
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.fillRect(r, QColor(t.field))
        w = r.width() * min(1.0, self.level)
        p.fillRect(QRectF(r.left(), r.top(), w, r.height()), green if self.level >= self.gate else DIM)
        x = r.left() + r.width() * self.gate
        p.fillRect(QRectF(x - 1, r.top(), 3, r.height()), pink)
        p.setPen(pink)
        p.drawRect(r)
        p.end()


def _slider(lo, hi, value):
    s = QSlider(Qt.Orientation.Horizontal)
    s.setRange(lo, hi)
    s.setValue(value)
    return s


class SoundDialog(QDialog):
    def __init__(self, capri):
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.capri = capri
        self.setWindowTitle("Капри — звук")
        t = theme.current()
        self.setStyleSheet(style() + f"QSlider::groove:horizontal {{ height: 6px; background: {t.line}; }}"
                                     f"QSlider::handle:horizontal {{ width: 14px; margin: -5px 0; background: {t.accent1}; }}"
                                     f"QSlider::sub-page:horizontal {{ background: {t.accent1}; }}")
        cfg = capri.cfg
        self.volume = _slider(0, 100, int(cfg.get("voice_volume", 100)))
        self.fx = _slider(0, 250, int(float(cfg.get("voice_fx", 1.8)) * 100))
        self.gain = _slider(50, 400, int(float(cfg.get("mic_gain", 1.0)) * 100))
        self.sens = _slider(0, 100, int(cfg.get("mic_sensitivity", 100)))
        self.vol_label, self.gain_label, self.sens_label, self.fx_label = QLabel(), QLabel(), QLabel(), QLabel()
        self.meter = LevelMeter()
        test = QPushButton("Проверить голос")
        test.clicked.connect(lambda: capri.jobs.put(("say", "Проверка громкости. Так меня хорошо слышно?")))
        close = QPushButton("Закрыть")
        close.clicked.connect(self.close)

        lay = QVBoxLayout(self)
        lay.addWidget(self._title("Голос Капри"))
        lay.addLayout(self._row("Громкость:", self.volume, self.vol_label))
        lay.addLayout(self._row("Эффекты:", self.fx, self.fx_label))
        lay.addWidget(test, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addSpacing(10)
        lay.addWidget(self._title("Микрофон для Капри — " + (capri.current_mic() or "по умолчанию")))
        lay.addLayout(self._row("Громкость:", self.gain, self.gain_label))
        lay.addLayout(self._row("Чувствительность:", self.sens, self.sens_label))
        lay.addWidget(self.meter)
        hint = QLabel("Эффекты: 0 — чистый голос, ×1.8 — как задумано. Нажми «Проверить голос», чтобы послушать.\n"
                      "Скажи что-нибудь: полоска должна заходить за розовую отметку и становиться зелёной.\n"
                      "Не слышит — прибавь громкость. Реагирует на шум — убавь чувствительность.\n"
                      "Общие настройки звука Windows не меняются.")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        self.resize(520, 0)

        # сразу применяем, в config.json пишем, когда отпустили ползунок
        self.volume.valueChanged.connect(self._labels)
        self.fx.valueChanged.connect(self._labels)
        self.fx.sliderReleased.connect(lambda: capri.set_voice_fx(self.fx.value() / 100))
        self.fx.valueChanged.connect(lambda v: None if self.fx.isSliderDown() else capri.set_voice_fx(v / 100))
        self.gain.valueChanged.connect(lambda v: self._live(gain=v / 100))
        self.sens.valueChanged.connect(lambda v: self._live(sensitivity=v))
        self.volume.sliderReleased.connect(lambda: capri.set_voice_volume(self.volume.value()))
        self.volume.valueChanged.connect(lambda v: None if self.volume.isSliderDown() else capri.set_voice_volume(v))
        self.gain.sliderReleased.connect(lambda: capri.set_mic_tuning(gain=self.gain.value() / 100))
        self.sens.sliderReleased.connect(lambda: capri.set_mic_tuning(sensitivity=self.sens.value()))
        for s, key in ((self.gain, "gain"), (self.sens, "sensitivity")):  # стрелки и колёсико мыши
            s.valueChanged.connect(lambda v, s=s, key=key: None if s.isSliderDown() else
                                   capri.set_mic_tuning(**{key: v / 100 if key == "gain" else v}))
        self._labels()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(50)

    @staticmethod
    def _title(text):
        lbl = QLabel(text)
        lbl.setStyleSheet(title_style())
        return lbl

    @staticmethod
    def _row(caption, slider, value_label):
        row = QHBoxLayout()
        cap = QLabel(caption)
        cap.setMinimumWidth(130)
        value_label.setMinimumWidth(50)
        row.addWidget(cap)
        row.addWidget(slider, 1)
        row.addWidget(value_label)
        return row

    def _live(self, gain=None, sensitivity=None):
        """Пока тянут ползунок — меняем на лету, без записи в файл."""
        lst = self.capri.listener
        if lst:
            if gain is not None:
                lst.gain = gain
            if sensitivity is not None:
                lst.sensitivity = sensitivity
        self._labels()

    def _labels(self):
        self.vol_label.setText(f"{self.volume.value()}%")
        fx = self.fx.value() / 100
        self.fx_label.setText("нет" if fx == 0 else f"×{fx:.1f}")
        self.gain_label.setText(f"×{self.gain.value() / 100:.1f}")
        self.sens_label.setText(f"{self.sens.value()}%")

    def _tick(self):
        lst = self.capri.listener
        self.meter.level = lst.level if lst else 0.0
        self.meter.gate = (100 - self.sens.value()) / 100 * GATE_MAX
        self.meter.update()

    def closeEvent(self, e):
        self.timer.stop()
        super().closeEvent(e)
