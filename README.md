# Pocket Toolbox — 0.2.2 beta — Finance, boards & private backups

A numbered personal workstation for Termux on Android. Distributed as an empty, configurable starter kit.

## What is included

- Books with numbered browsing, category counts, favorites, reading status and per-book notes.
- Quick notes and dated journal; editing with backups through nano.
- Shopping checklist; full Personal/Business Finance with opening balances, cash, transfers, reconciliation, budgets, invoices, partial payments, inventory, production costs, sales and returns.
- Savings goals, approved profit-share records, manual crypto portfolios, dated prices/FX, trading plans/journal, linear-contract records and CSV imports.
- Three local browser boards: main dashboard, Finance graphs and your business board. Forms save shopping/status changes, notes, cash, budgets, goals, asset prices, stock, batches, sales and payments.
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

### Install from GitHub’s downloadable ZIP

1. Install Termux from a source listed in the official project documentation: https://github.com/termux/termux-app#installation . This kit targets the F-Droid/GitHub Termux environment with Python 3.10 or later; Android 7+ is the project baseline. Do not mix Termux add-ons from differently signed sources.
2. Download the [source ZIP](https://github.com/ancientwarrior-glitch/pocket-toolbox/archive/refs/heads/main.zip) into Android’s Download folder, saving it as `pocket-toolbox-main.zip`. GitHub’s Code → Download ZIP button downloads the same source tree.
3. In Termux, run each line separately and grant shared-storage access:

```bash
termux-setup-storage
pkg install -y unzip
unzip -n ~/storage/downloads/pocket-toolbox-main.zip -d ~/pocket-toolbox-release
bash ~/pocket-toolbox-release/pocket-toolbox-main/install.sh
```

The extraction destination is inside Termux so file execution and permissions work predictably. If the browser renamed your ZIP, use its actual filename in the unzip command. Installer questions set your toolbox title, project name, currency label and books path. The default books directory is `~/storage/shared/Books`; choose your existing folder or create it yourself.

Then run:

```bash
pocket
```

Dependencies installed by `install.sh`: Python, nano, Newsboat, poppler (`pdftotext`) and age for encrypted backups. No root access or Termux:API add-on is required. The installer creates only its own `pocket` command and `~/.local/share/pocket-toolbox`; it does not edit shell startup files or overwrite existing `menu`, `rss`, or personal records. Reinstalling preserves settings/data and retains the previous application source. A conflicting unrelated `pocket` command causes installation to stop.

## Customize with ChatGPT

Fill in `CUSTOMIZE-ME.md`, then attach **the starter ZIP and that form** to your ChatGPT conversation. Ask for a customized version. ChatGPT cannot inspect a phone just because this kit was installed. For an existing installation, share `config.json` if needed; do not share record backups merely to customize labels or paths. `CUSTOMIZE-ME.md` includes a ready-to-copy prompt.

Settings are in `~/.local/share/pocket-toolbox/config.json` and are also editable from Settings. JSON must use double quotes and no trailing commas. Available preferences are shown in `config.example.json`. The currency setting is a label, not a currency conversion; do not change it to reinterpret existing amounts. Interface text is English; the customization form can request translated labels.

## Everyday controls

`0`: back/exit in numbered menus. `CTRL+C`: cancel an action. In book browsing, `q` exits, `s` searches, `f` lists favorites, `a 3` favorites/unfavorites item 3, `n 3` opens item 3's notes, and `r 3` sets its reading status. A number opens the selected folder/book. ReadEra or another reader handles its own saved reading position.

Notes: put a single `.` on its own line to save an appended entry. In nano, `CTRL+O`, then Enter saves; `CTRL+X` exits. Use Termux's CTRL extra key. Per-book note identities use the path relative to your configured books folder; moving/renaming a book can give it a new note identity.

Shopping: `a` adds; item number toggles checked state; `d 3` removes item 3. Folder browsing: `a` saves the current folder as a shortcut. Media copying asks for a full source file path and a label. Original media is kept. Upload status is entered manually; the kit neither uploads nor deletes videos.

## Finance and the boards

Dashboard opens the main board in your Android browser. Keep Termux running while using it; return to Termux and press Enter when finished. The Finance and business buttons open the other boards. There are no external scripts, uploads or live prices. The browser connects only to a temporary random localhost URL.

**First use:** open Budget and debts → Finance → 1 to create Personal/Business accounts with actual opening dates and balances, then categories. Records start blank. Finance options 18/19/20 open the Finance, business and main boards. Your configured title, project name, currency and folders carry through to the public boards. Browser forms include Review → Save for financial/business records; the main checklist saves when checked.

Material purchases and product sales belong in Finance's stock/invoice forms. Paid now creates their linked payment automatically. Do not enter that payment again as a cash expense/income. Production consumes materials and adds finished stock at saved material/labor/overhead costs. Batch ages are planning information, not proof that soap is ready to use. Cash flow, portfolio value and tracked business result are different figures. Profit shares require an explicitly reconciled/approved profit amount.

Crypto prices/FX are dated manual inputs; missing values remain unknown. The manager records spot holdings, swaps, basis-preserving transfers, fees, plans/journal and manual linear contracts. It does not connect to exchanges, place trades, calculate taxes or implement liquidation/inverse contracts. Exit statistics include partial exits; they are not full-trade or time-weighted returns. This is recordkeeping and planning, not a complete Excel formula-grid replacement. See [Finance details and limitations](finance/FINANCE.md).

### Upgrading from public 0.1

Update your checkout and rerun install.sh. Existing config, notes, books references and records are retained. The old budget database stays intact, and Earlier 0.1 ledger provides a read-only view. New money entries use `data/Finance/finance.sqlite`.

If you had old money records, use Finance option 12 to import a snapshot once. The importer is atomic, detects repeated/changed rows and preserves the old database. It imports historical movements to clearly labeled accounts with unknown opening balances, plus outstanding debts. Do not treat those historical movement totals as available cash: create actual current accounts separately. Old purchases lack stock quantities/cost allocations, so inventory needs reviewed opening stock; it is not invented automatically. Fresh users with no old records skip import. Do not keep editing the old database after import.

The public installation is isolated under its own app folder. Other terminal menus and their records are not modified.

## RSS and videos

Add your feeds in the RSS menu. Newsboat controls: Enter opens a feed/article, `o` opens its URL, `R` refreshes, `q` returns. This kit uses separate Newsboat files, not your existing subscriptions.

For a PeerTube-compatible site, add its hostname to `peertube_hosts` in Settings (hostname only, no `https://`) and choose `video_height`, e.g. 360. The helper tries the site's public video API and passes a rendition near/below that limit to an Android player. HLS rendition discovery follows common PeerTube filenames; instances/plugins can differ. If lookup fails, the webpage opens. RSS may contain audio-only enclosures. Install an Android video player such as VLC if needed. Video quality/streaming and Android chooser behavior need testing on the target phone.

## Android file sharing

Grant shared-storage access with `termux-setup-storage`. If a book opens through Android Files but an app refuses the Termux handoff, Termux may require `allow-external-apps = true` in `~/.termux/termux.properties`, followed by `termux-reload-settings`. This is a broader Termux external-app permission, not an ebook-only setting, so the installer does **not** enable it automatically. Review the Termux guidance: https://github.com/termux/termux-app/issues/4723 . An Android reader must support the selected file type.

## Backup, restore and privacy

Records/settings live under `~/.local/share/pocket-toolbox`. New full backups go to your configured Downloads folder under `Pocket-Toolbox-Backups` as encrypted `.tar.gz.age` files. You enter a passphrase into age locally; the toolbox does not store it. Keep it safely: a lost passphrase cannot be recovered. No plaintext export fallback is used.

Use **Backups: create, verify and share** in the main menu. Create explains the generated passphrase and offers immediate verification or sharing before leaving the screen. Verify checks the passphrase and authenticates/decrypts the file to the null device without restoring records or saving a decrypted copy. Share verifies first, then requests the Android share chooser for the encrypted file only; choose MEGA, another storage app or another destination yourself. The toolbox cannot confirm that the other app completed an upload. Show backup folder and filenames gives the actual configured path; Android category filters may hide .age files, so use folder browsing or direct sharing. Android file-sharing permissions/chooser behavior depend on the phone; the installer never enables broader external-app permissions silently. Finance and checklist backup files are included; SQLite databases are copied through the SQLite backup API. They contain your private records, favorites, RSS state and settings; they are **not** public starter kits. Books, copied media, other phone files and the program itself are excluded. Keep the source ZIP or repository checkout for reinstalling the program; then restore a compatible record backup. Copy important backups/media off the phone separately.

Restore accepts this kit's encrypted `pocket-*.tar.gz.age` archives and earlier plaintext `pocket-*.tar.gz` backups, validates members and the database, stages files privately, asks you to type `RESTORE`, and makes a new encrypted backup of the current state first. Matching records/settings are replaced; extra files remain. It rejects links and unsafe archive paths. A storage failure can still interrupt a multi-file restore; the pre-restore snapshot is retained. Backups from the original personalized `menu` are not compatible with public `pocket`. Once a Finance database exists, a pre-0.2 archive without Finance is refused to avoid mixing old and new money records; restore such an archive in a separate install instead.

The program has no telemetry or automatic publishing. Network activity occurs when using RSS, video lookup or external links. The duplicate finder hashes candidates and writes a report without deleting anything. File search uses names and record text; PDF search can read existing PDF text and normalizes whitespace, but does not perform OCR on scanned images. Large scans can take time/memory.

## Import income and expense records

Public Finance option **21** opens a local CSV/XLSX importer. Original-menu users get it at **23** after pulling and rerunning `finance/install_security.py` from their update checkout. No records or files are sent to the repository.

Choose a recent file from Downloads or enter its full path. For CSV choose delimiter and UTF-8 or Windows-1252 encoding; for Excel choose the sheet. Set the header row, match columns, select date/number formats and normal currency units versus whole cents, then choose an existing account. Amounts can be signed, separate debit/credit, or positive income-only/expense-only. Optional columns are category, stable transaction ID, currency and Income/Expense type. New category names are listed before confirmation.

The preview validates all included rows and shows their dates, amounts, categories and duplicate status. You can exclude source row numbers for transfers, totals, trades and already linked invoice/stock payments. Invalid included rows block the entire import. Review account opening dates/balances to avoid counting historical movements twice. Only type `IMPORT` after checking the preview. A private Finance snapshot is made before the atomic save; the source file is unchanged.

Reuse the same source label for future files from the same account/provider. Stable IDs prevent repeated imports and reject changed records under an already imported ID. Without IDs, exact normalized rows and their occurrence counts are recognized, but edits may look new. Matches against existing account/date/amount/description are flagged and skipped unless you explicitly include their source row numbers. These are review aids, not a guarantee of finding every duplicate; different descriptions, source labels and edited no-ID rows require care.

This imports **cash income/expenses**, not stock, invoices, investment positions, transfers, or arbitrary spreadsheet formulas. Trading imports remain under Finance 17. XLSX formula/error cells in mapped columns are refused: use a copy with calculated values pasted, or a CSV export. Old `.xls` files need conversion. Limits: 16 MiB input, 32 MiB expanded XLSX, 10000 data rows, 256 columns; no automatic FX conversion. Excel dates stored as numbers need the Excel serial date option. Compatible encrypted backups remain the route for a complete records restore.

## Security update for an earlier original-menu installation

This optional updater reads and edits supported scripts **locally**; it does not upload them. Existing records and private project names stay on the phone. It does not replace the original menus with public defaults.

Close the running boards/menus, then run:

```bash
pkg install -y git age
git clone --depth 1 https://github.com/ancientwarrior-glitch/pocket-toolbox.git "$HOME/pocket-security-update"
python "$HOME/pocket-security-update/finance/install_security.py"
menu
```

If that update checkout already exists, pull it with `git -C "$HOME/pocket-security-update" pull --ff-only` instead of cloning again. The Finance menu gains encrypted backup/restore entries at its end (21/22 on the standard layout). Option 21 opens Create, Verify, Share, Show folder and Restore. Option 23 imports income/expense tables from CSV or XLSX, using the existing account setup. Rerun the updater after pulling to add this submenu to an already updated original installation. Existing `toolbox-private-*.tar.gz.age` files remain in Downloads/Termux-Backups. Verification restores nothing; sharing verifies first and opens Android’s chooser for the encrypted file only. Recognized simple main-menu backup/restore handlers are redirected. Unknown/custom handlers and older backup widgets may still create plaintext; use the new Finance backup entry explicitly. Previous scripts are saved privately before replacement. Unknown source layouts stop before changing scripts.

The encrypted bundle covers the existing records root, toolbox scripts, main menu, widget launchers and RSS files. Books/media outside these roots and shell profiles need their own backups. Restoring a bundle requires its passphrase and creates a new encrypted pre-restore backup. The old compatibility branch remains separate; this local updater is the security upgrade path.

## Security and privacy

Boards expire after 15 minutes without loading/saving and after one hour total. A Lock now button closes the session. Browser code attempts to blank/lock after 60 seconds hidden; suspended mobile timers cannot guarantee immediate background locking. Private files use owner-only permissions, and symbolic private-data paths are refused. CSV Finance exports now stay in `data/Finance/Exports`; Finance-only snapshots stay privately in `data/Finance/Backups`.

Live records are not encrypted by the app. This is not a vault and does not defend against rooted/compromised devices, malicious software running under the same Termux account or malicious source updates. Old plaintext backups/exports are left untouched; remove them deliberately only after verifying an encrypted backup. See [SECURITY.md](SECURITY.md) for the threat model, safeguards and remaining limits.

## Testing and release status

Run both suites from the source folder:

```bash
python -m unittest discover -s tests -v
python -m unittest discover -s finance -v
```

Checks cover the generic installer/upgrade, customized board paths, legacy debt imports, SQLite backups/restores, linked stock/sales/payments, returns, basis, idempotent form saves and local API restrictions. The underlying boards and forms were checked by the author on his Android phone before generic packaging. The generic integration is covered by automated desktop checks and still needs testing on more phone/reader/player setups. Version **0.2.2 is a beta**, with blank records and no private configuration bundled.

## Support

Free and open source. If Pocket Toolbox helps you, you can support its development with Monero (XMR): [Donate or contribute](SUPPORT.md).

## Share it

Share this repository or its source ZIP. The ZIP is the public download; a personalized record backup is private. Nothing is automatically uploaded or published by this project. Include this README and LICENSE with redistributions.

## Uninstall

The launcher is `$PREFIX/bin/pocket`. App code/settings/records are in `~/.local/share/pocket-toolbox`. Back up records before manually removing those paths. Shared media and Download exports/backups are separate and remain until you remove them yourself.

## Primary references

- Termux installation: https://github.com/termux/termux-app#installation
- Newsboat manual: https://newsboat.org/releases/2.42/docs/newsboat.html
- Termux file handoff: https://github.com/termux/termux-app/issues/4723
