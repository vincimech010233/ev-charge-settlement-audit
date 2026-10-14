#!/usr/bin/env python3
"""Offline reconciliation of EV charge-session exports and invoice lines."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

MAX_INPUT_BYTES = 25 * 1024 * 1024
MAX_ROWS = 100_000
CENT = Decimal("0.01")
ZERO = Decimal("0")
SESSION_COLUMNS = ("session_id", "started_at", "site_id", "energy_kwh", "expected_total_eur")
INVOICE_COLUMNS = ("invoice_line_id", "session_id", "billed_kwh", "charged_total_eur")


class InputError(ValueError):
    """A file cannot be safely interpreted using the documented schema."""


@dataclass(frozen=True)
class Record:
    row_number: int
    values: dict[str, str]


def _read_rows(path: Path, required: tuple[str, ...]) -> tuple[list[Record], str]:
    try:
        with path.open("rb") as source:
            payload = source.read(MAX_INPUT_BYTES + 1)
        if len(payload) > MAX_INPUT_BYTES:
            raise InputError(f"{path}: file exceeds {MAX_INPUT_BYTES} bytes")
        digest = hashlib.sha256(payload).hexdigest()
        text = payload.decode("utf-8-sig")
        with io.StringIO(text, newline="") as source:
            reader = csv.DictReader(source, strict=True)
            if reader.fieldnames is None:
                raise InputError(f"{path}: missing CSV header")
            if len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise InputError(f"{path}: duplicate CSV column names")
            missing = sorted(set(required) - set(reader.fieldnames))
            if missing:
                raise InputError(f"{path}: missing required columns: {', '.join(missing)}")
            records: list[Record] = []
            for row in reader:
                if len(records) >= MAX_ROWS:
                    raise InputError(f"{path}: more than {MAX_ROWS} data rows")
                if None in row:
                    raise InputError(f"{path}: row {reader.line_num}: more values than header columns")
                records.append(Record(reader.line_num, {k: (v or "").strip() for k, v in row.items() if k is not None}))
        return records, digest
    except (OSError, UnicodeError, csv.Error) as exc:
        raise InputError(f"{path}: {exc}") from exc


def _decimal(value: str, label: str, row: int, *, nonnegative: bool = True) -> Decimal:
    if len(value) > 64:
        raise ValueError(f"row {row}: {label} is too long")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"row {row}: {label} is not a decimal number") from exc
    if not number.is_finite():
        raise ValueError(f"row {row}: {label} must be finite")
    if number and (number.adjusted() > 14 or number.adjusted() < -12):
        raise ValueError(f"row {row}: {label} is outside the supported numeric range")
    if nonnegative and number < ZERO:
        raise ValueError(f"row {row}: {label} must be non-negative")
    return number


def _session_valid(record: Record) -> dict[str, object]:
    row = record.values
    for key in ("session_id", "started_at", "site_id"):
        if not row[key]:
            raise ValueError(f"row {record.row_number}: {key} is required")
    try:
        datetime.fromisoformat(row["started_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"row {record.row_number}: started_at must be ISO 8601") from exc
    return {
        "session_id": row["session_id"],
        "started_at": row["started_at"],
        "site_id": row["site_id"],
        "energy_kwh": _decimal(row["energy_kwh"], "energy_kwh", record.row_number),
        "expected_total_eur": _decimal(row["expected_total_eur"], "expected_total_eur", record.row_number),
        "row_number": record.row_number,
    }


def _invoice_valid(record: Record) -> dict[str, object]:
    row = record.values
    for key in ("invoice_line_id", "session_id"):
        if not row[key]:
            raise ValueError(f"row {record.row_number}: {key} is required")
    return {
        "invoice_line_id": row["invoice_line_id"],
        "session_id": row["session_id"],
        "billed_kwh": _decimal(row["billed_kwh"], "billed_kwh", record.row_number),
        "charged_total_eur": _decimal(row["charged_total_eur"], "charged_total_eur", record.row_number),
        "row_number": record.row_number,
    }


def _money(value: Decimal) -> str:
    return format(value.quantize(CENT), "f")


def _number(value: Decimal) -> str:
    return format(value.normalize(), "f") if value else "0"


def _safe_csv_cell(value: object) -> str:
    """Prevent spreadsheet applications from evaluating untrusted cells as formulas."""
    text = str(value)
    probe = text
    while probe and (probe[0].isspace() or unicodedata.category(probe[0]) in {"Cc", "Cf"}):
        probe = probe[1:]
    if probe.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def audit(session_path: Path, invoice_path: Path, *, amount_tolerance: Decimal = CENT,
          energy_tolerance: Decimal = Decimal("0.01")) -> dict[str, object]:
    if (not amount_tolerance.is_finite() or not energy_tolerance.is_finite()
            or amount_tolerance < ZERO or energy_tolerance < ZERO
            or amount_tolerance.adjusted() > 14 or energy_tolerance.adjusted() > 14):
        raise InputError("tolerances must be finite, non-negative, and within the supported numeric range")
    session_records, session_hash = _read_rows(session_path, SESSION_COLUMNS)
    invoice_records, invoice_hash = _read_rows(invoice_path, INVOICE_COLUMNS)
    findings: list[dict[str, object]] = []

    def finding(code: str, session_id: str, detail: str, *, source: str = "", amount: Decimal = ZERO,
                energy: Decimal = ZERO) -> None:
        findings.append({"code": code, "session_id": session_id, "source": source, "detail": detail,
                         "amount_eur": _money(amount), "energy_kwh": _number(energy)})

    sessions: dict[str, list[dict[str, object]]] = defaultdict(list)
    invoices: dict[str, list[dict[str, object]]] = defaultdict(list)
    bad_session = bad_invoice = 0
    for record in session_records:
        try:
            item = _session_valid(record)
            sessions[str(item["session_id"])].append(item)
        except ValueError as exc:
            bad_session += 1
            finding("invalid_session_row", record.values.get("session_id", ""), str(exc), source="session_register")
    for record in invoice_records:
        try:
            item = _invoice_valid(record)
            invoices[str(item["session_id"])].append(item)
        except ValueError as exc:
            bad_invoice += 1
            finding("invalid_invoice_row", record.values.get("session_id", ""), str(exc), source="invoice")

    duplicate_sessions = {key for key, rows in sessions.items() if len(rows) > 1}
    duplicate_invoices = {key for key, rows in invoices.items() if len(rows) > 1}
    invoice_line_ids = Counter(str(item["invoice_line_id"]) for rows in invoices.values() for item in rows)
    duplicate_line_ids = {key for key, count in invoice_line_ids.items() if count > 1}
    for key in duplicate_sessions:
        finding("duplicate_session_id", key, f"{len(sessions[key])} session-register rows; matching withheld", source="session_register")
    for key in duplicate_invoices:
        finding("multiple_invoice_lines", key, f"{len(invoices[key])} invoice rows; matching withheld", source="invoice")
    for key in duplicate_line_ids:
        finding("duplicate_invoice_line_id", "", f"Invoice line ID {key!r} occurs {invoice_line_ids[key]} times", source="invoice")

    matched = 0
    amount_variance = ZERO
    energy_variance = ZERO
    for key in sorted(set(sessions) | set(invoices)):
        if key in duplicate_sessions or key in duplicate_invoices:
            continue
        session_rows = sessions.get(key, [])
        invoice_rows = invoices.get(key, [])
        if session_rows and not invoice_rows:
            session = session_rows[0]
            finding("missing_invoice_line", key, "Session register has no matching invoice line", source="invoice",
                    amount=session["expected_total_eur"], energy=session["energy_kwh"])
        elif invoice_rows and not session_rows:
            invoice = invoice_rows[0]
            finding("unexpected_invoice_line", key, "Invoice line has no matching session-register row", source="session_register",
                    amount=invoice["charged_total_eur"], energy=invoice["billed_kwh"])
        elif session_rows and invoice_rows:
            matched += 1
            session, invoice = session_rows[0], invoice_rows[0]
            delta_amount = invoice["charged_total_eur"] - session["expected_total_eur"]
            delta_energy = invoice["billed_kwh"] - session["energy_kwh"]
            amount_variance += delta_amount
            energy_variance += delta_energy
            if abs(delta_amount) > amount_tolerance:
                finding("amount_mismatch", key, "Invoice total differs from session-register expected total", source="invoice",
                        amount=delta_amount, energy=ZERO)
            if abs(delta_energy) > energy_tolerance:
                finding("energy_mismatch", key, "Billed energy differs from session-register energy", source="invoice",
                        amount=ZERO, energy=delta_energy)

    findings.sort(key=lambda item: (str(item["session_id"]), str(item["code"]), str(item["source"]), str(item["detail"])))
    counts = Counter(str(item["code"]) for item in findings)
    return {
        "schema_version": 1,
        "inputs": {
            "session_register_sha256": session_hash,
            "invoice_sha256": invoice_hash,
            "session_rows": len(session_records),
            "invoice_rows": len(invoice_records),
        },
        "tolerances": {"amount_eur": _money(amount_tolerance), "energy_kwh": _number(energy_tolerance)},
        "summary": {
            "matched_sessions": matched,
            "session_register_ids": len(sessions),
            "invoice_session_ids": len(invoices),
            "invalid_session_rows": bad_session,
            "invalid_invoice_rows": bad_invoice,
            "finding_count": len(findings),
            "findings_by_code": dict(sorted(counts.items())),
            "matched_amount_variance_eur": _money(amount_variance),
            "matched_energy_variance_kwh": _number(energy_variance),
        },
        "findings": findings,
    }


def write_report(report: dict[str, object], json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    fields = ("code", "session_id", "source", "detail", "amount_eur", "energy_kwh")
    with csv_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        text_fields = {"code", "session_id", "source", "detail"}
        writer.writerows({key: (_safe_csv_cell(row.get(key, "")) if key in text_fields else row.get(key, ""))
                          for key in fields} for row in report["findings"])


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile EV session-register CSV against invoice-line CSV (offline).")
    parser.add_argument("--sessions", type=Path, required=True, help="session register CSV")
    parser.add_argument("--invoice", type=Path, required=True, help="invoice lines CSV")
    parser.add_argument("--json", type=Path, default=Path("reconciliation.json"), help="JSON report output")
    parser.add_argument("--exceptions", type=Path, default=Path("exceptions.csv"), help="CSV findings output")
    parser.add_argument("--amount-tolerance", type=Decimal, default=CENT, help="absolute EUR tolerance (default 0.01)")
    parser.add_argument("--energy-tolerance", type=Decimal, default=Decimal("0.01"), help="absolute kWh tolerance (default 0.01)")
    parser.add_argument("--fail-on-exceptions", action="store_true", help="return 2 after writing outputs when findings exist")
    args = parser.parse_args(argv)
    try:
        inputs = {args.sessions.resolve(), args.invoice.resolve()}
        outputs = {args.json.resolve(), args.exceptions.resolve()}
        if len(outputs) != 2:
            raise InputError("JSON and exceptions outputs must be different files")
        if inputs & outputs:
            raise InputError("output paths must not overwrite either input file")
        report = audit(args.sessions, args.invoice, amount_tolerance=args.amount_tolerance,
                       energy_tolerance=args.energy_tolerance)
        write_report(report, args.json, args.exceptions)
    except (InputError, OSError) as exc:
        print(f"charge-audit: error: {exc}", file=sys.stderr)
        return 1
    summary = report["summary"]
    print(f"matched={summary['matched_sessions']} findings={summary['finding_count']} "
          f"amount_variance_eur={summary['matched_amount_variance_eur']}")
    return 2 if args.fail_on_exceptions and summary["finding_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
