"""Измеряет общие параметры голоса в записи: высоту (F0), её разброс, темп речи, паузы.

    python tools/voice_stats.py <файл> [<файл> ...]

Это не клонирование: считаются только числа, по которым подбираются настройки синтезатора."""
import subprocess
import sys

import imageio_ffmpeg
import numpy as np

SR = 16000


def load(path):
    raw = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", path, "-f", "s16le",
                          "-ac", "1", "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


def f0_track(x, frame=0.04, hop=0.01, fmin=80, fmax=600):
    """Высота тона по кадрам (упрощённый YIN). 0 — кадр без голоса."""
    n, h = int(SR * frame), int(SR * hop)
    lag_min, lag_max = int(SR / fmax), int(SR / fmin)
    out, rms = [], []
    for i in range(0, len(x) - n - lag_max, h):
        seg = x[i:i + n + lag_max]
        e = float(np.sqrt(np.mean(seg[:n] ** 2)))
        rms.append(e)
        d = np.array([np.sum((seg[:n] - seg[lag:lag + n]) ** 2) for lag in range(lag_min, lag_max)])
        cmnd = d * np.arange(1, len(d) + 1) / np.maximum(np.cumsum(d), 1e-9)
        k = int(np.argmin(cmnd))
        out.append(SR / (k + lag_min) if cmnd[k] < 0.18 else 0.0)
    f0, rms = np.array(out), np.array(rms)
    f0[rms < max(0.01, np.percentile(rms, 30))] = 0  # тишина и фон
    return f0, rms


def stats(path):
    x = load(path)
    f0, rms = f0_track(x)
    voiced = f0[f0 > 0]
    if len(voiced) < 20:
        return {"файл": path, "ошибка": "голос не найден"}
    semis = 12 * np.log2(voiced / np.median(voiced))
    # темп: пики огибающей громкости ≈ слоги
    env = np.convolve(rms, np.ones(5) / 5, mode="same")
    thr = np.percentile(env, 55)
    peaks = [i for i in range(1, len(env) - 1) if env[i] > thr and env[i] >= env[i - 1] and env[i] > env[i + 1]]
    peaks = [p for j, p in enumerate(peaks) if j == 0 or p - peaks[j - 1] >= 8]  # не чаще 12.5 слогов/с
    speech_sec = float(np.sum(env > thr * 0.6)) * 0.01
    pauses = float(np.sum(env <= thr * 0.6)) * 0.01
    return {
        "файл": path.split("\\")[-1],
        "длина, с": round(len(x) / SR, 1),
        "высота, медиана Гц": round(float(np.median(voiced)), 1),
        "высота, 10–90% Гц": f"{np.percentile(voiced, 10):.0f}–{np.percentile(voiced, 90):.0f}",
        "живость интонации, полутонов (σ)": round(float(np.std(semis)), 2),
        "темп, слогов/с": round(len(peaks) / max(speech_sec, 0.1), 2),
        "доля пауз": round(pauses / (pauses + speech_sec), 2),
    }


if __name__ == "__main__":
    for p in sys.argv[1:]:
        for k, v in stats(p).items():
            print(f"{k}: {v}")
        print()
