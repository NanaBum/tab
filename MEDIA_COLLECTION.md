# Local audio downloads and song/tab source bundles

Two local tools now support a small paired collection before model training.
The Songsterr app lives in the sibling `songsterr-downloader/` repository; this
project supplies YouTube audio download/MP3 conversion and pair packaging. No
transcription weights or existing detector/rhythm defaults are changed.

## Use on this computer

1. Open **Start Songsterr Downloader.cmd** in the parent outputs folder, or visit
   `http://127.0.0.1:5174/` while it is running. The separate Stop launcher stops
   only that owned server. It runs on this computer, with analytics disabled.
2. Open **Download YouTube audio.cmd** for a single YouTube video. Paste the exact
   recording URL. The app saves an MP3, the original downloaded audio stream and
   source metadata under `data/media-downloads/`. Stop preserves partial files
   and the log. This does not search for or verify an "official" recording.
3. **Collect training pair.cmd** prompts for a song-group ID, Songsterr URL and
   matching YouTube URL. Start the Songsterr server first. The collector captures
   one complete tab revision, downloads that recording and creates a source pair.
   No model training starts. Supply the same song-group ID for alternate versions
   of the same underlying song so future splits can keep them together.

The converters need internet to their original sources, not the author's hosted
downloader site. No account/cookies are copied from your browser. Unavailable,
restricted or failed sources produce an error; failed collection stages and logs
are retained. The initial downloader defaults to completed recordings up to two
hours; CLI `--max-duration` can change that limit. Playlist URLs are not collected.

## What a pair contains

Each fresh collection run has staging downloads and `pair/pair.json`, containing:

- Original downloaded audio and an MP3 preview, with file hashes and sizes. Keep
  the original for training to avoid an extra lossy encode. MP3 conversion does
  not improve the quality already delivered by YouTube.
- `score.gp7`, `score.mid`, captured Songsterr metadata and every declared track's
  JSON, all from one metadata/revision capture. Missing tracks fail explicitly
  rather than silently creating a partial reference. Converter warnings remain.
- Source URLs, recording title/channel metadata, Songsterr song/revision IDs,
  asset hashes and optional separate tab/recording permission notes. These notes
  record supplied information rather than infer rights from a software license.
- `label_status: candidate`, pending recording-version/alignment review, and an
  unassigned split. Packaging alone does not mean the tab matches the recording,
  establish a start offset, or produce training tensors.

The original parsed Songsterr values are reserialized; their hashes identify
the saved bytes, not the original HTTP encoding. GP7 is a ZIP-based format even
if the upstream website called its download `.gp`. The existing GP3/4/5 reference
importer does not read GP7 yet. Raw track JSON and MIDI are retained for the next
label-import stage; choose target guitar tracks and check version/alignment
before treating a pair as a reference. No string/fret model is trained here.

Staging plus final pair copies use extra disk space. Start with a small pilot.
Completed output folders are never overwritten automatically. A retry uses a
new output folder; older partials remain available for diagnosis.

## Commands and batch queue

```powershell
.venv-media/Scripts/python.exe -m tabber.media "https://www.youtube.com/watch?v=VIDEO_ID" --output data/one-recording
.venv-media/Scripts/python.exe -m tabber.media --local-audio guitar.wav --output runs/preview.mp3
.venv-media/Scripts/python.exe -m tabber.collect --song-id artist-song --songsterr-url "https://www.songsterr.com/a/wsa/SLUG" --youtube-url "https://www.youtube.com/watch?v=VIDEO_ID"
.venv-media/Scripts/python.exe -m tabber.collect --queue path/to/queue.json --output data/training-pairs/pilot
```

A queue is an explicit list, not a search/scrape operation. Collection is
sequential; each failed pair is recorded and other pairs continue. The command
returns failure if any pair failed, with every result in `collection-results.json`.
Related versions can share `song_id`, but every `pair_id` must be unique:

```json
{
  "format": "tabber-collection-queue",
  "schema_version": 1,
  "items": [{
    "pair_id": "artist-song-studio-version",
    "song_id": "artist-song",
    "songsterr_url": "https://www.songsterr.com/a/wsa/SLUG",
    "youtube_url": "https://www.youtube.com/watch?v=VIDEO_ID",
    "tab_permission_note": "Record the applicable permission here",
    "recording_permission_note": "Record the applicable recording-use information here"
  }]
}
```

Alternatively bundle existing assets with `--audio-manifest AUDIO/audio-source.json`
and `--tab-bundle songsterr-source.zip`, plus `--song-id` and a fresh `--output`.
ZIP entries, declared track completeness, asset membership, sizes and hashes are
checked before copying. Original input files remain unchanged. The resulting
manifest explicitly identifies original audio versus MP3, score and MIDI roles.

## Runtime and verification

Media dependencies are isolated in `.venv-media` (Python 3.13), pinned in
`requirements/media-windows-py313.txt`; install that lock, then `pip install
--no-deps -e .` in that environment. The existing audio environment supplies
FFmpeg 9.0.2; `--ffmpeg` can specify another executable. Node 22.14.0 was used for
yt-dlp's JavaScript runtime. The separate Songsterr app uses its own portable Bun
runtime and retains upstream MIT notices. No global runtime/settings changes.

A live public 19-second nonsong video downloaded and converted successfully,
with original audio retained and MP3 decoding checked. A source pair was then
packaged using an offline nine-track tab fixture and that deliberately unrelated
audio, verifying all hashes. It is explicitly excluded from training and stored
under ignored test runs, not the default training-pairs directory. No actual
matched music pair was collected. Evidence: [media-collection-smoke.json](reports/media-collection-smoke.json).
The downloader and pair CLI paths were exercised; new GUI layouts have not been
visually checked in this milestone. Tests avoid taking over the active desktop.

References: [yt-dlp](https://github.com/yt-dlp/yt-dlp),
[JavaScript runtime setup](https://github.com/yt-dlp/yt-dlp/wiki/EJS), and the
[Songsterr Downloader source](https://github.com/Metaphysics0/songsterr-downloader).
