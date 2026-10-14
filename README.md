# EV Charge Settlement Audit

An offline, vendor-neutral Python utility that reconciles an EV charging session register against line-level supplier invoice exports. It produces a deterministic JSON summary and CSV exception ledger for a finance or fleet-operations reviewer.

## Business need and users

Charging invoices may not read as a simple sum of the session list: suppliers can include fees outside session detail, while session detail comes from charge-point operator records. Finance teams at fleet operators, charge-point operators, and mobility-service providers need to identify which records agree and which deserve investigation. Official Volvo and BMW charging support pages document this invoice/session mismatch question; see [Evidence and novelty](docs/EVIDENCE.md).

Target users are accounts-payable analysts, fleet-energy managers, and CPO/MSP billing operations staff who already have authorized CSV exports. The project does not claim a measured customer saving or legal-compliance result.

## Features

- Match session-register rows to invoice lines by exact `session_id`.
- Report missing invoice lines, invoice-only sessions, duplicate session IDs, multiple invoice lines, duplicate line IDs, invalid rows, and energy or amount variances.
- Apply explicit absolute EUR and kWh tolerances using decimal arithmetic.
- Include SHA-256 hashes, row counts, finding counts, and matched signed variances in the JSON report.
- Neutralize spreadsheet-formula prefixes in the CSV exception ledger; the JSON report retains machine-readable identifiers.
- Keep processing local; use Python's standard library only; never connect to chargers, accounts, payment providers, or the network.
- Exit with status 2 on findings when `--fail-on-exceptions` is enabled, so the utility can be used in a manual close checklist.

## Architecture and requirements

Python 3.10 or later. The command-line entry point validates bounded UTF-8 CSV inputs, normalizes numeric values with `decimal.Decimal`, groups records by exact session ID, writes JSON and CSV outputs, and prints a short summary. Input files are limited to 25 MiB and 100,000 rows each. No package install or database is required. GitHub Actions is configured for Python 3.10, 3.12, and 3.13 using SHA-pinned actions; hosted workflow status is **NOT_VERIFIED** because this project has not been published.

## Installation and use

```sh
cd ev-charge-settlement-audit
python3 charge_audit.py \
  --sessions examples/session_register.csv \
  --invoice examples/invoice_lines.csv \
  --json reconciliation.json \
  --exceptions exceptions.csv \
  --fail-on-exceptions
```

The fictional example has three register sessions and three invoice lines: one session amount differs, one register session is absent from the invoice, and one invoice session has no register record. The command writes both reports before returning 2 because exceptions exist. The JSON report records one matched session and the signed amount variance for that matched session; missing and invoice-only exposure are separate findings.

### Input schemas

`--sessions` requires `session_id,started_at,site_id,energy_kwh,expected_total_eur`. `started_at` must be ISO-8601; amounts and energy must be finite and non-negative.

`--invoice` requires `invoice_line_id,session_id,billed_kwh,charged_total_eur`. An invoice line is expected to represent one session. Multiple lines mapped to one session are surfaced for human review rather than automatically aggregated. Additional input columns are ignored; the required column names and identifiers are case-sensitive.

```sh
python3 charge_audit.py --help
python3 -m unittest discover -s tests -v
```

## Security and data handling

The tool makes no network requests and stores no credentials. It does not need driver names, vehicle identifiers, card data, or personal contact details; exclude them from exports. Reports contain source record IDs, site IDs, aggregate monetary/energy values, and file hashes, which can still be commercially sensitive. Store and share them under the organization's normal access controls. Output paths must be distinct from each other and from both inputs. The tool does not approve invoices, change records, or submit payments.

Only use data you own or are authorized to process. Example inputs are synthetic. The utility is a review aid; humans remain responsible for contract interpretation, tax treatment, adjustments, and invoice approval.

## Tests and measured results

Tests cover clean matches, missing and extra invoice records, amount and energy variances, duplicate records, invalid and non-finite numbers, tolerance boundaries, input overwrite prevention, spreadsheet-formula injection, numeric CSV output, deterministic output, and CLI report/exit behavior. On Python 3.12.3, all 13 tests passed. The fictional example produced 2 matched sessions, 3 findings, and EUR 0.25 signed variance across matched sessions; the command wrote both reports and returned the expected exception status 2. Exact execution output is recorded in `results/`. Hosted CI is **NOT_VERIFIED** until a new repository exists and the workflow runs there.

## Limitations

- The session register's `expected_total_eur` is treated as the comparison baseline; the tool does not calculate tariffs, taxes, roaming, idle fees, or exchange rates.
- Exact IDs are required; it does not guess fuzzy matches or merge invoice components.
- Amount variance only summarizes unambiguous matched sessions; it is not a full invoice grand-total reconciliation. Missing and extra records are individually exposed as findings.
- CSV schema normalization from vendor-specific exports remains an operator-controlled preprocessing step.
- No production, privacy, accounting, regulatory, or commercial validation has been performed.

## License

MIT. See [LICENSE](LICENSE).

## Verifiable evidence

Official sources and the novelty assessment are linked in [docs/EVIDENCE.md](docs/EVIDENCE.md). Evidence of local validation is kept in `results/`; no GitHub URL, commit, PR, CI run, or release exists yet.
