# Changelog

## 0.2.4 beta — 2026-10-25

- Added password-gated terminal sessions using salted scrypt password verification. First launch creates a separate toolbox password; each new session requires it.
- Exit, Ctrl+], the pocket-lock command, inactivity and browser Lock now terminate the protected process group and its board servers. Browser interaction extends activity without background status polls keeping a session alive.
- Added an original-installation password installer for recognized menus, record scripts and widgets. Local backups preserve previous scripts; records and existing backup passwords are unchanged.
- This is explicitly an **interface lock**, not encryption of working files or a security boundary against access to the Termux shell. Working-record encryption is still pending.

## 0.2.3 beta — 2026-10-25

- Prepared JSON statements now preserve source evidence and review events alongside explicitly classified cash movements. Preview, stable event receipts, changed-ID rejection, atomic saves and pre-import snapshots protect records.
- Funding, historical debt payments, matched advances/reimbursements and investment cash stay separate from ordinary income/expenses. Unknown historical opening/debt balances and crypto basis are not inferred.
- Import menu R reads saved statement events. Full-table exports and compatible snapshot restores preserve them. Available through the existing public Finance 21 / original Finance 23 import action.

## 0.2.2 beta — 2026-10-25

- Added local CSV/XLSX income/expense import with worksheet/header selection, column matching, explicit formats/units, previews, row exclusions and confirmation.
- Stable source identities, possible-duplicate review, validation and private pre-import snapshots protect existing records; database saves are atomic.
- Available at public Finance 21 and original Finance 23 through the local updater. No new dependencies or uploads.

## 0.2.1 beta — 2026-10-25

- Original-menu local updater: Finance backup submenu now includes Create, Verify, Share and Show folder; rerunning updates the existing menu label without duplicating entries.

- Backup usability: named Create/Verify/Share/Show folder actions, generated-passphrase guidance, immediate verification after creation, and verification before Android sharing. No manual verification snippets are required.

- New full backups use age passphrase encryption; restore decrypts privately and checks expanded-size/member limits.
- Owner-only private files/directories, symlink refusal and private Finance exports.
- Sessions expire after idle/absolute limits, with Lock now and best-effort background blanking.
- Hashed CSP, anti-framing/cross-origin headers, bounded connections and security tests including real age round trips.
- Added a documented threat model; live records remain unencrypted and old plaintext copies are not removed.

## 0.2.0 — 2026-10-25 (beta)

- Added full Personal/Business Finance, inventory and production costing, linked invoices/payments/returns, goals, manual portfolios and trading records.
- Added three local browser boards with record-entry forms, financial Review → Save, fresh reports and duplicate-request protection.
- Public titles, business names, currency and paths come from user settings. Public packaging excludes the separate compatibility installer.
- Preserved earlier 0.1 records, added explicit idempotent import and a read-only old-ledger view.
- Backups now snapshot Finance SQLite databases; old backups without Finance cannot silently mix with new Finance records.
- Updated installer, documentation and customization form. Public installs start blank.

## 0.1.0

Initial configurable terminal toolbox with books, notes, journals, RSS, project records and backups.
