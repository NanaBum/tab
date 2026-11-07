"""Generate a reproducible synthetic C-major scale (not a real-world benchmark)."""

from pathlib import Path

import numpy as np
import soundfile as sf

rate = 22050
parts = []
for pitch in (60, 62, 64, 65, 67, 69, 71, 72):
    t = np.arange(int(rate * 0.38)) / rate
    wave = sum(np.sin(2 * np.pi * 440 * 2 ** ((pitch - 69) / 12) * t * h) / h for h in (1, 2, 3))
    wave *= 0.25 * np.minimum(t / 0.01, 1) * np.minimum((0.38 - t) / 0.03, 1)
    parts.extend((wave, np.zeros(int(rate * 0.12))))
Path("runs").mkdir(exist_ok=True)
sf.write("runs/demo.wav", np.concatenate(parts), rate)
print("Created runs/demo.wav")
