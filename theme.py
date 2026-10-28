"""Цветовая тема: два основных цвета скина → вся палитра программы (аватар, окна, значок в трее).
Модуль не зависит от Qt: цвета — строки вида «#rrggbb»."""
import colorsys
import re

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in rgb)


def _hsv(h):
    return colorsys.rgb_to_hsv(*(v / 255 for v in _rgb(h)))


def _from_hsv(h, s, v):
    return _hex(tuple(c * 255 for c in colorsys.hsv_to_rgb(h % 1.0, max(0, min(1, s)), max(0, min(1, v)))))


def mix(a, b, t):
    """Смесь двух цветов: t=0 — a, t=1 — b."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(x + (y - x) * t for x, y in zip(ra, rb)))


def valid(value):
    return isinstance(value, str) and bool(HEX.match(value))


class Theme:
    """accent1 — главный цвет (контуры, молнии, эквалайзер), accent2 — второй (статус, подписи),
    shadow — тень и контур фигуры, highlight — искры; bg/panel/field/line/text — окна программы."""
    FIELDS = ("accent1", "accent2", "shadow", "highlight", "bg", "panel", "field", "line", "text")

    def __init__(self, **colors):
        for name in self.FIELDS:
            setattr(self, name, colors[name])


# цвета Капри — ровно те, что были в программе до появления скинов
CAPRI = dict(accent1="#ff2260", accent2="#28ff96", shadow="#9646ff", highlight="#00f0ff",
             bg="#0a0612", panel="#1a0a1e", field="#120818", line="#5a2a50", text="#ffd2e1")


def derive(accent1, accent2, extra=None):
    """Палитра из двух цветов. Всё, что скин задал сам (extra), берётся как есть."""
    h1, s1, _ = _hsv(accent1)
    colors = dict(
        accent1=accent1, accent2=accent2,
        shadow=mix(accent1, accent2, 0.35) if accent1 != accent2 else mix(accent1, "#6a3cff", 0.5),
        highlight=mix(accent2, "#ffffff", 0.35),
        bg=_from_hsv(h1, min(0.7, s1), 0.07),
        panel=_from_hsv(h1, min(0.65, s1), 0.12),
        field=_from_hsv(h1, min(0.6, s1), 0.09),
        line=_from_hsv(h1, min(0.45, s1), 0.30),
        text=_from_hsv(h1, 0.18, 1.0),
    )
    for k, v in (extra or {}).items():
        if k in colors and valid(v):
            colors[k] = v
    return Theme(**colors)


def from_colors(colors):
    """colors — словарь из skin.json: accent1, accent2 и, по желанию, остальные цвета палитры."""
    colors = colors or {}
    a1 = colors.get("accent1") if valid(colors.get("accent1")) else CAPRI["accent1"]
    a2 = colors.get("accent2") if valid(colors.get("accent2")) else CAPRI["accent2"]
    return derive(a1, a2, colors)


_current = Theme(**CAPRI)


def current():
    return _current


def set_current(theme):
    global _current
    _current = theme


def style():
    """Таблица стилей окон программы в цветах текущего скина."""
    t = _current
    return f"""
QDialog {{ background: {t.bg}; color: {t.text}; }}
QLabel {{ color: {t.text}; }}
QTabWidget::pane {{ border: 1px solid {t.accent1}; }}
QTabBar::tab {{ background: {t.panel}; color: {t.text}; padding: 6px 14px; border: 1px solid {t.accent1}; }}
QTabBar::tab:selected {{ background: {t.accent1}; color: {t.bg}; }}
QTreeWidget, QLineEdit, QPlainTextEdit, QListWidget {{ background: {t.field}; color: {t.text};
    border: 1px solid {t.line}; selection-background-color: {t.accent1}; selection-color: {t.bg}; }}
QHeaderView::section {{ background: {t.panel}; color: {t.accent2}; border: 0; padding: 4px; }}
QPushButton {{ background: {t.panel}; color: {t.text}; border: 1px solid {t.accent1}; padding: 5px 14px; }}
QPushButton:hover {{ background: {t.accent1}; color: {t.bg}; }}
QPushButton:disabled {{ color: {t.line}; border-color: {t.line}; }}
QRadioButton {{ color: {t.text}; }}
QRadioButton::indicator:checked {{ background: {t.accent1}; }}
"""


def title_style():
    """Заголовок раздела в окне."""
    return f"color: {_current.accent2}; font-weight: bold;"
