# Media and Wayland recording helpers

These shortcuts run **only when invoked**, never when sourcing/reloading Zsh.
They do not install optional dependencies or create output directories.

| Helper | Platform / prerequisites | Invocation and output |
| --- | --- | --- |
| `yta-aac`, `yta-best`, `yta-flac`, `yta-mp3` | Any; `yt-dlp` and `ffmpeg` on PATH | Supply one or more URLs. Extract audio in AAC, source-best, FLAC, or MP3 format respectively. yt-dlp writes under its normal output template in the current directory unless configured otherwise. |
| `ytv-best` | Any; `yt-dlp` and `ffmpeg` on PATH | Supply one or more URLs. Prefer MP4 video + M4A audio; fall back to best available streams and request MP4 merging. Availability/format depends on the source and installed codecs. |
| `wsimplescreen` | Linux Wayland; `wf-recorder` and a working audio source | Start recording with audio (`-a`). wf-recorder chooses its default filename/container and codecs; stop using its normal interrupt (Ctrl-C). No arguments are accepted. |
| `wsimplescreenrecorder [file.mp4]` | Linux Wayland; `wf-recorder` and a working audio source | Record with audio to `recording.mp4` in the current directory, or the one supplied `.mp4` filename. wf-recorder chooses codecs, with no hardcoded GPU path or hardware encoder; the installation must support MP4 output. Stop with Ctrl-C. |

Downloader URLs are passed literally after `--` (not evaluated as shell text or
yt-dlp options). Neither downloader helper forces overwrite: yt-dlp's normal
existing-file/cache/configuration behavior applies; review its settings and choose
an appropriate empty output directory before invoking. The MP4 recorder refuses
an already existing filename or symlink before starting (not an atomic guarantee
against another process creating it later). The simple recorder uses wf-recorder's
default filename and overwrite behavior; check its output policy before use.
Recording requires a working Wayland compositor and audio source; the fixtures do
not verify either live prerequisite. Provider failures return nonzero status.
