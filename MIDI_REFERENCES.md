# Candidate note labels from collected scores

The local Songsterr source bundle retains GP7, MIDI and raw track JSON from one
captured revision. The existing Guitar Pro importer reads GP3/4/5, not GP7.
This separate MIDI importer prepares timed pitch/attack/release candidates from
explicitly selected MIDI tracks/channels without assigning guitar positions.

For a collected pair, the GP7 playback importer keeps each attack and its own
release together. This recovers overlapping unisons that cannot be paired
reliably after conversion to MIDI. It uses Node and alphaTab from the installed
sibling Songsterr Downloader. Use `--downloader` to point to that installation
when the folders are arranged differently.

```powershell
node scripts/import_gp7_reference.mjs data/training-pairs/PILOT/pair/pair.json --list-tracks
node scripts/import_gp7_reference.mjs data/training-pairs/PILOT/pair/pair.json --track 2 --output runs/score-track-2.json
```

Select the one-based track by name. The importer checks the score hash against
the pair manifest and retains its revision, warnings and review status. The
renderer supplies repeat, tempo and articulation playback. Pitch bends are
reduced to the generated MIDI key, and the saved durations are renderer gates.
Each output is a new file containing unaligned candidate events.

For a MIDI source, first inspect the actual MIDI file:

```powershell
uv run python scripts/import_midi_reference.py data/training-pairs/PILOT/pair/tab/score.mid --list-tracks
uv run python scripts/import_midi_reference.py data/training-pairs/PILOT/pair/tab/score.mid --track 1 --channels 3 --pair-manifest data/training-pairs/PILOT/pair/pair.json --output runs/reference-guitar.json
```

**Do not copy channel 3 blindly:** it is the selected guitar channel only in our
offline test fixture. Inspect each source's channels/programs and retained tab
metadata. The listing reports physical MIDI tracks, names, sounding channels,
note counts and zero-based program numbers. CLI track and channel selection is
one-based; MIDI percussion channel 10 is refused as a pitched guitar reference.

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
With `--pair-manifest`, the MIDI must match the pair's declared score-MIDI hash
and size. Source revision identity, warning lists, permissions/review notes and
test-fixture/training-exclusion flags are then carried into the labels and timed
comparison metadata. The original pair manifest is not overwritten or upgraded
to verified status by importing its MIDI.

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

## Use in comparisons and future training

```powershell
uv run python scripts/compare_timed_events.py runs/reference-guitar.json runs/transcription/detected-notes.json --output runs/comparison.json
```

Imported labels remain candidate references with unverified performance alignment.
The comparison retains their timing/technique/permission caveats and reports raw
scores separately from a reference-fitted global shift. Selecting a MIDI channel
does not establish that the downloaded tab and recording have the same version,
sections or tempo. Keep song grouping, permissions and review status in the pair
record; see [MEDIA_COLLECTION.md](MEDIA_COLLECTION.md) and
[GLOBAL_ALIGNMENT.md](GLOBAL_ALIGNMENT.md). Detector-generated MIDI is useful
for structural readback tests, not independent ground truth for that detector.

Use `scripts/compare_aligned_excerpt.py` when several detector outputs should
share one independently chosen score shift. Pass one `--reference` per target
track from the same pair, one `--prediction NAME FILE` per condition, and supply
`--score-shift`, `--recording-start`, `--duration`, and `--output`.
Predicted times start at excerpt zero. The comparator counts exact coincident
pitch/attack events once across guitar parts. It reports candidate onset scores
without fitting each condition separately. See the
[full-band separation pilot](reports/full-band-separation-pilot.json).

The fixture check imported 108 notes from one selected guitar channel in the
offline nine-track source bundle. Every pitch/start/end matched an independent
Mido playback-iterator calculation to eight decimal places, with source bytes
unchanged. [midi-reference-check.json](reports/midi-reference-check.json) records
that limited evidence. The fixture is excluded from training; no actual matched
music pair, audio alignment or new model-accuracy result is claimed.
