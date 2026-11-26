# Sounds

Recordings played to callers, mounted into Asterisk as `sounds/h2open/`.

- `no-answer.wav` — played when nobody answers within the ring timeout, e.g.
  "Şu an cevap veremiyoruz, sizi en kısa sürede geri arayacağız." Without
  it, the call just ends. The file name (without extension) is the
  `no_answer_sound` telephony setting, `h2open/no-answer` by default.

Format: WAV, 8000 Hz, 16-bit, mono. Convert any recording with:

    ffmpeg -i recording.m4a -ar 8000 -ac 1 -sample_fmt s16 no-answer.wav
