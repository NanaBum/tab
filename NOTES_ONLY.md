# Notes and timing without fingering

Select **Save notes and MIDI only (no tab)** in the app to hear the detector's
output independently of guitar positions. This option starts unchecked; normal
editable GP5 output remains the default. Select the usual transcription method
and sensitivity, then use **Detect notes and create MIDI**. The rhythm-grid and
fret-stretch controls are disabled in this mode because they do not apply.

Successful runs enable **Open MIDI** and **Open results folder**. The editable-tab
button stays disabled when no GP5 was created. MIDI opens through the operating
system's file association; if no player is configured, open/import `notes.mid`
manually in a MIDI-capable application. This is synthesized playback of detected
notes, not the original recording or a built-in audio player.

```powershell
.venv-guitar/Scripts/python.exe -m tabber riff.wav --backend guitar-gaps --notes-only --bpm 120 --output runs/riff-notes
uv run tabber --events runs/earlier/detected-notes.json --notes-only --bpm 120 --output runs/notes-review
```

The second command reuses saved detections without ML. Later, rebuild the same
event file with notes-only unchecked (or omit `--notes-only` on the CLI) to assign
fingerings and create a tab in a different output folder. Keep the original audio
alongside its provenance: a future learned fingering stage may use string timbre
that cannot be recovered from a pitch list. Files are referenced, not copied into
the output automatically.

## What is saved

- `detected-notes.json`: all selected events in the normal note-event format,
  with exact source seconds, pitches and confidence plus notes-only metadata.
- `notes.mid`: each pitch at the detected timing, rounded to 480 ticks per quarter
  note, with at least one tick of duration. This does not snap to the GP5 rhythm
  grid or assign guitar strings. MIDI tempo/tick representation approximates the
  original seconds; JSON remains the exact event record.
- `diagnostics/`: the normal unfiltered delivered events and input checks, plus
  an indexed exclusion audit if range filtering was explicitly selected. App
  runs also keep their normal `run.log`.

The detector's normal sensitivity/decoding still applies before these events are
delivered. This mode does not recover notes the detector missed, remove extras,
correct rhythm or improve model accuracy. **Exclude notes outside selected
tuning / 24 frets** remains a separate, explicit choice; leave it off when you
want to inspect every detection, including pitches that cannot fit the guitar.
Selected tuning still informs the simple detector's lower frequency band.

Fingering constraints cannot block this path: seven simultaneous events or a
five-fret search failure can still be auditioned. Overlapping unisons receive
independent nonpercussion MIDI channels so their releases remain separate.
More than 15 simultaneous same-pitch events cannot be represented this way and
fail explicitly rather than being merged or dropped. Other pitches can share
channels, and channels do not claim which guitar string was used.

No `tab.gp5`, `tab.txt` or fretted `notes.json` is generated. An output folder
containing those files is refused to prevent old tabs looking like new results.
The input must not be the output's detected-event or MIDI path. Use a fresh run
folder, as the app already does. Individual replacements are atomic for MIDI;
the output collection is not a transaction and partial runs remain incomplete.
