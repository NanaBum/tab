"""Small local YouTube-audio front end; no website, account or paid API."""

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from .jobs import run_conversion
from .media import youtube_url


class MediaApp:
    def __init__(self, window):
        self.window, self.running, self.result = window, False, None
        self.messages, self.cancel_event = queue.Queue(), threading.Event()
        self.root = Path(__file__).resolve().parents[2]
        window.title("YouTube audio to MP3 — local downloader")
        window.minsize(650, 340)
        window.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(window, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame, text="Save a YouTube recording as MP3", font=("Segoe UI", 15, "bold")
        ).pack(anchor="w")
        ttk.Label(
            frame, text="Keeps the original downloaded audio and source information too."
        ).pack(anchor="w", pady=(8, 20))
        ttk.Label(frame, text="YouTube video URL").pack(anchor="w")
        self.url = tk.StringVar()
        ttk.Entry(frame, textvariable=self.url).pack(fill="x", pady=(5, 16))
        actions = ttk.Frame(frame)
        actions.pack(fill="x")
        self.download = ttk.Button(actions, text="Download MP3", command=self.start)
        self.download.pack(side="left", fill="x", expand=True)
        self.stop = ttk.Button(actions, text="Stop", state="disabled", command=self.cancel)
        self.stop.pack(side="left", padx=(8, 0))
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill="x", pady=14)
        self.status = tk.StringVar(
            value="Choose the exact recording you want; playlists and live streams are excluded."
        )
        ttk.Label(frame, textvariable=self.status, wraplength=600).pack(anchor="w")
        self.open_folder = ttk.Button(
            frame, text="Open results folder", state="disabled", command=self.open_result
        )
        self.open_folder.pack(anchor="w", pady=(16, 0))
        window.after(150, self.poll)

    def start(self):
        try:
            url, identity = youtube_url(self.url.get())
        except ValueError as error:
            messagebox.showerror("Check video URL", str(error))
            return
        output = (
            self.root / "data/media-downloads" / f"{identity}-{datetime.now():%Y%m%d-%H%M%S-%f}"
        )
        self.running, self.result = True, None
        self.cancel_event.clear()
        self.download.configure(state="disabled")
        self.stop.configure(state="normal")
        self.open_folder.configure(state="disabled")
        self.progress.start(12)
        self.status.set("Downloading the selected recording and creating its MP3…")
        command = [sys.executable, "-m", "tabber.media", url, "--output", str(output / "audio")]
        threading.Thread(target=self.worker, args=(command, output), daemon=True).start()

    def worker(self, command, output):
        try:
            result = run_conversion(
                command, cwd=self.root, log_path=output / "run.log", cancel_event=self.cancel_event
            )
            if result.cancelled:
                message = "Stopped. Partial files and the log are retained in the results folder."
            elif result.returncode:
                lines = (
                    (output / "run.log").read_text(encoding="utf-8", errors="replace").splitlines()
                )
                message = next(
                    (
                        line
                        for line in reversed(lines)
                        if line.startswith("Could not prepare audio:")
                    ),
                    "Download failed; see run.log in the results folder.",
                )
            else:
                message = "MP3 and original audio are ready. Open the results folder."
            self.messages.put((output, message))
        except OSError as error:
            self.messages.put((output, f"Could not run downloader: {error}"))

    def poll(self):
        try:
            output, message = self.messages.get_nowait()
        except queue.Empty:
            pass
        else:
            self.running, self.result = False, output
            self.progress.stop()
            self.download.configure(state="normal")
            self.stop.configure(state="disabled")
            self.open_folder.configure(state="normal" if output.exists() else "disabled")
            self.status.set(message)
        self.window.after(150, self.poll)

    def cancel(self):
        self.cancel_event.set()
        self.stop.configure(state="disabled")
        self.status.set("Stopping this download…")

    def open_result(self):
        if self.result is not None:
            if os.name == "nt":
                os.startfile(self.result)
            else:
                subprocess.Popen(
                    ["open" if sys.platform == "darwin" else "xdg-open", str(self.result)]
                )

    def close(self):
        if self.running:
            messagebox.showinfo(
                "Download running", "Stop the download and wait, or let it finish, then close."
            )
        else:
            self.window.destroy()


def main():
    window = tk.Tk()
    MediaApp(window)
    window.mainloop()


if __name__ == "__main__":
    main()
