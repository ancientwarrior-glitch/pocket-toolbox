# Pocket Toolbox — starter kit 0.1.0

A numbered personal workstation for Termux on Android. Built from the toolbox developed with Yayo; distributed as an empty, configurable starter kit.

## What is included

- Books with numbered browsing, category counts, favorites, reading status and per-book notes.
- Quick notes and dated journal; editing with backups through nano.
- Shopping checklist; personal/business cash-flow ledger, debt balances and payments, corrections, monthly CSV export.
- Generic project hub: batch notes, production dates and ages, purchases, copying photos/videos, upload status and links.
- RSS through an isolated Newsboat configuration; optional PeerTube low-resolution handoff.
- Recent downloads, folder shortcuts, filename/record search, PDF text search, duplicate reports, reading-note exports.
- Dashboard, help, settings, record backup and restore.

No private files, feeds, budgets, account details, books, videos or original phone configuration are included. This is a clean rebuild with its own data format, not a backup or automatic migration of the original personalized toolbox.

## Install on a phone

### Install directly from Termux

With Termux installed, run these three commands in order:

```bash
pkg install -y git
git clone https://github.com/ancientwarrior-glitch/pocket-toolbox.git "$HOME/pocket-toolbox"
bash "$HOME/pocket-toolbox/install.sh"
```

Then run `termux-setup-storage`, allow Android storage access, and type `pocket`.
If `$HOME/pocket-toolbox` already exists, do not delete it blindly. For an existing
checkout of this repository, update with `git -C "$HOME/pocket-toolbox" pull --ff-only`
and rerun its installer. Existing installed settings and records are preserved.

### Install from the downloadable starter ZIP

1. Install Termux from a source listed in the official project documentation: https://github.com/termux/termux-app#installation . This kit targets the F-Droid/GitHub Termux environment with Python 3.10 or later; Android 7+ is the project baseline. Do not mix Termux add-ons from differently signed sources.
2. Download `pocket-toolbox-0.1.0.zip` into Android's Download folder.
3. In Termux, run each line separately and grant shared-storage access:

```bash
termux-setup-storage
pkg install -y unzip
unzip -n ~/storage/downloads/pocket-toolbox-0.1.0.zip -d ~/pocket-toolbox-release
bash ~/pocket-toolbox-release/pocket-toolbox/install.sh
```

The extraction destination is inside Termux so file execution and permissions work predictably. If the browser renamed your ZIP, use its actual filename in the unzip command. Installer questions set your toolbox title, project name, currency label and books path. The default books directory is `~/storage/shared/Books`; choose your existing folder or create it yourself.

Then run:

```bash
pocket
```

Dependencies installed by `install.sh`: Python, nano, Newsboat and poppler (`pdftotext`). No root access or Termux:API add-on is required. The installer creates only its own `pocket` command and `~/.local/share/pocket-toolbox`; it does not edit shell startup files or overwrite existing `menu`, `rss`, or personal records. Reinstalling preserves settings/data and retains the previous application source. A conflicting unrelated `pocket` command causes installation to stop.

## Customize with ChatGPT

Fill in `CUSTOMIZE-ME.md`, then attach **the starter ZIP and that form** to your ChatGPT conversation. Ask for a customized version. ChatGPT cannot inspect a phone just because this kit was installed. For an existing installation, share `config.json` if needed; do not share record backups merely to customize labels or paths. `CUSTOMIZE-ME.md` includes a ready-to-copy prompt.

Settings are in `~/.local/share/pocket-toolbox/config.json` and are also editable from Settings. JSON must use double quotes and no trailing commas. Available preferences are shown in `config.example.json`. The currency setting is a label, not a currency conversion; do not change it to reinterpret existing amounts. Interface text is English; the customization form can request translated labels.

## Everyday controls

`0`: back/exit in numbered menus. `CTRL+C`: cancel an action. In book browsing, `q` exits, `s` searches, `f` lists favorites, `a 3` favorites/unfavorites item 3, `n 3` opens item 3's notes, and `r 3` sets its reading status. A number opens the selected folder/book. ReadEra or another reader handles its own saved reading position.

Notes: put a single `.` on its own line to save an appended entry. In nano, `CTRL+O`, then Enter saves; `CTRL+X` exits. Use Termux's CTRL extra key. Per-book note identities use the path relative to your configured books folder; moving/renaming a book can give it a new note identity.

Shopping: `a` adds; item number toggles checked state; `d 3` removes item 3. Folder browsing: `a` saves the current folder as a shortcut. Media copying asks for a full source file path and a label. Original media is kept. Upload status is entered manually; the kit neither uploads nor deletes videos.

## Budget behavior

The project purchase button and budget menu write to **one ledger**, so a purchase is counted once. Keep Personal and Business scopes separate. Debt creation records an already outstanding amount without implying cash changed hands; debt payments/collections create one cash movement and reduce the debt. These are cash-flow records, not accounting profit, inventory valuation or an available bank/cash balance. There is no starting-balance calculation or Excel synchronization. Export creates a separate CSV. Corrections make a full record backup before modifying/deleting an entry; debt payment corrections cannot exceed the outstanding principal. To change an incorrectly created debt's person/principal/direction, request a customization; that editor is not included in 0.1.0.

## RSS and videos

Add your feeds in the RSS menu. Newsboat controls: Enter opens a feed/article, `o` opens its URL, `R` refreshes, `q` returns. This kit uses separate Newsboat files, not your existing subscriptions.

For a PeerTube-compatible site, add its hostname to `peertube_hosts` in Settings (hostname only, no `https://`) and choose `video_height`, e.g. 360. The helper tries the site's public video API and passes a rendition near/below that limit to an Android player. HLS rendition discovery follows common PeerTube filenames; instances/plugins can differ. If lookup fails, the webpage opens. RSS may contain audio-only enclosures. Install an Android video player such as VLC if needed. Video quality/streaming and Android chooser behavior need testing on the target phone.

## Android file sharing

Grant shared-storage access with `termux-setup-storage`. If a book opens through Android Files but an app refuses the Termux handoff, Termux may require `allow-external-apps = true` in `~/.termux/termux.properties`, followed by `termux-reload-settings`. This is a broader Termux external-app permission, not an ebook-only setting, so the installer does **not** enable it automatically. Review the Termux guidance: https://github.com/termux/termux-app/issues/4723 . An Android reader must support the selected file type.

## Backup, restore and privacy

Records/settings live under `~/.local/share/pocket-toolbox`. Backups go to `Downloads/Pocket-Toolbox-Backups`. They contain your private records, favorites, RSS state and settings; they are **not** public starter kits. Books, copied media, other phone files and the program itself are excluded. Keep this release ZIP for reinstalling the program; then restore a compatible record backup. Copy important backups/media off the phone separately.

Restore accepts this kit's `pocket-*.tar.gz` format only, validates members and the database, stages files, asks you to type `RESTORE`, and backs up the current state first. Matching records/settings are replaced; extra files remain. It rejects links and unsafe archive paths. A storage failure can still interrupt a multi-file restore; the pre-restore snapshot is retained. Backups from the original personalized `menu` are not compatible with this clean starter kit.

The program has no telemetry or automatic publishing. Network activity occurs when using RSS, video lookup or external links. The duplicate finder hashes candidates and writes a report without deleting anything. File search uses names and record text; PDF search can read existing PDF text and normalizes whitespace, but does not perform OCR on scanned images. Large scans can take time/memory.

## Testing and release status

Run `python -m unittest discover -s tests -v` from the source folder for automated checks. These run on desktop Python and cover money validation, ledger consistency, debt limits, note identity, safe backups/restores, configuration validation and installer behavior. They do not substitute for Android testing. Before advertising it as a stable release, test install, reader/player handoff, Newsboat, storage permissions, and restore on a spare Termux setup. Version 0.1.0 is a shareable **starter/beta**.

## Share it

Upload the release ZIP and optionally its customization form to a file host or repository of your choice. The ZIP is the public download; a personalized record backup is private. Nothing is automatically uploaded or published by this project. Include this README and LICENSE with redistributions.

## Uninstall

The launcher is `$PREFIX/bin/pocket`. App code/settings/records are in `~/.local/share/pocket-toolbox`. Back up records before manually removing those paths. Shared media and Download exports/backups are separate and remain until you remove them yourself.

## Primary references

- Termux installation: https://github.com/termux/termux-app#installation
- Newsboat manual: https://newsboat.org/releases/2.42/docs/newsboat.html
- Termux file handoff: https://github.com/termux/termux-app/issues/4723
