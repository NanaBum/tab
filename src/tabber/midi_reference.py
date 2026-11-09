"""Explicit MIDI track/channel selection for candidate timed note labels."""

from collections import Counter

from .models import Note
from .reference import ReferenceScore


def _messages(midi):
    if midi.type not in (0, 1) or midi.ticks_per_beat <= 0:
        raise ValueError(
            "Use synchronous MIDI type 0/1 with positive ticks per beat; type 2/SMPTE need separate timing"
        )
    rows, tempos = [], {}
    for track, messages in enumerate(midi.tracks):
        tick = 0
        for index, message in enumerate(messages):
            if type(message.time) is not int or message.time < 0:
                raise ValueError("MIDI delta ticks must be nonnegative integers")
            tick += message.time
            if message.type == "set_tempo":
                if message.tempo <= 0 or tick in tempos and tempos[tick] != message.tempo:
                    raise ValueError("MIDI tempo must be positive and unambiguous at each tick")
                tempos[tick] = message.tempo
            rows.append((tick, track, index, message))
            if len(rows) > 1000000:
                raise ValueError("MIDI reference exceeds the one-million-message limit")
    return sorted(rows, key=lambda row: row[:3])


def describe_midi(midi):
    _messages(midi)
    return _descriptions(midi)


def _descriptions(midi):
    result = []
    for index, track in enumerate(midi.tracks, 1):
        counts = Counter(
            message.channel for message in track if message.type == "note_on" and message.velocity
        )
        programs = {}
        for message in track:
            if message.type == "program_change":
                programs.setdefault(message.channel + 1, set()).add(message.program)
        result.append(
            {
                "track": index,
                "name": track.name,
                "note_attacks": sum(counts.values()),
                "channels": [
                    {
                        "channel": channel + 1,
                        "note_attacks": count,
                        "percussion_channel": channel == 9,
                        "programs_zero_based": sorted(programs.get(channel + 1, set())),
                    }
                    for channel, count in sorted(counts.items())
                ],
            }
        )
    return result


def extract_midi_reference(
    midi, *, track_number=None, channels=None, allow_approximate_expression=False
):
    """Import gates at score playback times; never infer strings or align audio.

    Track numbers and requested channels are one-based for CLI use. Same-channel
    overlapping unisons are refused because MIDI does not identify their releases.
    Pitch bends/pedal/portamento need explicit base-note approximation.
    """
    rows = _messages(midi)
    descriptions = _descriptions(midi)
    sounding = [track for track in descriptions if track["note_attacks"]]
    if not sounding:
        raise ValueError("MIDI file contains no sounding note events")
    if track_number is None:
        if len(sounding) != 1:
            raise ValueError("Choose a MIDI track explicitly with --track; use --list-tracks first")
        track_number = sounding[0]["track"]
    if type(track_number) is not int or not 1 <= track_number <= len(midi.tracks):
        raise ValueError("MIDI track number is outside the file")
    selected = descriptions[track_number - 1]
    available = {row["channel"] for row in selected["channels"]}
    if channels is None:
        if len(available) != 1:
            raise ValueError(
                "Choose MIDI channels explicitly with --channels; a type-0 file can mix every instrument"
            )
        channels = available
    channels = tuple(channels)
    if (
        not channels
        or len(set(channels)) != len(channels)
        or any(type(c) is not int or c not in available for c in channels)
    ):
        raise ValueError(
            "Choose distinct one-based channels containing notes in the selected track"
        )
    if 10 in channels:
        raise ValueError("MIDI percussion channel 10 is not a pitched guitar reference")
    channel_set = {channel - 1 for channel in channels}
    if any(
        track != track_number - 1
        and message.type == "note_on"
        and message.velocity
        and message.channel in channel_set
        for _, track, _, message in rows
    ):
        raise ValueError(
            "Selected channels also contain notes in another MIDI track; channel ownership needs source-score separation"
        )
    tempo, previous_tick, seconds = 500000, 0, 0.0
    tempo_map = [{"tick": 0, "microseconds_per_beat": tempo}]
    active, notes, events, features, expression_events = {}, [], [], set(), []
    for tick, track, index, message in rows:
        seconds += (tick - previous_tick) * tempo / (midi.ticks_per_beat * 1000000)
        previous_tick = tick
        if message.type == "set_tempo":
            tempo = message.tempo
            change = {"tick": tick, "microseconds_per_beat": tempo}
            if tempo_map[-1]["tick"] == tick:
                tempo_map[-1] = change
            elif tempo_map[-1]["microseconds_per_beat"] != tempo:
                tempo_map.append(change)
        channel = getattr(message, "channel", None)
        if channel not in channel_set:
            continue
        feature = None
        if message.type == "pitchwheel" and message.pitch:
            feature = "pitch-bend"
        elif message.type == "control_change":
            if message.control == 64 and message.value >= 64:
                feature = "sustain-pedal"
            elif message.control == 65 and message.value >= 64:
                feature = "portamento"
            elif message.control in (120, 123) and any(key[0] == channel for key in active):
                feature = "all-notes-or-sound-off"
        if feature:
            features.add(feature)
            expression_events.append({"track": track + 1, "tick": tick, "message": message.dict()})
        if track != track_number - 1 or message.type not in ("note_on", "note_off"):
            continue
        key = channel, message.note
        if message.type == "note_on" and message.velocity:
            if key in active:
                raise ValueError(
                    "Overlapping unisons on one MIDI channel have ambiguous releases; use original score/track JSON"
                )
            active[key] = (tick, seconds, message.velocity)
        else:
            if key not in active:
                raise ValueError(
                    "Selected MIDI note release has no matching attack in this track/channel"
                )
            start_tick, start_seconds, velocity = active.pop(key)
            if seconds <= start_seconds:
                raise ValueError("Selected MIDI note has no positive duration")
            notes.append(Note(start_seconds, seconds, message.note))
            events.append(
                {
                    "track": track_number,
                    "channel": channel + 1,
                    "pitch": message.note,
                    "start_tick": start_tick,
                    "end_tick": tick,
                    "velocity": velocity,
                }
            )
    if active:
        raise ValueError("Selected MIDI track ends with unreleased notes; no duration was invented")
    if not notes:
        raise ValueError("Selected MIDI track/channels have no sounding note events")
    if features and not allow_approximate_expression:
        raise ValueError(
            "MIDI expression needs explicit --allow-approximate-expression for base-note/gate labels: "
            + ", ".join(sorted(features))
        )
    order = sorted(
        range(len(notes)),
        key=lambda i: (
            notes[i].start,
            events[i]["start_tick"],
            events[i]["channel"],
            notes[i].pitch,
        ),
    )
    return ReferenceScore(
        [notes[i] for i in order],
        {
            "reference_status": "Candidate MIDI playback reference; not verified against an audio recording",
            "data_permission": "Maintained separately in source-pair records; not assessed by this importer",
            "track": track_number,
            "track_name": selected["name"],
            "midi_channels_one_based": sorted(channels),
            "channel_descriptions": [
                row for row in selected["channels"] if row["channel"] in channels
            ],
            "ticks_per_beat": midi.ticks_per_beat,
            "tempo_map": tempo_map,
            "source_events": [events[i] for i in order],
            "approximate_techniques": bool(features),
            "approximate_expression_requested": allow_approximate_expression,
            "technique_flags": sorted(features),
            "expression_events": expression_events,
            "timing": "MIDI playback seconds from tick zero using the global tempo map; no audio alignment or score-grid snapping",
            "limits": "Note-on pitches and explicit note-off gates only. No string/fret inference, pitch-bend expansion, pedal release extension or performance-ground-truth claim.",
        },
    )
