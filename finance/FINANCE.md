# Pocket Finance 0.2.0 beta

Included in public Pocket Toolbox. Install/update using the root README and install.sh. The separate original-menu compatibility installer is not part of this public package.

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
