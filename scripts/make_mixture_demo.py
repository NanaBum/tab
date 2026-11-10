"""Create a controlled guitar + generated bass/drum mixture for local testing.

The generated accompaniment is intentionally simple and not a real full-band
benchmark. Rights and attribution for the guitar input remain with its source.
"""

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("guitar", type=Path)
    parser.add_argument("--output", type=Path, default=Path("runs/mixture-demo"))
    args = parser.parse_args()
    make_mixture(args.guitar, args.output)


def make_mixture(guitar_path: Path, output: Path):
    guitar, rate = sf.read(guitar_path, always_2d=True)
    guitar = guitar.mean(axis=1)
    if not len(guitar) or not np.all(np.isfinite(guitar)):
        raise ValueError("Use a nonempty finite guitar recording")
    guitar /= max(float(np.max(np.abs(guitar))), 1e-6)
    bass, drums = np.zeros_like(guitar), np.zeros_like(guitar)
    generator = np.random.default_rng(0)
    for index, start in enumerate(range(0, len(guitar), int(rate * 0.5))):
        count = min(int(rate * 0.45), len(guitar) - start)
        t = np.arange(count) / rate
        pitch = (39, 44, 46, 39)[index % 4]
        f0 = 440 * 2 ** ((pitch - 69) / 12)
        wave = sum(np.sin(2 * np.pi * f0 * harmonic * t) / harmonic for harmonic in range(1, 6))
        bass[start : start + count] += 0.35 * wave * np.exp(-t * 5)
        kick = np.sin(2 * np.pi * (65 * t + 5 * (1 - np.exp(-30 * t)))) * np.exp(-t * 22)
        noise = generator.normal(0, 1, count) * np.exp(-t * 30)
        drums[start : start + count] += 0.4 * kick + (0.16 if index % 2 else 0.04) * noise
    mixture = guitar + bass + drums
    gain = 0.9 / max(float(np.max(np.abs(mixture))), 1e-6)
    output.mkdir(parents=True, exist_ok=True)
    for name, audio in (("guitar", guitar), ("mixture", mixture), ("accompaniment", bass + drums)):
        sf.write(output / f"{name}.wav", audio * gain, rate)
    print(f"Created controlled test mixture in {output}")


if __name__ == "__main__":
    main()
