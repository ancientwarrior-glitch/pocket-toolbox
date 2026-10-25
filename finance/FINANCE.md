# Pocket Finance 0.2.3 beta

Included in public Pocket Toolbox. Install/update using the root README and install.sh. The separate original-menu compatibility installer is not part of this public package. A generic `install_security.py` can harden an existing supported installation locally without uploading its scripts; see the root README.

## Start

Open Budget and debts, then Finance 1 to create accounts with actual opening balances/dates and categories. Personal and Business scopes are separate. Records live under ~/.local/share/pocket-toolbox/data/Finance. Finance 18 opens graphs, 19 the business board, and 20 the main dashboard. Titles, currency, folders and project name come from config.json. Currency is chosen before entering records, not an automatic conversion of existing amounts.

Earlier public 0.1 users can import a snapshot of data/budget.sqlite through Finance 12. The source is unchanged; stable identities prevent duplicate imports and changed imported rows require review. Historical movement accounts have unknown opening balances and are excluded from available-balance graphs. Outstanding debts retain payable/receivable direction. Inventory quantities are not invented from old cash records.

## Recordkeeping

Amounts use integer base-currency cents. Quantities use Decimal arithmetic (g, ml, each; compatible kg/l input). Transfers are not income. Reconciliation makes an audited adjustment. Budgets and goal earmarks do not move cash.

Purchases add stock and supplier invoices. Sales remove stock, record cost of goods sold and create receivables. Paid now creates the linked payment: do not enter it again in Cash. Production saves material, labor and overhead costs; later prices do not rewrite saved batch costs. Stock uses moving weighted-average cost. Opening stock creates no payment and must be the first stock event for that item.

Partial payments, customer/supplier returns, refund credits, losses and invoice reversals are supported. Later-period returns are recognized in that period. Tracked business result is not automatically approved net profit: reconcile labor/overhead payments against allocations, equipment and unclassified records before approving distributions. Profit-share payables use an explicitly approved profit figure.

## Boards and forms

Main dashboard: current reads, shopping, notebook batch ages, uploads, journal presence, newest backup file, checklist/status edits, new notes and simple cash entries. Notebook ages do not certify cure/readiness. Newest backup is a file-presence check, not restore verification.

Finance: balances, cash in/out, spending, budgets, goals and manual portfolio values. Forms record cash, budgets, goals/earmarks, dated prices and bill payments/refunds. Business: stock, batches, net sales/cost charts and open bills; forms create items, opening stock, receipts, multi-material production, sales and linked payments/refunds. Financial forms use Review → Save. Corrections, returns, advanced investments and operations without forms remain in the terminal.

Boards run through temporary random URLs on 127.0.0.1, with no remote assets or publishing. Keep Termux open until finished. Saves use allowlisted same-origin JSON requests and fresh SQLite connections. Cash/business saves use durable request receipts in the same transaction; retries do not duplicate entries. List writes preserve metadata, snapshot previous bytes under data/Board-Backups, reject stale revisions and replace files atomically. Avoid simultaneous terminal editing of the same list; external writers do not share the board lock. After the server stops, reopen Dashboard to save again.

## Investments and trading

Spot holdings use moving-average basis per scope/wallet/portfolio, with manual buys/openings/rewards, partial sells, swaps, fee records and cost-preserving transfers. Prices/FX are dated manual inputs. Missing prices remain unknown. Portfolio value is not investment return; exit statistics include partial exits, not full round trips or time-weighted returns. Drawdown uses the realized-result curve.

Trading plans/journal and manual LINEAR contracts are included. No exchange connection, order execution, liquidation model, inverse/quanto contracts, live prices or tax calculations. Normalized trading CSV imports require stable source/row IDs; native exchange exports must be mapped first.

## Backups and limits

Full toolbox backups include Finance via SQLite snapshots. Finance 13/16 backs up/restores Finance alone, validating the snapshot and making a pre-restore backup. Raw CSV tables use cents; readable cash reports format currency. Books, media and referenced screenshots need separate backups. A pre-0.2 full backup without Finance cannot replace a setup that already has Finance, to avoid mixing money records.

This is a multi-year recordkeeping and planning application, not an Excel formula grid. Automatic equipment/cost reconciliation, live read-only exchange adapters, native exchange CSV formats, full-trade grouping and deposit-adjusted market-equity performance remain future work.

## Security update

Full toolbox backups now use age encryption; install/update through install.sh to get age. Finance-only snapshots and CSV exports stay in private Finance/Backups and Finance/Exports. Live records are not an encrypted vault. Boards enforce expiry and browser restrictions; see SECURITY.md. Older plaintext files are not removed automatically.

## CSV/XLSX cash importer

Public Finance 21 (original upgraded menu: 23) provides file selection, worksheet/header choice, column mapping, explicit number/date/unit formats, account choice, paged preview and confirmation. It imports income/expenses only. Existing stable source IDs are skipped; changed IDs block the import. No-ID rows use normalized contents plus occurrence count. Possible matches with existing cash are skipped by default and require explicit row selection to override. Invalid included rows block the whole import; exclude totals/transfers/linked payments or correct the source. New category names are shown before saving. A private pre-import Finance snapshot is retained and cash/categories/import receipts save in one transaction. No formulas, automatic currency conversion or direct .xls support. See root README for limits and duplicate caveats.


## Prepared statements (0.2.3 beta)

The import action also accepts `pocket-statement-v1` JSON. Choose a file, read the paged preview, then type `IMPORT` to confirm. Enter `R` in the file-selection prompt to read saved source and review records. No file is uploaded.

A statement contains `format`, a stable `source`, `currency` matching the Finance base currency, optional `notes`, and an `events` array (1–10,000 events; file at most 16 MiB). Each event needs a unique stable `id`, ISO `date`, `description`, `scope` (`Personal`/`Business`) and `kind`. Cash amounts are signed decimal strings with at most two decimals. Optional fields are `category`, `party`, `group`, `note` and an `evidence` object. No arbitrary actions or code are executed.

Supported kinds:

- `Income` / `Expense`: ordinary cash, optional categories.
- `Capital`: positive funding cash, linked to a fully received Capital invoice; excluded from sales/profit.
- `DebtPayment`: historical negative debt-payment cash. The source record preserves the creditor and an explicit unknown-balance status. It does **not** reduce an existing invoice or establish an outstanding debt. Reconcile the opening/current debt separately when known.
- `Advance` / `Reimbursement`: one negative advance plus one or more later positive repayments with the same `group` and scope. Creates a receivable and links repayments; overpayment is rejected. Each file must carry the complete group, including on repeat import.
- `Investment`: signed investment cash observation only. It creates no asset quantity, cost basis, fee, trade gain or position. Do not separately import the same cash leg as a trade.
- `Review`: retains original evidence without posting cash. Use for provider-only lines, unresolved cancellations and crypto observations.

Historical accounts are created with names ending in `opening balance unknown`; their movements are useful history but their totals are not available cash. The dashboard excludes these accounts from established balances. Capital, debt payments, advances, reimbursements and investments remain outside ordinary money-in/out totals. Ordinary purchases with unknown purpose can be explicitly imported as uncategorized; no stock items or business use are inferred.

Exact source/event IDs skip on repeat. Changed IDs with changed contents are blocked; potential existing cash duplicates block the import for reconciliation. Stable IDs cannot detect every overlap across independently prepared files, so review sources carefully. The importer saves a private pre-import SQLite snapshot and commits the entire selected file atomically. Full table exports include `statement_events.csv`. Ordinary imported income/expenses can be corrected with the cash editor; funding and reimbursement invoices use linked invoice corrections. Review observations are preserved read-only in this beta; replacing a prepared source file does not edit already imported records.

A minimal generic example:

```json
{"format":"pocket-statement-v1","source":"my-provider-history","currency":"MXN","events":[{"id":"example-1","date":"2026-01-01","description":"Example expense","scope":"Personal","kind":"Expense","amount":"-10.00","category":"Food"}]}
```
