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

To screen several collected pairs together, run
`scripts/screen_pair_alignment.py` in the Basic Pitch environment with the
pair manifests as positional arguments and a new `--output` report. It checks
source hashes, compares full-band pitch classes over short windows and
estimates a global shift. The report shows competing peaks and later residuals
for an optional tempo fit based on early windows. Use it to select pairs for
the finer attack check.

For a finer check near a coarse offset, run
`scripts/probe_attack_alignment.py` in the Basic Pitch environment, which
already contains librosa. Supply the local WAV starting at the recording's
time zero, the target `--reference` files, `--coarse-shift`, two or more
ordered `--window START END` intervals, and a fresh `--output` path. The
first window selects a refinement. Later windows report its score alongside
their own peaks and nearby displaced controls. These are diagnostics to review
before choosing a training excerpt.

Both excerpt tools accept `--score-scale` for a constant tempo correction.
They multiply score times by that scale, then add the supplied shift in
seconds. For example, a scale of 0.998651 and a shift of −0.673 seconds
describe the coarse clock tested in the
[tempo-drift pilot](reports/affine-score-clock-pilot.json). Supply the same
clock to every comparison condition. The attack probe only refines the
shift and keeps the scale fixed.

After selecting candidate windows, run `scripts/prepare_training_excerpts.py`
with a version 1 `tabber-excerpt-plan` and a fresh output folder. Each row
names the source pair, decoded recording, attack report, explicit track
numbers, score scale, score shift, split, and recording-time windows. The
packager verifies source hashes, checks each window against the report's
displaced controls, and keeps all versions of a song in one split. It saves
sample-exact WAV excerpts, weak score onsets, and a manifest. Durations in the
event files describe score playback and are carried for inspection.

Run `scripts/evaluate_onset_excerpts.py` in the chosen detector's
environment to compare a fixed validation or test partition. It verifies
recording and label hashes and reports missed and unmatched attacks at
75 ms. For a full-band comparison, run once on the mix and once with
`--separate` into distinct output folders. Compare a second detector on
the exact same separated waveform with `--reuse-stems FIRST_OUTPUT`.
Test labels remain score candidates and are used only to score the
selected clips.
See the [full-band onset benchmark](reports/full-band-onset-test.json) for
the first test comparison with shared stems.

The fixture check imported 108 notes from one selected guitar channel in the
offline nine-track source bundle. Every pitch/start/end matched an independent
Mido playback-iterator calculation to eight decimal places, with source bytes
unchanged. [midi-reference-check.json](reports/midi-reference-check.json) records
that limited evidence. The fixture is excluded from training; no actual matched
music pair, audio alignment or new model-accuracy result is claimed.
