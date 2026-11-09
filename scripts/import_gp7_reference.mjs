// Recover paired note attacks and releases from a collected GP7 score.
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

const ticksPerQuarter = 960; // alphaTab's playback clock
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');

function playback(score, settings, midi, track) {
  const notes = [];
  const tempos = new Map([[0, 500000]]);
  let shift = 0;
  let bendEvents = 0;
  const handler = {
    addTickShift(ticks) { shift = ticks; },
    addTempo(tick, bpm) {
      if (!Number.isFinite(bpm) || bpm <= 0) throw new Error('Invalid playback tempo');
      tempos.set(Math.trunc(tick + shift), Math.trunc(60_000_000 / bpm));
    },
    addNote(index, start, length, pitch, velocity) {
      if (index !== track.index) return;
      const attack = Math.trunc(start + shift);
      const release = Math.trunc(start + shift + length);
      if (!Number.isSafeInteger(attack) || !Number.isSafeInteger(release) ||
          attack < 0 || release <= attack || !Number.isInteger(pitch) ||
          pitch < 0 || pitch > 127 || velocity <= 0) {
        throw new Error('Score contains an invalid generated note');
      }
      notes.push({ attack, release, pitch, velocity });
    },
    addBend(index, _tick, _channel, value) {
      if (index === track.index && value !== 8192) bendEvents++;
    },
    addNoteBend(index, tick, channel, _pitch, value) {
      this.addBend(index, tick, channel, value);
    },
    addTimeSignature() {},
    addRest() {},
    addControlChange() {},
    addProgramChange() {},
    finishTrack() {},
  };
  new midi.MidiFileGenerator(score, settings, handler).generate();
  if (!notes.length) throw new Error('Selected track generated no notes');

  const tempoMap = [];
  for (const [tick, microsecondsPerQuarter] of [...tempos].sort((a, b) => a[0] - b[0])) {
    const previous = tempoMap.at(-1);
    const seconds = previous ? previous.seconds +
      (tick - previous.tick) * previous.microseconds_per_quarter / (ticksPerQuarter * 1e6) : 0;
    tempoMap.push({ tick, seconds, microseconds_per_quarter: microsecondsPerQuarter });
  }
  function secondsAt(tick) {
    const tempo = tempoMap.findLast((change) => change.tick <= tick);
    return tempo.seconds + (tick - tempo.tick) * tempo.microseconds_per_quarter / (ticksPerQuarter * 1e6);
  }
  notes.sort((a, b) => a.attack - b.attack || a.pitch - b.pitch || a.release - b.release);
  return {
    tempoMap,
    bendEvents,
    events: notes.map((note) => ({
      start: secondsAt(note.attack),
      end: secondsAt(note.release),
      pitch: note.pitch,
      confidence: 1,
    })),
    ticks: notes,
  };
}

function main() {
  const { positionals, values } = parseArgs({
    allowPositionals: true,
    options: {
      'list-tracks': { type: 'boolean' },
      track: { type: 'string' },
      output: { type: 'string' },
      downloader: { type: 'string' },
    },
  });
  if (positionals.length !== 1 || (!values['list-tracks'] && (!values.track || !values.output))) {
    throw new Error('Use pair.json --list-tracks or pair.json --track NUMBER --output NEW.json');
  }
  const manifest = resolve(positionals[0]);
  const manifestBytes = readFileSync(manifest);
  const pair = JSON.parse(manifestBytes.toString('utf8'));
  if (pair?.format !== 'tabber-training-pair' || pair.schema_version !== 1 ||
      pair.roles?.score !== 'tab/score.gp7') {
    throw new Error('Use a version 1 collected pair with tab/score.gp7');
  }
  const source = resolve(dirname(manifest), pair.roles.score);
  const bytes = readFileSync(source);
  const asset = pair.assets.filter(({ path }) => path === pair.roles.score);
  if (asset.length !== 1 || asset[0].bytes !== bytes.length || asset[0].sha256 !== hash(bytes)) {
    throw new Error('GP7 file does not match the score declared by the pair');
  }
  const downloader = values.downloader ?? fileURLToPath(new URL('../../songsterr-downloader/', import.meta.url));
  const { Settings, importer, midi } = createRequire(resolve(downloader, 'package.json'))('@coderline/alphatab');
  const settings = new Settings();
  const score = importer.ScoreLoader.loadScoreFromBytes(bytes, settings);
  const tracks = score.tracks.map((track) => ({
    track: track.index + 1,
    name: track.name,
    tunings: track.staves.map((staff) => staff.tuning),
    pitched_strings: track.staves.some((staff) => !staff.isPercussion && staff.tuning.length > 0),
  }));
  if (values['list-tracks']) {
    console.log(JSON.stringify(tracks, null, 2));
    return;
  }
  const selected = tracks.find((track) => track.track === Number(values.track));
  if (!selected?.pitched_strings) throw new Error('Choose a one-based pitched string track');
  const { events, ticks, tempoMap, bendEvents } = playback(score, settings, midi, score.tracks[selected.track - 1]);
  const sourcePair = { songsterr: pair.sources?.songsterr };
  for (const key of [
    'song_id', 'split', 'label_status', 'recording_version_review', 'alignment',
    'permission_notes', 'tab_warnings', 'test_fixture', 'excluded_from_training',
  ]) {
    if (Object.hasOwn(pair, key)) sourcePair[key] = pair[key];
  }
  const payload = {
    format: 'tabber-note-events',
    schema_version: 1,
    metadata: {
      source_file: source,
      source_file_sha256: asset[0].sha256,
      source_pair_sha256: hash(manifestBytes),
      source_pair: sourcePair,
      label_status: 'candidate',
      score_track: selected,
      tempo_map: tempoMap,
      ticks_per_quarter: ticksPerQuarter,
      approximate_techniques: bendEvents > 0 ? ['Pitch trajectories reduced to playback MIDI keys'] : [],
      noncentral_bend_messages: bendEvents,
      playback_notes: ticks,
      limits: 'Score playback times and pitches. Effects follow the GP7 renderer and converter warnings. Recording alignment is a separate step.',
    },
    notes: events,
  };
  const output = resolve(values.output);
  mkdirSync(dirname(output), { recursive: true });
  writeFileSync(output, JSON.stringify(payload, null, 2) + '\n', { flag: 'wx' });
  console.log(`Saved ${events.length} candidate GP7 playback events: ${output}`);
}

try {
  main();
} catch (error) {
  console.error(`Could not import GP7 reference: ${error.message}`);
  process.exitCode = 1;
}
