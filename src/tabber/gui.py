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
        window.title("Tabber — guitar audio to editable tabs")
        window.minsize(660, 590)
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
        ttk.Label(frame, text="Recording").grid(row=2, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(frame, textvariable=self.audio).grid(row=2, column=1, sticky="ew")
        self.browse = ttk.Button(frame, text="Choose file…", command=self.choose_audio)
        self.browse.grid(row=2, column=2, padx=(8, 0))
        self.backend = tk.StringVar(
            value="Machine learning" if self.ml else "Simple melody detector"
        )
        choices = ["Simple melody detector"] + (["Machine learning"] if self.ml else [])
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
            text="Use known BPM, tap the beat, or type auto for a rough estimate. 4/4, standard tuning.",
            wraplength=460,
        ).grid(row=5, column=1, columnspan=2, sticky="w", pady=(5, 12))
        self.grid = tk.StringVar(value="16")
        ttk.Label(frame, text="Rhythm detail").grid(row=6, column=0, sticky="w")
        ttk.Combobox(
            frame, textvariable=self.grid, values=("16", "32", "64"), width=8, state="readonly"
        ).grid(row=6, column=1, sticky="w")
        ttk.Label(frame, text="16 is easier to read; 32 or 64 keeps faster notes.").grid(
            row=7, column=1, columnspan=2, sticky="w", pady=(5, 16)
        )
        self.confidence = tk.StringVar(value="Balanced")
        ttk.Label(frame, text="Note sensitivity").grid(row=8, column=0, sticky="w")
        ttk.Combobox(
            frame,
            textvariable=self.confidence,
            values=("More notes", "Balanced", "Fewer notes"),
            state="readonly",
        ).grid(row=8, column=1, sticky="ew")
        ttk.Label(
            frame, text="More notes keeps weaker detections; fewer notes reduces extra notes."
        ).grid(row=9, column=1, columnspan=2, sticky="w", pady=(5, 16))
        self.separate = tk.BooleanVar(value=False)
        separation_python = (
            self.root
            / ".venv-separation"
            / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        if separation_python.exists():
            ttk.Checkbutton(
                frame,
                text="Separate guitar from a full mix (experimental; slower)",
                variable=self.separate,
            ).grid(row=10, column=0, columnspan=3, sticky="w", pady=(0, 12))
        self.convert = ttk.Button(frame, text="Create guitar tab", command=self.start)
        self.convert.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(0, 12))
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=12, column=0, columnspan=3, sticky="ew")
        self.status = tk.StringVar(
            value="Choose a clean guitar recording. Results are drafts to review."
        )
        ttk.Label(frame, textvariable=self.status, wraplength=600).grid(
            row=13, column=0, columnspan=3, sticky="w", pady=12
        )
        buttons = ttk.Frame(frame)
        buttons.grid(row=14, column=0, columnspan=3, sticky="w")
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
        filename = filedialog.askopenfilename(
            title="Choose a guitar recording",
            filetypes=[("Audio recordings", "*.wav *.flac *.ogg *.mp3"), ("All files", "*.*")],
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
            if tempo == "auto" and self.ml is None:
                raise ValueError("Automatic tempo needs the ML environment")
        except ValueError:
            messagebox.showerror(
                "Check tempo", "Enter BPM from 1 to 999, or auto with the ML setup."
            )
            return
        if not path.is_file():
            messagebox.showerror("Choose a recording", "Choose an existing audio file first.")
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        output = self.root / "runs" / f"{path.stem}-{stamp}"
        interpreter = self.ml if self.backend.get() == "Machine learning" else Path(sys.executable)
        if tempo == "auto":
            interpreter = self.ml
        if interpreter.name.lower() == "pythonw.exe":
            interpreter = interpreter.with_name("python.exe")
        backend = "basic-pitch" if self.backend.get() == "Machine learning" else "baseline"
        command = [
            str(interpreter),
            "-m",
            "tabber",
            str(path.resolve()),
            "--bpm",
            str(tempo),
            "--grid",
            self.grid.get(),
            "--backend",
            backend,
            "--min-confidence",
            str({"More notes": 0.3, "Balanced": 0.5, "Fewer notes": 0.7}[self.confidence.get()]),
            "--output",
            str(output),
        ]
        if self.separate.get():
            command.append("--separate")
        self.running = True
        self.result = None
        self.convert.configure(state="disabled")
        self.browse.configure(state="disabled")
        self.open_tab.configure(state="disabled")
        self.open_folder.configure(state="disabled")
        self.progress.start(12)
        self.status.set(
            "Listening and building the tab… The first ML run may take a little longer."
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
                self.messages.put((False, output, error))
            else:
                estimates = [
                    line
                    for line in process.stdout.splitlines()
                    if line.startswith("Estimated tempo:")
                ]
                ready = "Your draft tab is ready. Open it in TuxGuitar to review and play."
                if estimates:
                    ready += " " + estimates[-1] + "."
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
