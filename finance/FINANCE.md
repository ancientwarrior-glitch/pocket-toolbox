# Pocket Finance — 0.2.0-beta.4 for the ORIGINAL toolbox

This is an additional, offline financial record system for people running the original `menu` scripts. The stable public `pocket` starter is not replaced. Finance is a set of financial workflows and reports, not an Excel cell-grid/formula editor.

## Install

Run each command separately in Termux:

```bash
pkg install -y git
git clone --depth 1 --branch finance-beta-original https://github.com/ancientwarrior-glitch/pocket-toolbox.git "$HOME/pocket-finance-beta"
python "$HOME/pocket-finance-beta/finance/install_original.py"
```

Then type `finance`. You do not run the repository's top-level `install.sh` for this add-on.

The installer checks compatible menu/function markers before changing existing scripts. It backs up the old menu, budget scripts, original budget database and purchase CSV under `~/Everyday/Finance/Installer-Backups/<timestamp>/`. It adds a new numbered Finance entry without assuming which numbers you already use. It redirects the old budget, project purchase and finance-correction buttons to the new system. Existing books, RSS, widgets, journal, videos and other menus stay as they are. Close and reopen a running menu to see its new option. A conflicting unrelated `finance` command stops installation.

No phone records are uploaded. Finance source files are copied to `~/bin/pocket-finance`; private records live in `~/Everyday/Finance/finance.sqlite`. The original SQLite database and CSV are preserved unchanged.

## First use

1. **Option 12: Import original records once.** This imports the original `~/Everyday/Jabones-Yayo/budget.sqlite` plus `purchases.csv`. It reads sources without changing them, keeps import identities, and rejects changed source records rather than silently duplicating money. Already-paid debt installments remain historical cash movements; only the remaining debt becomes a payable/receivable. Invalid dates/amounts stop the entire import for review. Do not copy the same records in manually as well.
2. **Option 1: Create actual accounts.** Name your cash/wallet accounts; enter their real opening balances and dates. An opening balance means the amount at the START of that day. Imported historical movements use explicitly labeled accounts with UNKNOWN opening balances. Their net movement is not your available cash, and should not be added to real cash balances.
3. Add Personal and Business categories. They can have the same names but remain separate.
4. **Option 4:** set a plan for any month. Balances/history do not reset at year end.
5. For existing business stock, add the item and use **Inventory → Record opening stock already owned**. This establishes starting quantity/value without counting an old purchase/payment twice. Enter zero cost only deliberately; it affects subsequent cost/profit reports.

Use the new Finance system for subsequent financial records. Its database is separate from the old logs, and changes are not synchronized back to the old SQLite/CSV. The installer redirects common financial menu entry points. The original toolbox-wide search still searches the old financial snapshot; Finance's own Search covers all new finance tables. Existing books, journals and other unrelated search behavior remains available.

## Menus

1. Accounts, opening balances, categories.
2. Income/expenses, two-account transfers, counted-balance reconciliation.
3. Reports over any date range, including years.
4. Monthly plans versus actual cash movements by category.
5. Bills, loans, capital contributions/distributions, receivables, partial payments, whole-invoice reversals, partial customer/supplier returns and refunds.
6. Materials/products, stock receipts, batch estimates/production, sales, losses, opening stock.
7. Goals, reserved/committed amounts, contribution scenarios, approved profit shares.
8. Spot/crypto positions, buys/openings/rewards, sales, swaps, wallet transfers, dated manual prices, portfolio reports.
9. Trade plans, status, journal/screenshot paths, manual linear contracts and settlement.
10. Search all finance records and audit entries.
11. Correct or void standalone cash entries; linked events use their originating workflow.
12. Import original records.
13. Consistent SQLite snapshots.
14. Export all tables to CSV.
15. Help.
16. Restore a compatible finance snapshot, preserving a pre-restore copy.
17. Import normalized trading CSV.
18. Graphs / visual dashboard.
19. Jabones Yayo / business board.
20. Main toolbox visual dashboard.

## Main toolbox visual dashboard

After updating, the original Dashboard button (normally main menu 11) opens the visual home board. Finance option 20 also opens it. The installer saves the previous `~/bin/toolbox-home.py` and adds a small launcher; calling that script with `help` still runs the original terminal guide. Reinstalling does not duplicate the launcher. If the original script is absent, Finance option 20 remains available.

The home board reads the original formats shown by the user's dashboard: `Everyday/Jabones-Yayo/reading-log.json` (records with a `status` field), `Everyday/Organizer/shopping.json`, `uploads.json`, `batch-dates.json`, and batch-note filenames under `Everyday/Jabones-Yayo/Batches`. It displays current reads, unchecked shopping, batch ages, waiting uploads and saved publication/download-check counts. It only checks today's journal file exists; journal and batch-note bodies are not exposed.

The latest `.tar.gz`, `.tgz` or `.zip` file in `~/storage/downloads/Termux-Backups` is chosen by modification time. This is a file-presence check, not verification that the archive is complete or restorable. Missing records show empty states; unreadable/wrong top-level JSON formats show a warning. No original records are edited or migrated.

Finance/business links serve their read-only snapshots under the same random local route. Keep the Termux screen open while using links, then press Enter there to stop the server. Reopen the dashboard after changing records. Terminal menus still handle editing, opening books and tracking statuses. These boards use the original personal paths and names on this beta branch; they are not yet the generic public starter release.

## Business board

Option 19 opens a read-only local board with searchable materials and finished stock, inventory value at recorded cost, monthly net sales versus cost of goods sold, saved production costs and batch ages, and business bills/credits to collect or pay. Its records come from Finance options 5 and 6. Older Jabones batch notes are separate and are not automatically imported.

The stock list flags zero stock; it does not invent low-stock thresholds. Each quantity retains its own unit. Batch age bars have a temporary adjustable planning marker; reaching that marker does not certify soap cure or readiness. All products use the same age display, so set an appropriate marker for the batch you are reviewing. Bills have no stored due dates and are not labeled overdue. Net sales include credit sales and dated returns/reversals, rather than cash collection. Credits owed after overpayment/returns are shown separately on each bill and included in the corresponding amounts to collect/pay. Future-dated stock, batches, bills and payments are excluded from the current snapshot.

Update using the commands below and choose 19. Existing records are retained.

## Graphs

Option 18 opens a read-only browser dashboard with cash balances, money-in/money-out bars, category outflows, portfolio values, expense-budget progress and savings goals. Filter Personal/Business, account and period; tap graph points for exact figures. It uses saved records and manual prices, so it works offline. Unknown valuations are gaps rather than made-up zeros, and empty logs show explicit empty states. Imported accounts with unknown opening balances are excluded from the cash-balance graph.

The dashboard starts a small temporary server bound only to `127.0.0.1`, serving one random URL. It has no external scripts, fonts, CDNs or price calls. Keep the terminal screen open until the page loads; return and press Enter when finished to stop the server. The already loaded page can continue filtering its in-memory snapshot. Reopen Graphs to refresh records. No screenshots or report exports are uploaded.

To update an already installed beta, exit Finance, then run:

```bash
git -C "$HOME/pocket-finance-beta" pull --ff-only
python "$HOME/pocket-finance-beta/finance/install_original.py"
finance
```

The update copies the chart module alongside the existing engine/UI and keeps the finance database intact.

## Money and business accounting

Base currency is MXN for this original-menu beta. All monetary records use integer cents. Quantities use Decimal arithmetic with up to 18 decimal places. Materials use grams, milliliters or each; compatible kg/l input converts to base units. There is no automatic live currency conversion; investment quotes can record a dated manual quote-to-base exchange rate.

Purchasing stock creates one supplier invoice and one stock movement. Paying some/all of that invoice creates the cash movement once. Recording production consumes material/packaging quantities and creates finished stock. Moving weighted-average stock values are used, with saved material, labor and overhead costs for each production batch. Later ingredient price changes do not rewrite that batch's cost. Record stock events in chronological order per item; backdated moves are rejected when they would invalidate later cost calculations.

A product sale records the sale/receivable and cost of goods sold; collecting money is a payment, not a second sale. Credit/partial payments are supported. Whole-sale reversals restore stock and refund recorded payments to their original accounts. Partial customer returns restore the original sold-stock cost, reduce the receivable and create a refund credit if money was already collected. Partial supplier returns remove currently available stock at its current recorded cost and apply an agreed supplier credit; any credit versus stock-cost difference is reported as supplier-return variance. Refunds can be paid/received in installments through the credit-balance menu. A later-period return is recognized in its return period rather than deleting the earlier period's revenue. Inventory losses reduce quantity/value without inventing a cash payment.

The business report is explicitly a **tracked result**, not automatically approved net profit. It includes recorded sales minus saved sold-stock cost, recorded operating costs and inventory losses. Labor/overhead allocated to production flow through sold-stock cost. Cash wage/overhead funding must be reconciled against those allocations; equipment depreciation, undocumented costs and unclassified imported entries require review. Otherwise costs could be omitted or counted twice. Capital/loan movements are not sales or ordinary operating expenses.

Profit shares take an explicitly reconciled and approved net-profit figure, recipient and agreed percentage. For example, the user can enter their agreed 5% after expenses and their own pay. The program does not declare a provisional tracked result distributable. A distribution is a payable capital movement, not another operating expense. A duplicate recipient/period record is rejected.

Goal reserves/commitments are planning earmarks, not transfers or expenses. They do not enforce that sufficient actual cash exists; compare them against reconciled accounts before spending. Scenarios use user-entered nominal annual rate divided by 12 and month-end contributions, without fees or taxes.

## Crypto and trading rules

Positions are separated by scope, wallet, portfolio and asset. Long-term holdings and active trades can be separate portfolios. This beta uses **moving weighted-average cost basis per position**, for analysis; it does not claim jurisdiction-specific tax treatment.

- Acquisition fees entered in base currency are included in cost basis. Quantity received is the NET quantity.
- A Sell means proceeds leave the tracked portfolio; optionally credit a cash account in the same event. Use a Swap into a tracked USDT/USD/etc. position when proceeds stay inside the portfolio.
- A Swap realizes the disposed asset's result at the user-entered base-currency fair value and starts the received asset at that value. Additional swap fees supported here are paid outside the portfolio and capitalized into the received basis. You can link that outside fee payment to a cash account in the same event, avoiding a second expense entry.
- A sale fee can be valued in base currency and paid from another tracked asset. The fee asset's quantity and cost basis are removed, including its disposal result. This is tested separately from simple fees deducted from sale proceeds.
- Own-wallet transfers preserve basis and do not create a trading gain. The network-fee quantity is paid in the same asset and valued at disposed cost basis. Transfer destinations must have the same asset and scope. Transfers between portfolio labels preserve basis and record matching allocation flows at carried cost; those flows are not market-equity performance returns. Do not manufacture a sell/buy merely to rename a holding.
- Rewards/airdrop/distribution receipts use the Reward event with an explicit user-entered receipt value. Reward income is reported separately; the same value becomes cost basis.
- Prices retain their date, quote currency and manual exchange rate. Reports use the latest recorded price on or before the requested date. A missing price remains unknown; an old price is displayed with its date, not described as live.
- Statistics report realized gains, unrealized gains, fees, reward income, average winning/losing exit, exit-event win rate, expectancy and realized-result-curve drawdown. Partial exits count as exit events. These are not full-round-trip trade statistics, time-weighted return or market-equity drawdown.
- Trade plans record thesis/timeframe/conditions, side, quantity, entry, stop, target, planned risk/reward, status and a screenshot path. Journal notes can record reasons and lessons. Screenshot references are paths, not copied images.
- Manual LINEAR contracts record multiplier, quantity, side, entry, collateral, fees, closing price, funding/borrowing adjustment and realized result. Prices and settlement values must already be in the base currency. Collateral is informational and does not automatically move account cash. These records are separate from spot portfolios. Inverse/quanto contracts, partial contract closes and automatic liquidation modeling are not implemented.

## Trading imports

`trades-template.csv` is a normalized import format, not a promise to understand every exchange's native export. Map the exchange's actual columns into the template. Preserve stable `source` and `id` values so repeated files cannot duplicate trades. Required columns:

`source,id,date,event,scope,wallet,portfolio,asset,quantity,total_base,fee_base`

Supported CSV events: Buy, Sell, Opening, Reward. Monetary values are decimal base-currency units, not cents. Quantity is net asset quantity. Events must be chronological per position. A Sell's proceeds leave the portfolio; it does not automatically post to a cash account through CSV. Swaps and transfers use linked menus. The whole file is one transaction: any invalid or conflicting row rolls back all its new events. Same source/ID/content is skipped; same source/ID with changed content is rejected for review.

## Backup, correction and export

Every logical operation commits its related records together, with a timestamped audit event. Canceling an operation rolls it back. Cash corrections save before/after values. Voids and invoice reversals remain recorded. Stock and trade amendments are intentionally restricted where a casual edit would change dependent costs.

Finance snapshots use SQLite's backup API. Option 16 validates a compatible snapshot and saves the current database before restoring it. The original menu's existing full toolbox backup includes `~/Everyday/Finance` and `~/bin/pocket-finance`, so finance records/code are covered there too. Keep copies off the phone. Referenced screenshots are not included unless separately backed up.

The date-range Reports screen can export a readable cash report with decimal currency amounts in Money in / Money out columns. The separate Export all tables option produces raw database tables with headers; their monetary columns are integer CENTS unless the column itself is a stored unit price/quantity string. Keep raw exports unchanged if making an edited copy. No automatic Excel workbook synchronization is included.

## Rollback of installation

Previous scripts are in `~/Everyday/Finance/Installer-Backups/<timestamp>/` with their numbered filenames. Restore the saved scripts to the corresponding original menu/bin locations, and remove the `finance` launcher only if abandoning the add-on. Do not delete the new finance database just to restore the old menu. Any new finance entries remain in the new database and are not copied back into the old logs automatically.

## Accepted roadmap still beyond this beta

The larger requested financial system includes richer custom views, automated payment/production-cost reconciliation and equipment treatment, configurable profit-distribution schedules, native exchange import adapters, live prices/read-only exchange connections, full trade grouping and deposit-adjusted market-equity performance. These remain explicit follow-up work, not hidden claims of this release. Automatic order execution was separated from the recordkeeping project and is not included. This is not a complete replacement for every Excel feature.

## Validation

Run `python -m unittest discover -s finance -v` from the repository. Tests exercise multi-year cash, transfer rollback, budgets, reconciliation, partial debt payments, stock and saved batch costs, insufficient-stock rollback, credit sales, dated returns, loss, allocations, profit shares, spot fees and third-asset fees, swap/transfer basis, dated FX valuations, missing prices, risk/reward, linear settlement, idempotent/atomic imports, snapshots/restores and original-menu installer preservation/idempotency. Android UI behavior and a migration of the user's actual records still require phone validation.
