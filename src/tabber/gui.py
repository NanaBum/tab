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

from .events import load_event_document, saved_detections
from .jobs import run_conversion
from .rhythm import SCORE_GRIDS, recorded_score_grid
from .tempo import TapTempo, parse_bpm, recorded_bpm
from .tuning import PRESETS, format_tuning, parse_tuning, recorded_tuning

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
    notes_only=False,
    retry_finer_grid=False,
):
    """Route saved events directly to export; filtering requires explicit opt-in."""
    interpreter = Path(interpreter)
    if interpreter.name.lower() == "pythonw.exe":
        interpreter = interpreter.with_name("python.exe")
    command = [str(interpreter), "-m", "tabber"]
    parse_tuning(tuning)
    command.extend(("--tuning", tuning))
    if notes_only:
        command.append("--notes-only")
    elif retry_finer_grid:
        command.append("--retry-finer-grid")
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
    if max_span != 5 and not notes_only:
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
        self.cancel_event = threading.Event()
        self.result = None
        self.rebuild_input = None
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
            values=tuple(PRESETS),
            state="readonly",
        ).grid(row=6, column=1, sticky="ew", pady=(0, 12))
        self.grid = tk.StringVar(value="16")
        ttk.Label(frame, text="Rhythm detail").grid(row=7, column=0, sticky="w")
        self.rhythm_detail = ttk.Combobox(
            frame, textvariable=self.grid, values=SCORE_GRIDS, width=8, state="readonly"
        )
        self.rhythm_detail.grid(row=7, column=1, sticky="w")
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
        self.notes_only = tk.BooleanVar(value=False)
        self.retry_finer_grid = tk.BooleanVar(value=False)
        options = ttk.Frame(frame)
        options.grid(row=11, column=0, columnspan=3, sticky="w", pady=(0, 12))
        ttk.Checkbutton(
            options,
            text="Save notes and MIDI only (no tab)",
            variable=self.notes_only,
            command=self.update_output_mode,
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            options,
            text="Exclude notes outside selected tuning / 24 frets (save originals)",
            variable=self.guitar_range,
        ).grid(row=1, column=0, sticky="w")
        self.stretch_control = ttk.Checkbutton(
            options, text="Allow wider fret stretches (7 frets)", variable=self.wider_span
        )
        self.stretch_control.grid(row=2, column=0, sticky="w")
        self.finer_grid_control = ttk.Checkbutton(
            options, text="Try a finer grid if notes collide", variable=self.retry_finer_grid
        )
        self.finer_grid_control.grid(row=2, column=1, sticky="w", padx=(8, 0))
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
            ).grid(row=3, column=0, sticky="w")
        actions = ttk.Frame(frame)
        actions.grid(row=12, column=0, columnspan=3, sticky="ew", pady=(0, 12))
        self.convert = ttk.Button(actions, text="Create guitar tab", command=self.start)
        self.convert.pack(side="left", fill="x", expand=True)
        self.stop_conversion = ttk.Button(
            actions, text="Stop conversion", state="disabled", command=self.cancel
        )
        self.stop_conversion.pack(side="left", padx=(8, 0))
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
        self.open_midi = ttk.Button(
            buttons,
            text="Open MIDI",
            state="disabled",
            command=lambda: self.open_result("notes.mid"),
        )
        self.open_midi.pack(side="left", padx=(8, 0))
        self.open_folder = ttk.Button(
            buttons,
            text="Open results folder",
            state="disabled",
            command=lambda: self.open_result(),
        )
        self.open_folder.pack(side="left", padx=8)
        self.rebuild_saved = ttk.Button(
            buttons,
            text="Use saved detections",
            state="disabled",
            command=self.use_saved_detections,
        )
        self.rebuild_saved.pack(side="left")
        self.window.after(150, self.poll)

    def update_output_mode(self):
        notes_only = self.notes_only.get()
        self.rhythm_detail.configure(state="disabled" if notes_only else "readonly")
        self.stretch_control.configure(state="disabled" if notes_only else "normal")
        self.finer_grid_control.configure(state="disabled" if notes_only else "normal")
        self.convert.configure(
            text="Detect notes and create MIDI" if notes_only else "Create guitar tab"
        )

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
            if replay:
                self.set_saved_settings(Path(filename))

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
                notes_only=self.notes_only.get(),
                retry_finer_grid=self.retry_finer_grid.get(),
            )
        except (ValueError, OSError) as error:
            messagebox.showerror("Check saved notes", str(error))
            return
        self.running = True
        self.cancel_event.clear()
        self.result = None
        self.rebuild_input = None
        self.convert.configure(state="disabled")
        self.stop_conversion.configure(state="normal")
        self.browse.configure(state="disabled")
        self.open_tab.configure(state="disabled")
        self.open_midi.configure(state="disabled")
        self.open_folder.configure(state="disabled")
        self.rebuild_saved.configure(state="disabled")
        self.progress.start(12)
        self.status.set(
            "Rebuilding the tab from saved notes…"
            if self.backend.get() == SAVED_NOTES
            else "Listening and building the tab… The first ML run may take a little longer."
        )
        if self.notes_only.get():
            self.status.set(
                "Preparing MIDI from saved notes…"
                if self.backend.get() == SAVED_NOTES
                else "Listening and preparing detected notes and MIDI…"
            )
        threading.Thread(target=self.worker, args=(command, output), daemon=True).start()

    def worker(self, command, output):
        try:
            process = run_conversion(
                command, cwd=self.root, log_path=output / "run.log", cancel_event=self.cancel_event
            )
            log = (output / "run.log").read_text(encoding="utf-8", errors="replace")
            if process.cancelled:
                self.messages.put(
                    (
                        False,
                        output,
                        "Conversion stopped. Saved diagnostics and any partial outputs remain in the results folder; they are not a completed tab.",
                    )
                )
                return
            if process.returncode:
                messages = [
                    line for line in log.splitlines() if line.startswith("Could not transcribe:")
                ]
                error = (
                    messages[-1]
                    if messages
                    else "Conversion failed; see run.log in the results folder."
                )
                notices = [
                    line
                    for line in log.splitlines()
                    if line.startswith(
                        ("Audio note:", "Range note:", "Fingering note:", "Detector note:")
                    )
                ]
                if notices:
                    error += " " + " ".join(notices)
                self.messages.put((False, output, error))
            else:
                estimates = [
                    line
                    for line in log.splitlines()
                    if line.startswith(
                        (
                            "Estimated tempo:",
                            "Timing note:",
                            "Audio note:",
                            "Range note:",
                            "Fingering note:",
                            "Detector note:",
                        )
                    )
                ]
                ready = "Your draft tab is ready. Open it in TuxGuitar to review and play."
                if "--notes-only" in command:
                    ready = "Your detected notes and MIDI are ready. Open MIDI to listen; no editable tab was created."
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
            self.stop_conversion.configure(state="disabled")
            self.browse.configure(state="normal")
            self.open_folder.configure(state="normal" if output.exists() else "disabled")
            self.rebuild_input = saved_detections(output)
            self.rebuild_saved.configure(state="normal" if self.rebuild_input else "disabled")
            self.open_tab.configure(
                state="normal" if success and (output / "tab.gp5").is_file() else "disabled"
            )
            self.open_midi.configure(
                state="normal" if success and (output / "notes.mid").is_file() else "disabled"
            )
            self.status.set(message)
        self.window.after(150, self.poll)

    def use_saved_detections(self):
        if self.running or self.rebuild_input is None:
            return
        if not self.rebuild_input.is_file():
            self.rebuild_saved.configure(state="disabled")
            self.status.set("The saved detections file is unavailable.")
            return
        self.backend.set(SAVED_NOTES)
        self.audio.set(str(self.rebuild_input))
        self.separate.set(False)
        self.set_saved_settings(self.rebuild_input)

    def set_saved_settings(self, path):
        try:
            _, metadata = load_event_document(path)
        except (OSError, ValueError):
            metadata = {}
        bpm = recorded_bpm(metadata)
        tuning = recorded_tuning(metadata)
        grid = recorded_score_grid(metadata)
        if grid is not None:
            self.grid.set(str(grid))
        if tuning is not None:
            self.tuning.set(format_tuning(tuning))
        if bpm is None:
            self.status.set(
                "Saved detections selected. Enter a BPM or tap the tempo, and check the tuning."
            )
        else:
            self.tempo.set(str(bpm))
            self.status.set(f"Saved detections selected at {bpm:g} BPM. Review tempo and tuning.")

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

    def cancel(self):
        if self.running:
            self.cancel_event.set()
            self.stop_conversion.configure(state="disabled")
            self.status.set("Stopping this conversion… Saved diagnostics will be kept.")

    def close(self):
        if self.running:
            messagebox.showinfo(
                "Conversion in progress",
                "Click Stop conversion and wait for it to stop, or let it finish, then close.",
            )
            return
        self.window.destroy()


def main():
    window = tk.Tk()
    TabberApp(window)
    window.mainloop()


if __name__ == "__main__":
    main()
