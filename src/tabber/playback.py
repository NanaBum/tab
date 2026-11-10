"""Bounded score-order expansion for repeat blocks and explicit ending masks."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RepeatBlock:
    start: int
    close: int
    stop: int
    passes: int


def measure_playback(headers, *, max_measures=10000):
    """Return played source indices, with pass provenance, without mutating headers.

    Supports nested plain repeats and nonnested explicit alternate-ending masks.
    Ambiguous combinations and notation jumps are refused rather than guessed.
    """
    if not isinstance(max_measures, int) or not 1 <= max_measures <= 100000:
        raise ValueError("Playback limit must be from 1 to 100,000 measures")
    opens, blocks = [], []
    for index, header in enumerate(headers):
        if header.direction or header.fromDirection:
            raise ValueError("Navigation jumps need dedicated playback handling")
        if not isinstance(header.repeatClose, int) or header.repeatClose < -1:
            raise ValueError("Invalid repeat count")
        if (
            not isinstance(header.repeatAlternative, int)
            or not 0 <= header.repeatAlternative <= 255
        ):
            raise ValueError("Alternate endings must be explicit eight-pass bitmasks")
        if header.isRepeatOpen:
            opens.append(index)
            if len(opens) > 64:
                raise ValueError("Repeat nesting exceeds 64 levels")
        if header.repeatClose >= 0:
            if opens:
                start = opens.pop()
            elif not blocks:
                start = 0  # First closing repeat may imply the beginning of the score.
            else:
                raise ValueError("Later repeat closures need an explicit opening marker")
            passes = header.repeatClose + 1
            if passes > max_measures:
                raise ValueError("Repeat count exceeds the playback measure limit")
            stop = index + 1
            while stop < len(headers) and headers[stop].repeatAlternative:
                if headers[stop].isRepeatOpen or headers[stop].repeatClose >= 0:
                    raise ValueError(
                        "Overlapping repeat/ending structures need dedicated playback handling"
                    )
                stop += 1
            blocks.append(RepeatBlock(start, index, stop, passes))
    if opens:
        raise ValueError("Repeat opening has no closing marker")
    if len({block.start for block in blocks}) != len(blocks):
        raise ValueError("Repeat blocks with the same opening are ambiguous")
    mask_prefix = [0]
    coverage = [0] * (len(headers) + 1)
    for header in headers:
        mask_prefix.append(mask_prefix[-1] + bool(header.repeatAlternative))
    for block in blocks:
        coverage[block.start] += 1
        coverage[block.stop] -= 1
        ending_seen = False
        for index in range(block.start, block.stop):
            mask = headers[index].repeatAlternative
            if mask and mask.bit_length() > block.passes:
                raise ValueError("Alternate ending names a pass beyond the repeat count")
            if mask:
                ending_seen = True
            elif ending_seen and index <= block.close:
                raise ValueError(
                    "Each measure of a multi-measure ending needs an explicit ending mask"
                )
    active = []
    for block in sorted(blocks, key=lambda item: item.start):
        while active and block.start >= active[-1].stop:
            active.pop()
        if active:
            parent = active[-1]
            if block.stop > parent.close + 1:
                raise ValueError("Repeat blocks cross or share ambiguous endings")
            if mask_prefix[parent.stop] != mask_prefix[parent.start]:
                raise ValueError(
                    "Nested repeats combined with alternate endings are not supported yet"
                )
        active.append(block)
    covering = 0
    for index, header in enumerate(headers):
        covering += coverage[index]
        if header.repeatAlternative and not covering:
            raise ValueError("Alternate ending has no matching repeat block")
    starts = {block.start: block for block in blocks}
    played = []

    def emit(first, stop, owner=None, pass_number=1, stack=()):
        index = first
        while index < stop:
            block = starts.get(index)
            if block is not None and block != owner:
                for iteration in range(1, block.passes + 1):
                    frame = {
                        "start_measure": block.start + 1,
                        "pass": iteration,
                        "total_passes": block.passes,
                    }
                    emit(block.start, block.stop, block, iteration, stack + (frame,))
                index = block.stop
                continue
            mask = headers[index].repeatAlternative
            if not mask or mask & (1 << (pass_number - 1)):
                if len(played) >= max_measures:
                    raise ValueError("Expanded playback exceeds the measure limit")
                played.append(
                    {
                        "source_measure_index": index,
                        "source_measure": headers[index].number,
                        "playback_measure": len(played) + 1,
                        "repeat_passes": list(stack),
                    }
                )
            index += 1

    emit(0, len(headers))
    return played
