# Resuming development

This project was bootstrapped locally before authenticated GitHub access was
available. Corresponding local and remote versions have identical source trees
but different commit parents/IDs. Do not force-push local history over GitHub.

Remote changes have been published through the connected GitHub tools, based on
the verified remote branch head, with every file SHA compared against local Git
before moving the ref. Normalize Windows CRLF to LF when constructing GitHub
blobs so those hashes match. Use expected-head checks for ref updates and preserve
any concurrent user work. Once normal Git authentication is available, a clean
clone is preferable to trying to rewrite these histories.

The review sequence is stacked, with one PR based on its predecessor:

1. Foundation and GP5 export.
2. Local ML and dataset evaluation.
3. Desktop app and saved-note replay.
4. Optional string-tone experiment.
5. Optional CPU guitar separation.
6. Tempo controls and optional estimate.
7. GP5 serialization verification and tied-note readback.
8. Rotating-performer and exact fingering audits.
9. Desktop saved-note rebuilding and model-provenance audit.
10. Saved-score timing audit and grid-movement notices.
11. Independent MIDI string voices and positive durations.
12. Untimed reference-sequence comparison.
13. Local M4A decoding and input diagnostics.
14. Fresh installed-wheel and local setup validation.
15. Optional guitar-specific CPU model, pinned checkpoint and separate environment.
16. Fixed clean electric-guitar comparison, small-subset download and reference audit.
17. Fixed picked-lick comparison on a second electric guitar and tuning-format support.
18. Audited opt-in range filtering, wider-span rebuilding and clearer fingering errors.
19. Single-global-shift event comparison and sparse full-song note matching.

Current local work is on `codex/global-time-alignment`, based on local
`be9683a` / remote `89923cbdfbb3e6bb97bbc76d133d91886f9d8221` (PR #18,
`codex/explicit-guitar-range`, tree `8e3a424df421727e98729a38e74802f879c0e59e`).
Keep the guitar model experimental. The immediate user target is electric riffs,
then full-band recordings. User audio and comparisons remain outside this repo.

Inspect current PRs and branch heads before continuing. These changes remain
unmerged; main is still the initial bootstrap. To get the complete code before
review/merging, use an up-to-date development branch, not main. The known PR #13
milestone is `codex/audio-input-checks`: local commit `68bd31d`, remote commit
`59bcf93b2aa1f9265e182f2399aa377dbbfe94ee`, identical source tree
`e4b49d25916043c748c33d5f25509c4797a412c9`. Later branches may add to it.
Hosted tests remain manual-only.

Development data, audio, weights and run results are under ignored data/, models/
and runs/. Five separate environments exist on the development machine:

- `.venv`: core Python 3.13; `uv.lock`.
- `.venv-ml`: Basic Pitch/features, Python 3.11; `requirements/ml-windows-py311.txt`.
- `.venv-separation`: CPU Demucs, Python 3.11; separate requirements lock.
- `.venv-audio`: FFmpeg codec only, Python 3.13; `requirements/audio-windows-py313.txt`.
- `.venv-guitar`: experimental GAPS guitar model, Python 3.11; `requirements/guitar-windows-py311.txt`.

Core tests must run without importing TensorFlow or downloading models. Package
recipes do not bundle datasets, weights, audio or environments. The exported
source ZIP in the parent directory is made with `git archive`, not a directory ZIP.

The user's action list and progress document are in the parent outputs directory,
along with launchers and attributed audio/tab demos. Keep those up to date when
work needs the user's recordings, preferences, app permissions, or musical review.
Keep processing local, do not use paid services or change spending limits, and
leave merges for explicit user review.

For a supplied single-note string/fret list without timestamps, use the separate
sequence comparator and keep its edit-distance results distinct from timed F1.
Never select thresholds, fingerings or alignment ties using the reference answer
and then describe the result as uncorrected machine accuracy. User recordings and
reference lists stay outside the repository. Input checks are heuristic notices;
they do not authorize gain changes or a causal diagnosis of recording problems.
