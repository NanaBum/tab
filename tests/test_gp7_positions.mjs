import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtempSync, mkdirSync, readFileSync, rmdirSync, unlinkSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

test('GP7 playback preserves explicit unison positions through a repeat', (t) => {
  const require = createRequire(new URL('../../songsterr-downloader/package.json', import.meta.url));
  const { exporter, importer } = require('@coderline/alphatab');
  const score = importer.ScoreLoader.loadAlphaTex(
    String.raw`\tempo 120 . \ro (0.1 5.2).4 9.3.4 r.2 | \rc 2 0.1.1`,
  );
  const gp7 = new exporter.Gp7Exporter().export(score);
  const root = mkdtempSync(join(tmpdir(), 'tabber-gp7-'));
  const tab = join(root, 'tab');
  const scorePath = join(tab, 'score.gp7');
  const manifest = join(root, 'pair.json');
  const plainPath = join(root, 'plain.json');
  const positionedPath = join(root, 'positioned.json');
  mkdirSync(tab);
  t.after(() => {
    for (const path of [plainPath, positionedPath, manifest, scorePath]) {
      try { unlinkSync(path); } catch (error) { if (error.code !== 'ENOENT') throw error; }
    }
    rmdirSync(tab);
    rmdirSync(root);
  });
  writeFileSync(scorePath, gp7);
  writeFileSync(manifest, JSON.stringify({
    format: 'tabber-training-pair', schema_version: 1,
    roles: { score: 'tab/score.gp7' },
    assets: [{ path: 'tab/score.gp7', bytes: gp7.length, sha256: createHash('sha256').update(gp7).digest('hex') }],
    test_fixture: true,
  }));
  const script = fileURLToPath(new URL('../scripts/import_gp7_reference.mjs', import.meta.url));
  const run = (output, flags) => {
    execFileSync(process.execPath, [script, manifest, '--track', '1', '--output', output, ...flags]);
    return JSON.parse(readFileSync(output, 'utf8'));
  };
  const plain = run(plainPath, []);
  const positioned = run(positionedPath, ['--include-positions']);
  assert.deepEqual(positioned.notes, plain.notes);
  const ticks = positioned.metadata.playback_notes;
  assert.deepEqual(ticks.map(({ source_position, ...timing }) => timing), plain.metadata.playback_notes);
  assert.equal(positioned.metadata.score_positions.pitch_consistent, 8);
  assert.deepEqual(ticks.map(({ source_position: p }) => [p.string, p.fret]),
    [[0, 0], [1, 5], [2, 9], [0, 0], [0, 0], [1, 5], [2, 9], [0, 0]]);
  assert.deepEqual(ticks.map((note) => note.attack), [0, 0, 960, 3840, 7680, 7680, 8640, 11520]);
});
