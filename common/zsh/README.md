# Supported Zsh shortcuts

This is the `common/zsh/.zshrc` reference, not a request to deploy the old Bash
package. “Any” means the shortcut is defined outside the OS branch; Linux-only
entries are defined under `OSTYPE=linux-gnu*`, not as working macOS utilities.
Optional providers are checked when a function is invoked, not installed for you.
Sourcing/reloading defines shortcuts; it does not run package queries, downloads,
mirror selection, recordings or snapshots. Do not source the real profile just to
validate this reference. Provider configuration and existing files still matter.

## Shell environment and daily use

| Name / setting | Platform / prerequisites | Purpose and effect |
| --- | --- | --- |
| `v`, `vim` | Any; `nvim` when invoked | Aliases for Neovim. `reload` sources `~/.zshrc` again; normal profile loaders run again. |
| `reload` | Any; accessible `~/.zshrc` | Re-source the profile, including optional external loaders. No helper action is called by the profile. |
| `la`, `ll` | Any; `ls` | `ls -a` (hidden entries) and `ls -alFh` (long, classified, human sizes). No GNU-only flags required. Arguments are forwarded by the aliases. |
| `df` | Any; `df` | Alias `df -h` for human-readable disk usage; forwards arguments. |
| `free`, `psa` | Linux; `free`, `ps` | Aliases `free -mt` (memory/total) and `ps auxf` (process tree); forward arguments. |
| `psgrep` | Linux; `ps`, `grep` | Exactly one nonempty literal process name; searches `ps aux` with case-insensitive fixed-string `grep -i -F` (also includes VSZ header); read-only. |
| `jctl`, `sysfailed` | Linux; `journalctl`, `systemctl` | Aliases `journalctl -p 3 -xb` (current boot priority 3 errors) and `systemctl list-units --failed`; forward arguments, read-only. |
| `audio` | Linux; `pactl`, `grep` | Print `Server Name` from `pactl info`; read-only, depends on a working audio service. |

Zap is loaded only if its script exists under `${XDG_DATA_HOME:-$HOME/.local/share}/zap/zap.zsh`;
when available it plugs autosuggestions, Supercharge and syntax highlighting.
Starship initializes only if installed; Zsh completion remains case-insensitive.
External `.env`, Google Cloud SDK path/completion and envman loaders are sourced
only when their respective files exist; these loaders can have their own effects.
The existing macOS Homebrew/path branch remains unverified on native macOS.
The Linux branch also defines the interactive `pacman` → `sudo pacman` alias;
the documented read-only package functions bypass that alias.

`EDITOR` defaults to `nvim`, `VISUAL` to `EDITOR`, without replacing a usable
caller selection. History defaults to `$HOME/.zsh_history` and 10000 entries
where the built-in sizes were small/unset; append history suppresses duplicates
and leading-space commands, and Zsh records multiline entries as one entry.
Existing `$HOME/.local/bin` and `$HOME/.bin` directories are prepended once to
PATH on reload (in that effective order), without adding missing directories.
An explicit `CUDA_HOME` is retained; its `bin` is added once only if present.
Otherwise `/opt/cuda` is selected only when `/opt/cuda/bin` exists. No missing
CUDA installation is an error or triggers provisioning.

## Extraction

| Name | Platform / provider | Invocation and side effects |
| --- | --- | --- |
| `ex` | Any; appropriate installed extractor | Exactly one existing archive file; extracts into the current directory using `tar` for `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`, `.tar.xz`, `.tar.zst`; `bunzip2` for `.bz2`; `gunzip` for `.gz`; `unrar` for `.rar`; `unzip` for `.zip`; `uncompress` for `.Z`; `7z` for `.7z`; `ar` for `.deb`. No other extension is supported. |

The selected filename is sent as an absolute local path (including filenames
with spaces, glob characters, leading dashes or colons), not evaluated as code.
The extractor's normal overwrite/output policy applies; single-file decompression
tools may remove the compressed input by default. **This is not an archive
sandbox**: extract only trusted archives after reviewing members and destination.
Invalid arguments, missing extractors and provider failures return nonzero.

## Arch package helpers (Linux)

These functions require the named command(s) on PATH **at invocation**.
Queries bypass the interactive sudo alias. Package-name arguments for mutations
must be nonempty and cannot begin with `-`. Neither updates nor removals use
`--noconfirm`, forced-refresh `-Syy`, dependency-check or integrity bypass.

| Name | Provider | Invocation and effect |
| --- | --- | --- |
| `sps`, `spr`, `sprs` | `sudo`, `pacman` | One or more package names: `sudo pacman -S` installs, `-R` removes, `-Rs` removes with unused dependencies; Pacman's normal confirmation applies. |
| `spqo`, `spsii` | `pacman` | At least one path for `pacman -Qo --` (ownership) or package for `pacman -Sii --` (repository detail); no sudo. |
| `depends` | `pacman` | Exactly one package; print the `Required By` field from `pacman -Sii --`; no sudo. |
| `list`, `listt`, `listaur` | `pacman` | No arguments; explicit package names (`-Qqe`), explicitly installed unrequired packages (`-Qqet`), or explicitly installed foreign/AUR packages (`-Qqem`); no sudo. |
| `update`, `upd` | `sudo`, `pacman` | No arguments; normal confirmed `sudo pacman -Syu` repository refresh/upgrade. `upd` delegates to `update`. |
| `upall`, `upa` | `paru` | No arguments; `paru -Syu` for repository/AUR upgrade with provider's normal confirmation. `upa` delegates to `upall`. |
| `rip`, `riplong`, `big` | `expac`, `sort`, `nl`; `tail` for `rip`/`riplong` | No arguments; dated package installs, last 200/3000 lines respectively, or installed sizes sorted human-numerically (`expac -H M`). Read-only. |
| `cleanup` | `pacman`, `mktemp`, `rm`; `sudo` only for nonempty removal | No arguments; query `pacman -Qtdq`. Empty output with status 0 or silent status 1 means no orphans: no removal. Nonempty valid package identifiers invoke confirmed `sudo pacman -Rns --`; diagnostic output, malformed names and other query failures stop before removal. |

Silent status 1 with empty stdout/stderr is Pacman's no-match convention,
**not** a blanket rule that failed queries succeed. Provider errors do not
authorize a subsequent mutation. Upgrade/install/remove/network queries are
real effects: get separate permission before running them on a host.

## Mirror selection (Linux Arch)

Every selector takes **no arguments** and generates a fresh candidate; each
requires `sudo`, `mktemp`, `rm`, and its listed generator. These can query network
mirrors; none runs at startup. `reflector` and `rate-mirrors` are alternatives,
not installed automatically.

| Name | Generator | Selection intent |
| --- | --- | --- |
| `mirror` | `reflector` | `-f 30 -l 30 --number 10 --verbose`: fast/recent 30, select 10. |
| `mirrord` | `reflector` | Latest 30, 10 sorted by delay. |
| `mirrors` | `reflector` | Latest 30, 10 sorted by score. |
| `mirrora` | `reflector` | Latest 30, 10 sorted by age. |
| `mirrorx` | `reflector` | Age ≤6, latest 20, fastest 20, 5 threads, rate sort, HTTPS. |
| `mirrorxx` | `reflector` | Same as `mirrorx` with 20 threads. |
| `ram` | `rate-mirrors` | Arch, `--allow-root --disable-comments`. |
| `rams` | `rate-mirrors` | Same as `ram`, HTTPS only. |

After nonempty, readable generator output in a temporary `${TMPDIR:-/tmp}`
candidate, `sudo cp -p` copies `/etc/pacman.d/mirrorlist` to
`/etc/pacman.d/mirrorlist.backup` **before** replacement (the backup may be
overwritten by a later invocation). `sudo mktemp` creates a stage in the target
directory; `sudo install -m 644` writes it and `sudo mv -f -T` publishes by
same-directory rename. Generation, backup, staging or publication failures
return nonzero and do not publish a new list; the old list remains. Failed
publication can leave a newly updated backup. A failure to remove the temporary
candidate **after a successful rename** also reports nonzero even though the
new list is already published: inspect both list and backup before retrying.
Cleanup failures may leave temporary candidate/stage paths; review the diagnostic.
No real mirror write/query is part of the automated tests.

## Media and Wayland recording

| Name | Platform / providers | Invocation, output and side effects |
| --- | --- | --- |
| `yta-aac` | Any; `yt-dlp`, `ffmpeg` | One or more URLs; extract audio as AAC. |
| `yta-best` | Any; `yt-dlp`, `ffmpeg` | One or more URLs; extract source-best audio. |
| `yta-flac` | Any; `yt-dlp`, `ffmpeg` | One or more URLs; extract audio as FLAC. |
| `yta-mp3` | Any; `yt-dlp`, `ffmpeg` | One or more URLs; extract audio as MP3. |
| `ytv-best` | Any; `yt-dlp`, `ffmpeg` | One or more URLs; prefer MP4 video + M4A audio; fall back to best video + best audio, request MP4 merging (source/codecs may prevent it). |
| `wsimplescreen` | Linux Wayland; `wf-recorder`, audio source | No arguments; `wf-recorder -a`, with audio; provider chooses filename, container and codec. Stop by normal interrupt (Ctrl-C). |
| `wsimplescreenrecorder` | Linux Wayland; `wf-recorder`, audio source, MP4-capable installation | Zero or one `.mp4` filename; `wf-recorder -a -f` to `recording.mp4` in cwd by default or supplied path, with audio. Stop by Ctrl-C; no fixed GPU/encoder. |

Download URLs are passed literally after `--` to yt-dlp, not treated as yt-dlp
options. Outputs use yt-dlp's normal template (typically current directory)
and its existing-file/cache/configuration policy; these functions do not force
overwrite, make directories or guarantee format availability. The MP4 recorder
refuses an existing file **or symlink** before starting, but has no atomic
protection against concurrent creation; the simple recorder leaves naming and
overwrite behavior to wf-recorder. Check provider settings/output paths first.
Fixture tests cannot prove a live Wayland compositor/audio source works.

## Btrfs and Snapper (Linux)

These assume existing configured filesystems and Snapper `root`/`home`
configurations. Providers are checked on invocation, never installed or set up.

| Name | Providers | Invocation and privileged effect |
| --- | --- | --- |
| `btrfsfs` | `sudo`, `btrfs` | No arguments; `sudo btrfs filesystem df /` displays root usage. |
| `btrfsli` | `sudo`, `btrfs` | No arguments; `sudo btrfs subvolume list / -t` lists root subvolumes/snapshots. |
| `snapli` | `sudo`, `snapper` | Optional `root` (default) or `home`; `sudo snapper -c <config> list`. |
| `snapcr` | `sudo`, `snapper` | Zero or one nonempty description; `sudo snapper -c root create` (with `-d <description>` when supplied). Creates a root snapshot. |
| `snapch` | `sudo`, `snapper` | Same as `snapcr` for the existing `home` configuration. Creates a home snapshot. |

There are no snapshot deletion, filesystem creation or Snapper configuration
creation shortcuts. A listing may still require sudo authentication.

## Configuration editing

User-file helpers are available on any OS; each target must already be a regular
file. On invocation they read current `EDITOR` (falling back to `VISUAL`, then
`nvim` when empty), split it into program/arguments **without shell evaluation**,
check that program on PATH, and pass `--`, fixed target and any extra arguments.
An `EDITOR` with space-separated arguments is supported; shell quoting inside
the variable is not interpreted. No shortcut creates a missing file.

| Name | Platform / provider | Existing target and effect |
| --- | --- | --- |
| `nz` | Any; selected editor | `$HOME/.zshrc` user edit. |
| `nb` | Any; selected editor | `$HOME/.bashrc` user edit (does not modify Bash automatically). |
| `nf` | Any; selected editor | `$HOME/.config/fish/config.fish` user edit. |

Privileged shortcuts below take **no arguments**. Each checks the existing
regular-file target and `sudoedit` executable, then calls `sudoedit -- <target>`;
the editor is not run as root. Editing is a real privileged side effect, not
validated against host files by fixtures. Source GRUB configuration is
`/etc/default/grub`, **not** generated `/boot/grub/grub.cfg`.

| Name | Platform / provider | Fixed target (purpose) |
| --- | --- | --- |
| `npacman` | Linux; `sudoedit` | `/etc/pacman.conf` (Pacman configuration). |
| `nmirrorlist` | Linux; `sudoedit` | `/etc/pacman.d/mirrorlist` (mirrors). |
| `narcomirrorlist` | Linux; `sudoedit` | `/etc/pacman.d/arcolinux-mirrorlist` (optional ArcoLinux mirror source). |
| `ngrub` | Linux; `sudoedit` | `/etc/default/grub` (GRUB source). |
| `nmkinitcpio` | Linux; `sudoedit` | `/etc/mkinitcpio.conf` (initramfs source). |
| `nfstab` | Linux; `sudoedit` | `/etc/fstab` (mounts). |
| `nhosts` | Linux; `sudoedit` | `/etc/hosts` (hosts). |
| `nhostname` | Linux; `sudoedit` | `/etc/hostname` (hostname). |
| `nresolv` | Linux; `sudoedit` | `/etc/resolv.conf` (resolver). |
| `nnsswitch` | Linux; `sudoedit` | `/etc/nsswitch.conf` (name service). |
| `nsamba` | Linux; `sudoedit` | `/etc/samba/smb.conf` (Samba). |
| `ngnupgconf` | Linux; `sudoedit` | `/etc/pacman.d/gnupg/gpg.conf` (Pacman GPG). |
| `nvconsole` | Linux; `sudoedit` | `/etc/vconsole.conf` (console). |
| `nsddm` | Linux; `sudoedit` | `/etc/sddm.conf` (SDDM). |
| `nsddmk` | Linux; `sudoedit` | `/etc/sddm.conf.d/kde_settings.conf` (SDDM KDE). |
| `nlxdm` | Linux; `sudoedit` | `/etc/lxdm/lxdm.conf` (LXDM). |
| `nlightdm` | Linux; `sudoedit` | `/etc/lightdm/lightdm.conf` (LightDM). |
| `nplymouth` | Linux; `sudoedit` | `/etc/plymouth/plymouthd.conf` (Plymouth). |

## Acceptance and preservation evidence

`tests/common/zsh/` uses isolated native Zsh, fixture loaders and fake provider
commands/paths, not the real HOME. This table maps the approved spec to the
existing automated seam and outstanding human checks; it does **not** claim
human QA or independent final feature review is complete. The native tests
verify fixture behavior rather than real host providers or native macOS.

| Criterion | Evidence / remaining boundary |
| --- | --- |
| Z1 | `test_shell_environment.py`: editor/history/PATH, Zap/Starship, completion, reload, fixture loaders and simulated Linux/macOS. Owner to check actual prompt, completion, history and loaders in an authorized isolated shell. |
| Z2 | `test_daily_helpers.py`: daily aliases and fake Linux providers, literal process name and macOS guard. Native macOS behavior still untested. |
| Z3 | `test_daily_helpers.py`: archive argument/format/error regressions with fake extractors, including hostile-looking filenames; no untrusted real extraction. |
| Z4 | `test_arch_packages.py`: fake confirmed install/removal/update, non-sudo queries, Pacman orphan convention, failure stops; real Arch providers/network/privilege require separate approval. |
| Z5 | `test_mirrors.py`: all eight selectors, fake candidate/backup/staging/publication and failure paths. Real mirror/network/privileged writes not exercised. |
| Z6 | `test_media_recording.py`: fake yt-dlp/ffmpeg format, argv and missing-provider behavior; real downloads need separate permission. |
| Z7 | `test_media_recording.py`: fake wf-recorder audio/MP4, missing tool/output and platform guards; live Wayland/audio/overwrite policies need authorized QA. |
| Z8 | `test_snapshots_config_editing.py`: fake Btrfs/Snapper root/home inspection and create; existing host configurations and real snapshots need separate permission. |
| Z9 | `test_shell_environment.py`: optional CUDA, caller override and reload PATH; real CUDA installation not provisioned/verified. |
| Z10 | `test_snapshots_config_editing.py`: invocation-time editor, user targets, fake sudoedit/fixed existing privileged targets and errors; real sudoedit requires separate permission. |
| Z11 | `test_helper_reference.py` checks public name inventory and AC entries here; manual cross-check against integrated `.zshrc` determines meanings, effects, limitations. Documentation test does not execute providers. |
| Z12 | Full package tests, `zsh -n common/zsh/.zshrc` and Git hygiene are automated gates; Bash package, Linux Zsh login profile, root setup/profile, other Stow packages and real HOME remain untouched by this ticket. Final independent Tester/Reviewer on one integrated SHA and owner QA are still required after ticket integration. |

No lock deletion, integrity/dependency bypass, forced no-confirmation, automatic
install/setup, snapshot deletion, reset, generated GRUB edit, hard Git reset or
recursive permission fix is a supported shortcut. No real sudo, package/network
query or upgrade, mirror write, untrusted extraction, snapshot, download,
recording, secret read or provisioning was used to validate these docs. Human
permission is required separately for live privileged/network/capture actions;
the automated macOS simulation is not native macOS proof.
