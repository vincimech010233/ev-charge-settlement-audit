import csv
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from charge_audit import InputError, audit, main, write_report


SESSION_HEADER = "session_id,started_at,site_id,energy_kwh,expected_total_eur\n"
INVOICE_HEADER = "invoice_line_id,session_id,billed_kwh,charged_total_eur\n"


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.sessions = self.root / "sessions.csv"
        self.invoice = self.root / "invoice.csv"

    def tearDown(self):
        self.tmp.cleanup()

    def files(self, sessions: str, invoice: str):
        self.sessions.write_text(SESSION_HEADER + sessions, encoding="utf-8")
        self.invoice.write_text(INVOICE_HEADER + invoice, encoding="utf-8")

    def codes(self, report):
        return [row["code"] for row in report["findings"]]

    def test_clean_reconciliation_and_hashes(self):
        self.files("S1,2026-01-02T10:00:00Z,Depot-A,12.5,4.25\n",
                   "L1,S1,12.5,4.25\n")
        report = audit(self.sessions, self.invoice)
        self.assertEqual(report["summary"]["matched_sessions"], 1)
        self.assertEqual(report["summary"]["finding_count"], 0)
        self.assertEqual(len(report["inputs"]["session_register_sha256"]), 64)

    def test_missing_extra_amount_and_energy_variances(self):
        self.files("S1,2026-01-02T10:00:00Z,D1,10,3\nS2,2026-01-02T11:00:00Z,D1,5,2\n",
                   "L1,S1,11,3.50\nL3,S3,2,0.75\n")
        report = audit(self.sessions, self.invoice)
        self.assertEqual(set(self.codes(report)), {
            "amount_mismatch", "energy_mismatch", "missing_invoice_line", "unexpected_invoice_line"
        })
        self.assertEqual(report["summary"]["matched_amount_variance_eur"], "0.50")
        self.assertEqual(report["summary"]["findings_by_code"]["missing_invoice_line"], 1)

    def test_duplicate_session_and_multiple_invoice_lines_are_not_silently_matched(self):
        self.files("S1,2026-01-02T10:00:00Z,D1,1,1\nS1,2026-01-02T10:00:00Z,D1,1,1\n",
                   "L1,S1,1,1\nL2,S2,1,1\nL3,S2,1,1\n")
        report = audit(self.sessions, self.invoice)
        self.assertEqual(report["summary"]["matched_sessions"], 0)
        self.assertEqual(set(self.codes(report)), {"duplicate_session_id", "multiple_invoice_lines"})

    def test_repeated_invoice_line_id_across_different_sessions_is_reported(self):
        self.files("", "L1,S1,1,1\nL1,S2,1,1\n")
        report = audit(self.sessions, self.invoice)
        self.assertIn("duplicate_invoice_line_id", self.codes(report))

    def test_bad_rows_are_retained_as_findings_while_good_rows_match(self):
        self.files("GOOD,2026-01-02T10:00:00Z,D1,1,1\nBAD,not-a-date,D1,-1,2\n",
                   "L1,GOOD,1,1\nL2,BAD,NaN,2\n")
        report = audit(self.sessions, self.invoice)
        self.assertEqual(report["summary"]["matched_sessions"], 1)
        self.assertEqual(report["summary"]["invalid_session_rows"], 1)
        self.assertEqual(report["summary"]["invalid_invoice_rows"], 1)
        self.assertIn("invalid_session_row", self.codes(report))
        self.assertIn("invalid_invoice_row", self.codes(report))

    def test_tolerance_boundary_is_inclusive_and_negative_tolerance_rejected(self):
        self.files("S1,2026-01-02T10:00:00Z,D1,1,1\n", "L1,S1,1.01,1.01\n")
        report = audit(self.sessions, self.invoice, amount_tolerance=Decimal("0.01"),
                       energy_tolerance=Decimal("0.01"))
        self.assertEqual(report["summary"]["finding_count"], 0)
        with self.assertRaises(InputError):
            audit(self.sessions, self.invoice, amount_tolerance=Decimal("-0.01"))

    def test_duplicate_headers_are_rejected(self):
        self.sessions.write_text("session_id,session_id,started_at,site_id,energy_kwh,expected_total_eur\n", encoding="utf-8")
        self.invoice.write_text(INVOICE_HEADER, encoding="utf-8")
        with self.assertRaises(InputError):
            audit(self.sessions, self.invoice)

    def test_extreme_decimal_exponents_are_rejected_as_invalid_rows(self):
        self.files("S1,2026-01-02T10:00:00Z,D1,1e9999999,1\n", "")
        report = audit(self.sessions, self.invoice)
        self.assertEqual(report["summary"]["invalid_session_rows"], 1)

    def test_cli_writes_json_and_csv_report_then_returns_exception_status(self):
        self.files("S1,2026-01-02T10:00:00Z,D1,1,1\n", "")
        json_path, csv_path = self.root / "out.json", self.root / "out.csv"
        code = main(["--sessions", str(self.sessions), "--invoice", str(self.invoice), "--json", str(json_path),
                     "--exceptions", str(csv_path), "--fail-on-exceptions"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(json_path.read_text())["summary"]["finding_count"], 1)
        with csv_path.open(newline="") as source:
            self.assertEqual(next(csv.DictReader(source))["code"], "missing_invoice_line")

    def test_cli_refuses_to_overwrite_an_input(self):
        self.files("", "")
        self.assertEqual(main(["--sessions", str(self.sessions), "--invoice", str(self.invoice),
                               "--json", str(self.sessions), "--exceptions", str(self.root / "out.csv")]), 1)
        self.assertTrue(self.sessions.read_text(encoding="utf-8").startswith("session_id,"))

    def test_report_bytes_are_deterministic(self):
        self.files("S1,2026-01-02T10:00:00Z,D1,1,1\n", "L1,S1,1.02,1.04\n")
        report1 = audit(self.sessions, self.invoice)
        report2 = audit(self.sessions, self.invoice)
        json1, csv1 = self.root / "one.json", self.root / "one.csv"
        json2, csv2 = self.root / "two.json", self.root / "two.csv"
        write_report(report1, json1, csv1)
        write_report(report2, json2, csv2)
        self.assertEqual(json1.read_bytes(), json2.read_bytes())
        self.assertEqual(csv1.read_bytes(), csv2.read_bytes())

    def test_csv_formula_injection_is_neutralized_after_whitespace_and_controls(self):
        session_ids = ["=1+1", "+2", "-3", "@SUM(A1)", "\t=4", "\u200b+5"]
        sessions = "".join(f"{value},2026-01-02T10:00:00Z,D1,1,1\n" for value in session_ids)
        self.files(sessions, "")
        report = audit(self.sessions, self.invoice)
        json_path, csv_path = self.root / "formula.json", self.root / "formula.csv"
        write_report(report, json_path, csv_path)
        self.assertEqual([row["session_id"] for row in json.loads(json_path.read_text())["findings"]],
                         ["+2", "-3", "=1+1", "=4", "@SUM(A1)", "\u200b+5"])
        with csv_path.open(encoding="utf-8", newline="") as source:
            rows = list(csv.DictReader(source))
        self.assertEqual([row["session_id"] for row in rows], ["'+2", "'-3", "'=1+1", "'=4", "'@SUM(A1)", "'\u200b+5"])

    def test_negative_numeric_variance_remains_a_numeric_csv_cell(self):
        self.files("-3,2026-01-02T10:00:00Z,D1,1,1\n", "L1,-3,1,0\n")
        report = audit(self.sessions, self.invoice)
        csv_path = self.root / "negative.csv"
        write_report(report, self.root / "negative.json", csv_path)
        with csv_path.open(encoding="utf-8", newline="") as source:
            row = next(csv.DictReader(source))
        self.assertEqual(row["session_id"], "'-3")
        self.assertEqual(row["amount_eur"], "-1.00")
        self.assertEqual(row["energy_kwh"], "0")


if __name__ == "__main__":
    unittest.main()
