# Security and privacy — 0.2.1 beta

## Protected scope

This is a local personal toolbox, not a multi-user server or encrypted live-data vault. Live SQLite/JSON/text records remain readable to the Termux app user. A rooted/compromised device, malware running under the same app account, a compromised browser, stolen unlocked Termux access or malicious source updates are outside these protections. Keep Android and Termux packages updated and use the device lock.

## Changes in this update

- Default new full backups exported to shared storage use age passphrase encryption (.tar.gz.age). No custom cipher implementation or stored password. Passphrases are entered at age's terminal prompt, not command arguments/history. Temporary plaintext stays in owner-only Termux directories and is removed on ordinary success/failure. Flash storage/memory cannot be promised securely erased. Missing age or failed encryption never falls back to a plaintext export.
- Internal record directories use 0700 and files 0600; existing private records are tightened. Symbolic links in private record paths are refused, rather than followed into other locations. Shared Android storage may not enforce Unix modes, so live records belong inside Termux. Financial CSV exports and Finance-only snapshots now stay inside the private Finance folder. Intentionally exported books/notes/media and old files require separate handling.
- Board server binds only 127.0.0.1 and uses a fresh 192-bit random route per run. Host, Origin and cross-site browser request checks restrict access; writes use allowlisted JSON actions and capped body sizes. Each connection has a timeout and concurrent workers are limited. Localhost does not exclude other apps on the same device. Anyone who obtains the session URL can potentially access it; do not share the URL or screenshot it.
- Sessions expire after 15 minutes without page-load/save activity and after one hour regardless of activity. Explicit lock invalidates the whole session. Browser code attempts to lock and navigate to about:blank after 60 seconds hidden, or on expiry/restored cached pages. Mobile browsers can suspend timers, so background blanking is best effort; close the tab and stop the server for reliable user-initiated closure. Display clearing is not a promise to erase browser memory, history, screenshots or device backups. Unsaved forms are discarded on lock.
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
