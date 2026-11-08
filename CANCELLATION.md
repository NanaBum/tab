# Stopping a local conversion

The desktop app enables **Stop conversion** while a conversion is running.
Click it once and wait for the stopped message. The interface then lets you
choose another input or start another run. The editable-tab button stays disabled
for a cancelled run, even if a partial GP5 happens to exist in its folder.

The app preserves the original input, `run.log`, saved detection/input diagnostics
and any partial outputs. It does not delete or roll back them. These files can
help diagnose a failure, but they do not establish a completed transcription.
Each app run still has its own results directory. For a new attempt, start a new
conversion rather than assuming partial output is complete.

Python output and errors are written to the log while the process runs rather
than kept only in memory until the end. Python child output is unbuffered so
progress remains available if cancellation interrupts a model. Sensitivity,
tuning, rhythm and fingering behavior are unchanged.

On Windows, the app places the conversion in an owned kernel job object. Stopping
it ends that job's conversion and inherited children, including local decoder or
separation processes; it does not search for processes by name or stop another
independently started Tabber conversion. Closing the job also prevents owned
children being left behind. If a supported job cannot be created or assigned,
the run fails explicitly rather than using a broad process-killing fallback.
The app asks you to stop or finish a running conversion before closing its window.

If a conversion has already finished when the cancellation request is observed,
its completion result takes precedence. Otherwise stopping is a forced process
termination, not a pause/resume feature. An individual output file is normally
replaced atomically, but the collection of outputs is not a single transaction;
some formats may have been written before interruption. A fresh run is required
to complete the work.

## Evidence and scope

- Real Windows process tests stop an owned child while preserving an unrelated
  running process, source bytes and a saved diagnostic. They also cover retained
  stdout/stderr and exit status, cancellation before launch, and launch failure.
- App worker checks retain failure notices and never report a cancelled partial
  tab as successful. The button layout was visually checked. The interactive
  button-click check was interrupted by user input and is not claimed complete.
- A local synthetic audio workload exercises actual guitar-GAPS through the same
  process helper. The checked-in [cancellation evidence](reports/cancellation-check.json)
  records whether model segment entry was observed, cancellation/log retention,
  source preservation and a subsequent successful saved-note conversion.

These checks establish local process behavior, not transcription accuracy. The
non-Windows implementation uses a private process session; descendant stopping
was verified on Windows in this environment, not on macOS/Linux. No model training,
audio uploads or paid service is involved.
