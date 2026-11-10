# Local MIDI references

Import a local MIDI file to create timed reference notes for comparisons.
Select the guitar track or channels explicitly.

```powershell
uv run python scripts/import_midi_reference.py score.mid --list-tracks
uv run python scripts/import_midi_reference.py score.mid --track 1 --channels 3 --output runs/reference-guitar.json
```

The track and channel numbers are examples. Use the listing to choose those
in your file. MIDI channel 10 is reserved for percussion.

A type-0 MIDI may put every instrument in one physical track. Consequently,
choosing track 1 alone does not mean selecting the first guitar. Multiple sounding
tracks require an explicit track choice; multiple sounding channels require an
explicit channel list, such as `--channels 3,4`. The tool does not guess a target
instrument from track names or silently include bass, drums or other parts.

## Timing and unsupported expression

MIDI types 0 and 1 with positive ticks per beat are supported. All tracks supply
the global tempo map, including changes inside a held note; playback time starts
at tick zero, preserving written lead-in/rest time. Note-off and zero-velocity
note-on messages release notes. No score-grid snapping, tempo fitting, audio
alignment or string/fret inference is applied. Source tick/channel/velocity
records and the MIDI hash accompany the normal `tabber-note-events` JSON.
Pitch bends, sustain pedal, portamento and active all-notes/sound-off controls
are refused by default. For deliberately approximate **base pitches and note-off
gates**, use `--allow-approximate-expression`. The output retains expression flags
and messages. That mode does not expand bend curves, extend pedal-held releases,
or turn the file into verified performed-pitch labels. Dangling or unmatched
notes still fail; durations are never invented to repair an input.

Overlapping equal pitches on independent channels retain separate releases.
Overlapping unisons on the same channel are ambiguous and fail rather than
choosing a pairing. Channels carrying notes across multiple physical tracks are
also refused to avoid guessing instrument/release ownership. Type-2 asynchronous
files, SMPTE timing, conflicting/zero tempos, zero-duration notes and more than
one million messages fail explicitly. This is a bounded reference-import path,
not a complete MIDI synthesizer or general performance reconstruction engine.

## Compare with a transcription

```powershell
uv run python scripts/compare_timed_events.py runs/reference-guitar.json runs/transcription/detected-notes.json --output runs/comparison.json
```

Check that the reference and recording represent the same performance before
using the timing scores. See [GLOBAL_ALIGNMENT.md](GLOBAL_ALIGNMENT.md) for
comparison settings.
