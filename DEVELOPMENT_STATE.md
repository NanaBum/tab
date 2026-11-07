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

The review sequence is stacked: foundation -> ML/evaluation -> desktop app ->
optional string-tone experiment -> local separation -> tempo controls. Inspect
the current pull requests and branch heads before continuing. Nothing has been
merged, and hosted tests are manual-only.

Development data, audio, weights and run results are under ignored data/, models/
and runs/. Three separate environments exist on the development machine: .venv
(core), .venv-ml (Basic Pitch/features), .venv-separation (CPU Demucs). Their locks
are separate. Core tests must run without importing TensorFlow or downloading models.

The user's action list and progress document are in the parent outputs directory,
along with launchers and attributed audio/tab demos. Keep those up to date when
work needs the user's recordings, preferences, app permissions, or musical review.
Keep processing local, do not use paid services or change spending limits, and
leave merges for explicit user review.
