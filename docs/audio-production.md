# Блок 7 — Продакшн звукового контента

> Версия 1.0 — 26.06.2026

---

## Структура каждого трека

Каждая сессия Audium — это два слоя наложенных друг на друга:

```
┌─────────────────────────────────────┐
│  Ambient-слой (настроение)          │  громкость ~60-70%
│  Suno / лицензированная музыка      │
├─────────────────────────────────────┤
│  DSP-слой (механизм)                │  громкость ~30-40%
│  Точные частоты, синтез Python      │
└─────────────────────────────────────┘
         = готовый трек .mp3
```

Ambient-слой делает прослушивание приятным. DSP-слой — это то, что реально работает.

---

## DSP-синтез — генерируем сами на Python

Не нужны DAW и звукорежиссёр для частотного слоя. Всё генерируется скриптом.

### Бинауральные биты

```python
# audium/tools/generate_binaural.py
import numpy as np
import soundfile as sf

def generate_binaural(
    carrier_hz: float,      # несущая частота (200-400 Гц — комфортна для слуха)
    beat_hz: float,         # целевая частота (разница между ушами)
    duration_min: int,
    output_path: str,
    sample_rate: int = 44100,
    amplitude: float = 0.35
):
    """
    Левый канал: carrier_hz
    Правый канал: carrier_hz + beat_hz
    Мозг слышит разницу = beat_hz
    
    Требует стерео-наушников.
    """
    t = np.linspace(0, duration_min * 60, sample_rate * duration_min * 60)
    left  = amplitude * np.sin(2 * np.pi * carrier_hz * t)
    right = amplitude * np.sin(2 * np.pi * (carrier_hz + beat_hz) * t)

    # Fade in/out 30 сек чтобы не было резкого начала/конца
    fade_samples = sample_rate * 30
    fade_in  = np.linspace(0, 1, fade_samples)
    fade_out = np.linspace(1, 0, fade_samples)
    left[:fade_samples]   *= fade_in
    right[:fade_samples]  *= fade_in
    left[-fade_samples:]  *= fade_out
    right[-fade_samples:] *= fade_out

    stereo = np.column_stack([left, right])
    sf.write(output_path, stereo, sample_rate, subtype='PCM_16')
    print(f"Создан: {output_path} ({duration_min} мин, {beat_hz} Гц бинауральный бит)")
```

### Изохронные тоны (работают без наушников)

```python
def generate_isochronic(
    carrier_hz: float,
    beat_hz: float,         # частота пульсации амплитуды
    duration_min: int,
    output_path: str,
    sample_rate: int = 44100,
    amplitude: float = 0.40,
    duty_cycle: float = 0.5
):
    """
    Ритмичная пульсация амплитуды — мозг синхронизируется с ритмом.
    Работает в моно и через колонки.
    """
    t = np.linspace(0, duration_min * 60, sample_rate * duration_min * 60)
    carrier = np.sin(2 * np.pi * carrier_hz * t)

    # Прямоугольная огибающая с duty_cycle
    envelope = ((t * beat_hz) % 1.0) < duty_cycle
    # Сглаживаем края чтобы убрать щелчки
    from scipy.ndimage import uniform_filter1d
    envelope = uniform_filter1d(envelope.astype(float), size=int(sample_rate * 0.01))

    signal = amplitude * carrier * envelope
    mono = signal.reshape(-1, 1)
    stereo = np.column_stack([mono, mono])  # одинаковые каналы
    sf.write(output_path, stereo, sample_rate, subtype='PCM_16')
```

### Генерация всего каталога

```python
# audium/tools/build_catalog.py
TRACKS = [
    # (id, carrier, beat_hz, тип, минуты)
    # SLEEP
    ("sleep_theta_01", 200, 6.0, "binaural",    30),
    ("sleep_theta_02", 220, 5.0, "binaural",    60),
    ("sleep_delta_01", 220, 2.0, "binaural",    60),
    ("sleep_delta_02", 180, 1.5, "isochronic",  45),
    ("sleep_theta_03", 200, 4.0, "isochronic",  30),

    # FOCUS
    ("focus_beta_01",    320, 15.0, "isochronic", 20),
    ("focus_lobeta_01",  300, 12.0, "binaural",   30),
    ("focus_lobeta_02",  280, 10.0, "isochronic",  45),
    ("focus_beta_02",    300, 16.0, "binaural",   45),

    # STRESS
    ("stress_alpha_01", 250, 10.0, "isochronic", 15),
    ("stress_alpha_02", 220,  8.0, "binaural",   30),
    ("stress_alpha_03", 260,  9.0, "binaural",   45),

    # RECOVERY
    ("recovery_theta_01", 200, 6.0, "isochronic", 20),
    ("recovery_theta_02", 220, 5.0, "binaural",   45),
    ("recovery_alpha_01", 250, 8.0, "isochronic", 20),
]

for track_id, carrier, beat, signal_type, minutes in TRACKS:
    path = f"audio/dsp/{track_id}_raw.wav"
    if signal_type == "binaural":
        generate_binaural(carrier, beat, minutes, path)
    else:
        generate_isochronic(carrier, beat, minutes, path)
```

---

## Ambient-слой

### Текущий статус Suno (важно)

В июле 2026 ожидается судебное решение по делу Suno vs RIAA, которое определит легальный статус AI-музыки в США. До решения использование Suno несёт юридический риск при коммерческом использовании.

**Варианты для ambient-слоя:**

| Вариант | Стоимость | Риск | Рекомендация |
|---------|-----------|------|-------------|
| Suno | Бесплатно/дёшево | Высокий (до решения суда) | Только для черновиков и тестов |
| Creative Commons (freemusicarchive.org, ccmixter.org) | Бесплатно | Низкий | ✅ Для MVP |
| Epidemic Sound / Artlist | $15-30/мес | Нулевой | ✅ После первых продаж |
| Заказ у композитора | 5–15 тыс ₽/трек | Нулевой | V2, когда есть бюджет |

**Решение для MVP:** Creative Commons ambient-треки (атмосферные, минималистичные, без вокала). Таких треков десятки тысяч в открытом доступе.

После июльского решения суда — пересмотреть позицию по Suno.

---

## Микширование

Для MVP — Audacity (бесплатно, Windows/Mac/Linux). Задача простая:

1. Открыть DSP WAV (сгенерированный скриптом)
2. Импортировать ambient-трек (CC-лицензия)
3. Нормализовать ambient до -18 LUFS, DSP до -24 LUFS
4. Синхронизировать длительности (обрезать или зациклить ambient)
5. Экспортировать как MP3 320kbps

Если длина ambient < длины DSP — в Audacity можно зациклить (Effect → Repeat).

**Целевые громкости:**
- Ambient-слой: -18 LUFS
- DSP-слой: -24 LUFS (слышен, но не перекрывает ambient)
- Финальный трек: -14 LUFS (стандарт стриминга)

---

## Технические спецификации треков

| Параметр | Значение |
|----------|----------|
| Формат | MP3 |
| Битрейт | 320 kbps |
| Частота дискретизации | 44100 Hz |
| Каналы | Стерео (обязательно для бинауральных) |
| Нормализация | -14 LUFS |
| Fade in/out | 30 сек |

---

## Полный каталог треков (15 на старте)

### Сон — 5 треков

| ID | Название | Частота | Диапазон | Тип сигнала | Длит. | Наушники |
|----|----------|---------|----------|-------------|-------|----------|
| sleep_theta_01 | Засыпание | 6 Гц | Тета | Бинауральный | 30 мин | **Обязательно** |
| sleep_theta_02 | Ночной переход | 5 Гц | Тета | Бинауральный | 60 мин | **Обязательно** |
| sleep_delta_01 | Глубокое восстановление | 2 Гц | Дельта | Бинауральный | 60 мин | **Обязательно** |
| sleep_delta_02 | Тихая ночь | 1.5 Гц | Дельта | Изохронный | 45 мин | Не нужны |
| sleep_theta_03 | Медленный спуск | 4 Гц | Тета | Изохронный | 30 мин | Не нужны |

### Фокус — 4 трека

| ID | Название | Частота | Диапазон | Тип сигнала | Длит. | Наушники |
|----|----------|---------|----------|-------------|-------|----------|
| focus_beta_01 | Быстрый запуск | 15 Гц | Бета | Изохронный | 20 мин | Не нужны |
| focus_lobeta_01 | Спокойный фокус | 12 Гц | Низкая Бета | Бинауральный | 30 мин | **Обязательно** |
| focus_lobeta_02 | Устойчивое внимание | 10 Гц | Низкая Бета | Изохронный | 45 мин | Не нужны |
| focus_beta_02 | Состояние потока | 16 Гц | Бета | Бинауральный | 45 мин | **Обязательно** |

### Снятие стресса — 3 трека

| ID | Название | Частота | Диапазон | Тип сигнала | Длит. | Наушники |
|----|----------|---------|----------|-------------|-------|----------|
| stress_alpha_01 | Пауза | 10 Гц | Альфа | Изохронный | 15 мин | Не нужны |
| stress_alpha_02 | Разгрузка | 8 Гц | Альфа | Бинауральный | 30 мин | **Обязательно** |
| stress_alpha_03 | Полный сброс | 9 Гц | Альфа | Бинауральный | 45 мин | **Обязательно** |

### Восстановление — 3 трека

| ID | Название | Частота | Диапазон | Тип сигнала | Длит. | Наушники |
|----|----------|---------|----------|-------------|-------|----------|
| recovery_theta_01 | После нагрузки | 6 Гц | Тета | Изохронный | 20 мин | Не нужны |
| recovery_theta_02 | Мышечный отдых | 5 Гц | Тета | Бинауральный | 45 мин | **Обязательно** |
| recovery_alpha_01 | Умственный отдых | 8 Гц | Альфа | Изохронный | 20 мин | Не нужны |

**Итого:** 15 треков. 8 бинауральных (наушники обязательны) + 7 изохронных (без наушников).

---

## Метаданные — catalog.json

```json
// audio/catalog.json — источник правды для плеера и протокола
[
  {
    "id": "sleep_theta_01",
    "title": "Засыпание",
    "category": "sleep",
    "frequency_hz": 6.0,
    "frequency_name": "Тета",
    "duration_sec": 1800,
    "requires_headphones": true,
    "signal_type": "binaural",
    "preview_sec": 90,
    "description": "Тета-ритм 6 Гц — переход в сон. Для засыпания в первые 30 минут."
  },
  {
    "id": "sleep_delta_01",
    "title": "Глубокое восстановление",
    "category": "sleep",
    "frequency_hz": 2.0,
    "frequency_name": "Дельта",
    "duration_sec": 3600,
    "requires_headphones": true,
    "signal_type": "binaural",
    "preview_sec": 90,
    "description": "Дельта-ритм 2 Гц — фаза глубокого сна. Для ночного восстановления."
  },
  {
    "id": "sleep_delta_02",
    "title": "Тихая ночь",
    "category": "sleep",
    "frequency_hz": 1.5,
    "frequency_name": "Дельта",
    "duration_sec": 2700,
    "requires_headphones": false,
    "signal_type": "isochronic",
    "preview_sec": 90,
    "description": "Дельта-ритм 1.5 Гц — изохронный, работает без наушников. 45 минут глубокого сна."
  },
  {
    "id": "focus_beta_02",
    "title": "Состояние потока",
    "category": "focus",
    "frequency_hz": 16.0,
    "frequency_name": "Бета",
    "duration_sec": 2700,
    "requires_headphones": true,
    "signal_type": "binaural",
    "preview_sec": 90,
    "description": "Бета-ритм 16 Гц — глубокая концентрация. Для работы требующей полного погружения."
  },
  {
    "id": "stress_alpha_01",
    "title": "Пауза",
    "category": "stress",
    "frequency_hz": 10.0,
    "frequency_name": "Альфа",
    "duration_sec": 900,
    "requires_headphones": false,
    "signal_type": "isochronic",
    "preview_sec": 90,
    "description": "Альфа-ритм 10 Гц — быстрый сброс напряжения. Без наушников, 15 минут."
  }
  // ... остальные 10 треков по той же схеме
]
```

---

## Структура файлов в репозитории

```
audio/
├── catalog.json          # метаданные всех треков
├── sleep_delta_01.mp3    # готовые треки (в .gitignore — большие файлы)
├── sleep_delta_02.mp3
├── ...
└── dsp/                  # промежуточные DSP WAV (не для продакшна)
    └── .gitignore

tools/
├── generate_binaural.py
├── generate_isochronic.py
└── build_catalog.py
```

**Важно:** аудиофайлы (.mp3, .wav) добавить в `.gitignore` — они большие, хранить в git не нужно. Деплой: rsync или scp на VPS отдельно от кода.

---

## Порядок производства на старте

1. Установить зависимости: `pip install numpy scipy soundfile`
2. Запустить `tools/build_catalog.py` → получить 13 DSP WAV-файлов
3. Подобрать 13 CC ambient-треков под настроение каждой категории
4. Смикшировать в Audacity (1–2 часа на все треки)
5. Экспортировать в `audio/*.mp3`
6. Заполнить `audio/catalog.json`
7. Загрузить на VPS через `rsync -avz audio/ user@server:/app/audio/`

---

## Что добавить после MVP

- Треки с голосовым сопровождением (guided sessions) — нужен голос
- Персонализированные миксы на основе истории пользователя
- Интеграция с Oura/Apple Watch для адаптации частоты
- Заказная авторская музыка у композитора
