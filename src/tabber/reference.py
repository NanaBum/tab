"""Read local Guitar Pro scores as candidate timed references, not audio truth."""

import math
from bisect import bisect_right
from dataclasses import dataclass

from guitarpro import models as gp

from .models import Note


@dataclass(frozen=True)
class ReferenceScore:
    notes: list[Note]
    metadata: dict


def describe_tracks(song):
    return [
        {
            "track": index,
            "name": track.name,
            "strings": len(track.strings),
            "tuning": [string.value for string in track.strings],
            "capo": track.offset,
            "percussion": track.isPercussionTrack,
        }
        for index, track in enumerate(song.tracks, 1)
    ]


def _tempo_clock(song):
    explicit = {}
    changes = {960: song.tempo}
    for track in song.tracks:
        for measure in track.measures:
            for voice in measure.voices:
                for beat in voice.beats:
                    change = beat.effect.mixTableChange
                    tempo = change.tempo if change is not None else None
                    if tempo is None:
                        continue
                    if tempo.duration != 0:
                        raise ValueError("Gradual tempo changes need dedicated playback alignment")
                    if beat.start is None or beat.start < 960:
                        raise ValueError("Tempo change has no valid score position")
                    if beat.start in explicit and explicit[beat.start] != tempo.value:
                        raise ValueError("Tracks declare conflicting tempos at the same position")
                    explicit[beat.start] = tempo.value
    changes.update(explicit)
    if any(not math.isfinite(value) or value <= 0 for value in changes.values()):
        raise ValueError("Score tempos must be finite and positive")
    ticks, seconds, values = [], [], []
    for tick, bpm in sorted(changes.items()):
        seconds.append(seconds[-1] + (tick - ticks[-1]) * 60 / (960 * values[-1]) if ticks else 0.0)
        ticks.append(tick)
        values.append(bpm)

    def clock(tick):
        if tick < 960:
            raise ValueError("Note position precedes the start of the score")
        index = bisect_right(ticks, tick) - 1
        return seconds[index] + (tick - ticks[index]) * 60 / (960 * values[index])

    return clock, [
        {"tick": tick, "seconds": second, "bpm": bpm}
        for tick, second, bpm in zip(ticks, seconds, values)
    ]


def _techniques(note, beat):
    effect = note.effect
    details = {}
    for name in (
        "bend",
        "grace",
        "harmonic",
        "slides",
        "trill",
        "tremoloPicking",
        "letRing",
        "staccato",
        "palmMute",
        "hammer",
        "vibrato",
    ):
        value = getattr(effect, name)
        if value:
            details[name] = repr(value)
    if note.type == gp.NoteType.dead:
        details["dead_note"] = "Unpitched/percussive note; base fret pitch only"
    if note.durationPercent != 1:
        details["durationPercent"] = repr(note.durationPercent)
    if beat.effect.stroke.direction != gp.BeatStrokeDirection.none:
        details["stroke"] = repr(beat.effect.stroke)
    if beat.effect.tremoloBar is not None:
        details["tremoloBar"] = repr(beat.effect.tremoloBar)
    if beat.effect.hasRasgueado or beat.effect.vibrato:
        details["beat_expression"] = "Rasgueado or beat vibrato"
    if beat.octave != gp.Octave.none:
        details["octave_sign"] = repr(beat.octave)
    return details


def extract_reference(song, *, track_number=None, allow_approximate_techniques=False):
    if track_number is None:
        if len(song.tracks) != 1:
            raise ValueError("Choose a track explicitly; inspect --list-tracks first")
        track_number = 1
    if not isinstance(track_number, int) or not 1 <= track_number <= len(song.tracks):
        raise ValueError("Track number must select an existing track (1-based)")
    track = song.tracks[track_number - 1]
    if track.isPercussionTrack or not track.strings:
        raise ValueError("Choose a pitched string-instrument track")
    if [string.number for string in track.strings] != list(range(1, len(track.strings) + 1)):
        raise ValueError("Unexpected source string numbering")
    if not isinstance(track.offset, int) or track.offset < 0:
        raise ValueError("Score capo must be a nonnegative fret number")
    if not song.measureHeaders:
        raise ValueError("Score has no measures")
    if len(track.measures) != len(song.measureHeaders):
        raise ValueError("Selected track does not cover the score's measures")
    expected = 960
    for header in song.measureHeaders:
        if (
            header.isRepeatOpen
            or header.repeatClose >= 0
            or header.repeatAlternative
            or header.direction
            or header.fromDirection
        ):
            raise ValueError(
                "Unfold repeats, alternate endings and navigation jumps before timed import"
            )
        if header.tripletFeel != gp.TripletFeel.none:
            raise ValueError("Swing/triplet-feel playback needs dedicated timing alignment")
        if header.start != expected or header.length <= 0:
            raise ValueError("Score measure positions are not continuous")
        expected = header.end
    clock, tempo_map = _tempo_clock(song)
    events, active = [], {}
    for measure in track.measures:
        for voice_index, voice in enumerate(measure.voices):
            for beat in voice.beats:
                if not beat.notes:
                    continue
                if (
                    beat.start is None
                    or beat.start < measure.header.start
                    or beat.duration.time <= 0
                    or beat.start + beat.duration.time > measure.header.end
                ):
                    raise ValueError("A sounding beat has invalid score timing")
                for note in beat.notes:
                    if (
                        not 1 <= note.string <= len(track.strings)
                        or not 0 <= note.value <= track.fretCount
                    ):
                        raise ValueError("Source note has an invalid string or fret")
                    if note.type not in (gp.NoteType.normal, gp.NoteType.tie, gp.NoteType.dead):
                        raise ValueError("Unexpected source note type")
                    key = voice_index, note.string
                    details = _techniques(note, beat)
                    if track.is12StringedGuitarTrack:
                        details["12_string_doubling"] = (
                            "Extra strings not expanded into performed pitches"
                        )
                    if note.type == gp.NoteType.tie:
                        previous = active.get(key)
                        if (
                            previous is None
                            or previous["end_tick"] != beat.start
                            or previous["fret"] != note.value
                        ):
                            raise ValueError("Source contains a broken sustained-note tie")
                        previous["end_tick"] = beat.start + beat.duration.time
                        previous["technique_details"].update(details)
                    else:
                        event = {
                            "start_tick": beat.start,
                            "end_tick": beat.start + beat.duration.time,
                            "string": note.string - 1,
                            "fret": note.value,
                            "voice": voice_index,
                            "measure": measure.number,
                            "technique_details": details,
                        }
                        events.append(event)
                        active[key] = event
    events.sort(key=lambda event: (event["start_tick"], event["string"], event["voice"]))
    features = sorted({name for event in events for name in event["technique_details"]})
    if features and not allow_approximate_techniques:
        raise ValueError(
            "Performance techniques need review: "
            + ", ".join(features)
            + ". Use --allow-approximate-techniques only for candidate base-note inspection."
        )
    notes = [
        Note(
            clock(event["start_tick"]),
            clock(event["end_tick"]),
            track.strings[event["string"]].value + track.offset + event["fret"],
        )
        for event in events
    ]
    if not notes:
        raise ValueError("Selected track contains no sounding note events")
    return ReferenceScore(
        notes,
        {
            "reference_status": "Candidate notated reference; performance alignment and accuracy not verified",
            "data_permission": "Not assessed by this importer",
            "title": song.title,
            "artist": song.artist,
            "track": track_number,
            "track_name": track.name,
            "tuning": [string.value for string in track.strings],
            "capo": track.offset,
            "string_convention": "Zero-based, source string 1 first; frets relative to capo",
            "tempo_map": tempo_map,
            "source_events": events,
            "approximate_techniques": bool(features),
            "technique_flags": features,
            "timing": "Metronomic score seconds from tick 960; not audio-aligned performance timing",
        },
    )
