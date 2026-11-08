"""Small offline desktop front end; no web server or paid service."""

import importlib.util
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .tempo import TapTempo

SAVED_NOTES = "Rebuild saved notes"
GUITAR_MODEL = "Guitar model (experimental)"


def conversion_command(
    interpreter,
    path,
    output,
    *,
    method,
    tempo,
    grid,
    confidence,
    separate,
    guitar_range=False,
    max_span=5,
    tuning="standard",
):
    """Route saved events directly to export; filtering requires explicit opt-in."""
    interpreter = Path(interpreter)
    if interpreter.name.lower() == "pythonw.exe":
        interpreter = interpreter.with_name("python.exe")
    command = [str(interpreter), "-m", "tabber"]
    from .tuning import parse_tuning

    parse_tuning(tuning)
    command.extend(("--tuning", tuning))
    if method == SAVED_NOTES:
        if tempo == "auto":
            raise ValueError("Saved notes need a supplied BPM; enter a number or tap the tempo.")
        if separate:
            raise ValueError("Turn off guitar separation when rebuilding saved notes.")
        from .events import load_events

        load_events(path)
        command.extend(("--events", str(path.resolve())))
    else:
        if method == GUITAR_MODEL:
            onset = {0.3: 0.2, 0.5: 0.3, 0.7: 0.5}[confidence]
            command.extend(
                (str(path.resolve()), "--backend", "guitar-gaps", "--onset-threshold", str(onset))
            )
        else:
            backend = "basic-pitch" if method == "Machine learning" else "baseline"
            command.extend(
                (str(path.resolve()), "--backend", backend, "--min-confidence", str(confidence))
            )
        if separate:
            command.append("--separate")
    if guitar_range:
        command.append("--guitar-range")
    if max_span != 5:
        command.extend(("--max-span", str(max_span)))
    command.extend(("--bpm", str(tempo), "--grid", str(grid), "--output", str(output)))
    return command


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ml_python(root: Path) -> Path | None:
    candidate = root / ".venv-ml" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if candidate.is_file():
        return candidate
    if importlib.util.find_spec("basic_pitch") is not None:
        return Path(sys.executable)
    return None


class TabberApp:
    def __init__(self, window: tk.Tk):
        self.window = window
        self.root = project_root()
        self.messages = queue.Queue()
        self.running = False
        self.result = None
        self.ml = ml_python(self.root)
        from .guitar_gaps import default_checkpoint

        guitar_python = (
            self.root / ".venv-guitar" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        self.guitar = (
            guitar_python if guitar_python.is_file() and default_checkpoint().is_file() else None
        )
        window.title("Tabber — guitar audio to editable tabs")
        window.minsize(700, 690)
        window.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(window, padding=24)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(
            frame,
            text="Turn a guitar recording into an editable tab",
            font=("Segoe UI", 15, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(frame, text="Processes audio on this computer. No upload or per-track fee.").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(6, 22)
        )
        self.audio = tk.StringVar()
        ttk.Label(frame, text="Input file").grid(row=2, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(frame, textvariable=self.audio).grid(row=2, column=1, sticky="ew")
        self.browse = ttk.Button(frame, text="Choose file…", command=self.choose_audio)
        self.browse.grid(row=2, column=2, padx=(8, 0))
        self.backend = tk.StringVar(
            value="Machine learning" if self.ml else "Simple melody detector"
        )
        choices = ["Simple melody detector"] + (["Machine learning"] if self.ml else [])
        if self.guitar:
            choices.append(GUITAR_MODEL)
        choices.append(SAVED_NOTES)
        ttk.Label(frame, text="Method").grid(row=3, column=0, sticky="w", pady=12)
        self.method = ttk.Combobox(
            frame, textvariable=self.backend, values=choices, state="readonly"
        )
        self.method.grid(row=3, column=1, sticky="ew", pady=12)
        self.tempo = tk.StringVar(value="120")
        self.taps = TapTempo()
        ttk.Label(frame, text="Tempo (BPM/auto)").grid(row=4, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.tempo, width=10).grid(row=4, column=1, sticky="w")
        ttk.Button(frame, text="Tap tempo", command=self.tap_tempo).grid(
            row=4, column=2, padx=(8, 0)
        )
        ttk.Label(
            frame,
            text="Use known BPM, tap the beat, or type auto for a rough estimate. Score meter: 4/4.",
            wraplength=460,
        ).grid(row=5, column=1, columnspan=2, sticky="w", pady=(5, 12))
        self.tuning = tk.StringVar(value="standard")
        ttk.Label(frame, text="Guitar tuning").grid(row=6, column=0, sticky="w", pady=(0, 12))
        ttk.Combobox(
            frame,
            textvariable=self.tuning,
            values=("standard", "drop-d", "eb-standard", "d-standard"),
            state="readonly",
        ).grid(row=6, column=1, sticky="ew", pady=(0, 12))
        self.grid = tk.StringVar(value="16")
        ttk.Label(frame, text="Rhythm detail").grid(row=7, column=0, sticky="w")
        ttk.Combobox(
            frame, textvariable=self.grid, values=("16", "32", "64"), width=8, state="readonly"
        ).grid(row=7, column=1, sticky="w")
        ttk.Label(frame, text="16 is easier to read; 32 or 64 keeps faster notes.").grid(
            row=8, column=1, columnspan=2, sticky="w", pady=(5, 16)
        )
        self.confidence = tk.StringVar(value="Balanced")
        ttk.Label(frame, text="Note sensitivity").grid(row=9, column=0, sticky="w")
        ttk.Combobox(
            frame,
            textvariable=self.confidence,
            values=("More notes", "Balanced", "Fewer notes"),
            state="readonly",
        ).grid(row=9, column=1, sticky="ew")
        ttk.Label(
            frame,
            text="Sensitivity applies when listening. Saved notes keep every event unless you select the range filter below.",
            wraplength=460,
        ).grid(row=10, column=1, columnspan=2, sticky="w", pady=(5, 16))
        self.separate = tk.BooleanVar(value=False)
        self.guitar_range = tk.BooleanVar(value=False)
        self.wider_span = tk.BooleanVar(value=False)
        options = ttk.Frame(frame)
        options.grid(row=11, column=0, columnspan=3, sticky="w", pady=(0, 12))
        ttk.Checkbutton(
            options,
            text="Exclude notes outside selected tuning / 24 frets (save originals)",
            variable=self.guitar_range,
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            options, text="Allow wider fret stretches (7 frets)", variable=self.wider_span
        ).grid(row=1, column=0, sticky="w")
        separation_python = (
            self.root
            / ".venv-separation"
            / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        if separation_python.exists():
            ttk.Checkbutton(
                options,
                text="Separate guitar from a full mix (experimental; slower)",
                variable=self.separate,
            ).grid(row=2, column=0, sticky="w")
        self.convert = ttk.Button(frame, text="Create guitar tab", command=self.start)
        self.convert.grid(row=12, column=0, columnspan=3, sticky="ew", pady=(0, 12))
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=13, column=0, columnspan=3, sticky="ew")
        self.status = tk.StringVar(
            value="Choose a clean guitar recording. Results are drafts to review."
        )
        ttk.Label(frame, textvariable=self.status, wraplength=600).grid(
            row=14, column=0, columnspan=3, sticky="w", pady=12
        )
        buttons = ttk.Frame(frame)
        buttons.grid(row=15, column=0, columnspan=3, sticky="w")
        self.open_tab = ttk.Button(
            buttons,
            text="Open editable tab",
            state="disabled",
            command=lambda: self.open_result("tab.gp5"),
        )
        self.open_tab.pack(side="left")
        self.open_folder = ttk.Button(
            buttons,
            text="Open results folder",
            state="disabled",
            command=lambda: self.open_result(),
        )
        self.open_folder.pack(side="left", padx=8)
        self.window.after(150, self.poll)

    def choose_audio(self):
        replay = self.backend.get() == SAVED_NOTES
        filename = filedialog.askopenfilename(
            title="Choose saved detected notes" if replay else "Choose a guitar recording",
            filetypes=(
                [("Saved notes", "*.json")]
                if replay
                else [("Audio recordings", "*.wav *.flac *.ogg *.mp3 *.m4a *.aac")]
            )
            + [("All files", "*.*")],
        )
        if filename:
            self.audio.set(filename)

    def tap_tempo(self):
        bpm = self.taps.tap(time.monotonic())
        if bpm is None:
            self.status.set(f"Keep tapping with the beat ({len(self.taps.times)} taps).")
        else:
            self.tempo.set(f"{bpm:.1f}")
            self.status.set(f"Tapped tempo: {bpm:.1f} BPM. Keep tapping to refine it.")

    def start(self):
        path = Path(self.audio.get().strip()).expanduser()
        try:
            from .tempo import parse_bpm

            tempo = parse_bpm(self.tempo.get())
            if (
                tempo == "auto"
                and self.ml is None
                and not (self.backend.get() == GUITAR_MODEL and self.guitar)
            ):
                raise ValueError("Automatic tempo needs the ML environment")
        except ValueError:
            messagebox.showerror(
                "Check tempo", "Enter BPM from 1 to 999, or auto with the ML setup."
            )
            return
        if not path.is_file():
            messagebox.showerror("Choose an input", "Choose an existing input file first.")
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        output = self.root / "runs" / f"{path.stem}-{stamp}"
        interpreter = self.ml if self.backend.get() == "Machine learning" else Path(sys.executable)
        if self.backend.get() == GUITAR_MODEL:
            interpreter = self.guitar
        elif tempo == "auto":
            interpreter = self.ml
        try:
            command = conversion_command(
                interpreter,
                path,
                output,
                method=self.backend.get(),
                tempo=tempo,
                grid=self.grid.get(),
                confidence={"More notes": 0.3, "Balanced": 0.5, "Fewer notes": 0.7}[
                    self.confidence.get()
                ],
                separate=self.separate.get(),
                guitar_range=self.guitar_range.get(),
                max_span=7 if self.wider_span.get() else 5,
                tuning=self.tuning.get(),
            )
        except (ValueError, OSError) as error:
            messagebox.showerror("Check saved notes", str(error))
            return
        self.running = True
        self.result = None
        self.convert.configure(state="disabled")
        self.browse.configure(state="disabled")
        self.open_tab.configure(state="disabled")
        self.open_folder.configure(state="disabled")
        self.progress.start(12)
        self.status.set(
            "Rebuilding the tab from saved notes…"
            if self.backend.get() == SAVED_NOTES
            else "Listening and building the tab… The first ML run may take a little longer."
        )
        threading.Thread(target=self.worker, args=(command, output), daemon=True).start()

    def worker(self, command, output):
        try:
            process = subprocess.run(
                command,
                check=False,
                cwd=self.root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            output.mkdir(parents=True, exist_ok=True)
            (output / "run.log").write_text(process.stdout + process.stderr, encoding="utf-8")
            if process.returncode:
                messages = [
                    line
                    for line in process.stderr.splitlines()
                    if line.startswith("Could not transcribe:")
                ]
                error = (
                    messages[-1]
                    if messages
                    else "Conversion failed; see run.log in the results folder."
                )
                notices = [
                    line
                    for line in process.stdout.splitlines()
                    if line.startswith(("Audio note:", "Range note:", "Fingering note:"))
                ]
                if notices:
                    error += " " + " ".join(notices)
                self.messages.put((False, output, error))
            else:
                estimates = [
                    line
                    for line in process.stdout.splitlines()
                    if line.startswith(
                        (
                            "Estimated tempo:",
                            "Timing note:",
                            "Audio note:",
                            "Range note:",
                            "Fingering note:",
                        )
                    )
                ]
                ready = "Your draft tab is ready. Open it in TuxGuitar to review and play."
                if estimates:
                    ready += " " + " ".join(estimates)
                self.messages.put(
                    (
                        True,
                        output,
                        ready,
                    )
                )
        except OSError as error:
            self.messages.put((False, output, f"Could not start conversion: {error}"))

    def poll(self):
        try:
            success, output, message = self.messages.get_nowait()
        except queue.Empty:
            pass
        else:
            self.running = False
            self.result = output
            self.progress.stop()
            self.convert.configure(state="normal")
            self.browse.configure(state="normal")
            self.open_folder.configure(state="normal" if output.exists() else "disabled")
            self.open_tab.configure(state="normal" if success else "disabled")
            self.status.set(message)
        self.window.after(150, self.poll)

    def open_result(self, filename=None):
        if self.result is None:
            return
        path = self.result / filename if filename else self.result
        try:
            if os.name == "nt":
                os.startfile(path)
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])
        except OSError as error:
            messagebox.showerror(
                "Could not open result", f"Open this file manually:\n{path}\n\n{error}"
            )

    def close(self):
        if self.running:
            messagebox.showinfo(
                "Conversion in progress", "Wait for the current conversion to finish, then close."
            )
            return
        self.window.destroy()


def main():
    window = tk.Tk()
    TabberApp(window)
    window.mainloop()


if __name__ == "__main__":
    main()
