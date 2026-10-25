# Security and privacy — 0.2.1 beta

## Protected scope

This is a local personal toolbox, not a multi-user server or encrypted live-data vault. Live SQLite/JSON/text records remain readable to the Termux app user. A rooted/compromised device, malware running under the same app account, a compromised browser, stolen unlocked Termux access or malicious source updates are outside these protections. Keep Android and Termux packages updated and use the device lock.

## Changes in this update

- Default new full backups exported to shared storage use age passphrase encryption (.tar.gz.age). No custom cipher implementation or stored password. Passphrases are entered at age's terminal prompt, not command arguments/history. Temporary plaintext stays in owner-only Termux directories and is removed on ordinary success/failure. Flash storage/memory cannot be promised securely erased. Missing age or failed encryption never falls back to a plaintext export.
- Internal record directories use 0700 and files 0600; existing private records are tightened. Symbolic links in private record paths are refused, rather than followed into other locations. Shared Android storage may not enforce Unix modes, so live records belong inside Termux. Financial CSV exports and Finance-only snapshots now stay inside the private Finance folder. Intentionally exported books/notes/media and old files require separate handling.
- Board server binds only 127.0.0.1 and uses a fresh 192-bit random route per run. Host, Origin and cross-site browser request checks restrict access; writes use allowlisted JSON actions and capped body sizes. Each connection has a timeout and concurrent workers are limited. Localhost does not exclude other apps on the same device. Anyone who obtains the session URL can potentially access it; do not share the URL or screenshot it.
- Sessions expire after 15 minutes without page-load/save activity and after one hour regardless of activity. Explicit lock invalidates the whole session. Browser code attempts to lock and navigate to about:blank after 60 seconds hidden, on expiry/restored cached pages, or when its periodic status check detects the server stopped. Status checks do not keep sessions alive. Mobile browsers can suspend timers, so background blanking is best effort; close the tab and stop the server for reliable user-initiated closure. Display clearing is not a promise to erase browser memory, history, screenshots or device backups. Unsaved forms are discarded on lock.
- Content Security Policy allows only hashed shipped inline scripts/styles, same-origin API connections, and no external assets. Framing, base-URL changes and native form submissions are blocked. Responses disable caching/referrers and isolate cross-origin use. User text is escaped or inserted with textContent.
- Restore validates paths, rejects links/traversal, bounds file counts and expanded sizes, stages privately and checks SQLite integrity before replacing files. A fresh encrypted pre-restore backup is required. Validation does not prove an archive came from its claimed author; only restore backups you trust.
- Financial actions remain transactional and retries retain durable receipts; list updates check revisions and preserve previous bytes. Filesystem and SQLite changes are not one cross-file transaction.

## Important remaining limits

Old plaintext backups/exports are NOT automatically deleted or encrypted. After verifying a new encrypted backup can decrypt, move/remove old copies deliberately, including cloud/file-manager copies and trash. Losing the backup passphrase means no recovery. Keep a safe copy separately; do not send it to an assistant.

No automatic uploads/telemetry are added. RSS, video playback, external links and software installation/updates contact their providers and can expose normal network information. Encryption of backups is not anonymous browsing. Donation destinations deliberately published in the repository are public.

Repository checksums detect accidental mismatch; they are not independent authentication if the repository account itself is compromised. Updates remain manual. Protect the hosting account and review code changes. The checks described here are developer tests and review, not an independent penetration test or security certification.

## Validation and reporting

Tests cover actual age encryption/decryption, wrong passphrases, tampered ciphertext, private permissions, symlink rejection, security-header hashes, same-origin restrictions, idle/absolute expiry, lock, archive bounds and restore safety. Real age integration tests require age on PATH and a Unix PTY. Reader/browser/keyboard behavior still needs target-phone checks after updates.

Report suspected vulnerabilities privately to the maintainer using an available private channel. Do not include live financial records, passwords, private backups or recovery material in public issues.

References: https://github.com/FiloSottile/age and https://age-encryption.org/v1

The optional original-installation security updater patches supported scripts locally and saves private script backups. It does not publish their names or contents. Unknown older backup shortcuts are not assumed safe; use the new encrypted Finance backup entry.


## Toolbox password (0.2.4 beta)

The first launch of an updated public `pocket` asks you to create and repeat a new password/passphrase of at least 12 characters. Typed characters are hidden. Each new terminal session asks for that password again before opening records. This password is separate from all encrypted-backup passphrases; changing one does not change the others. The stored verifier uses a random salt and scrypt; the password itself is not saved.

Exit normally or press Ctrl+] to lock. `pocket-lock` requests a lock from another terminal. `pocket-password` changes the toolbox password after checking the current password. Five minutes without terminal input or browser interaction locks the session. Browser pointer/keyboard/scroll events extend activity; background status polling does not. Reading a static page for five minutes can therefore lock it. Browser Lock now also closes the protected toolbox session. Unsaved work can be lost when locking; complete a save before leaving. Browser hidden-tab locking remains in place. Close all old sessions after installing: an already running copy cannot retroactively become password protected.

Original-menu users update their checkout, then run `python "$HOME/pocket-security-update/finance/install_passwords.py"`. It guards supported original menu/Finance/RSS/record scripts and shell/Python widgets, reports unrecognized entries, and preserves previous scripts privately on the device. It does not modify financial/journal records. Public users rerun `install.sh` instead.

**Security scope:** this is an interface lock, not file encryption. It blocks ordinary entry through the guarded launchers and terminates their process group on lock. Someone able to use the Termux shell can read working files, edit the program, reset its local password verifier, or run an unguarded copy. Root access, malware, external readers, screenshots, shell history, copies/exports in shared storage and apps outside the protected process group are not protected by this lock. A terminal process killed by Android cannot clear a screenshot or control external apps. Keep the Android device lock enabled. Existing `.age` backups remain encrypted; encrypting all live working records is a separate unfinished feature. Do not describe this release as an encrypted vault.

The lock verifier lives in Termux internal storage at `~/.config/pocket-toolbox-lock`, separate from record backups. On a fresh device, restore compatible records and choose a new toolbox password; old encrypted-backup passphrases are still needed to decrypt those backups. There is no online recovery service. Editing/removing a verifier is possible for someone with shell access; this is why it must not be confused with data encryption.
