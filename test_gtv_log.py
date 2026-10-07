import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter


spec = importlib.util.spec_from_file_location("gtv_log", Path(__file__).with_name("gtv_log.py"))
gtv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gtv)


class AssessmentTests(unittest.TestCase):
    def test_incomplete_bundle_reports_coverage_and_missing_source(self):
        con = sqlite3.connect(":memory:")
        con.execute("""CREATE TABLE candidates
            (id TEXT, activity TEXT, source TEXT, url TEXT, file_path TEXT,
             status TEXT, criterion TEXT, impact TEXT, corroboration TEXT)""")
        con.execute("INSERT INTO candidates VALUES (?,?,?,?,?,?,?,?,?)",
                    ("abc", "Project", "Local Git history", "https://github.com/example/commits",
                     "C:/missing", "Evidence ready", "Recognition", "Users adopted it", "Peer said so"))
        messages = " ".join(message for _, message in gtv.assess(con))
        self.assertIn("no saved evidence file", messages)
        self.assertIn("Recognition: 1/2", messages)
        self.assertIn("Optional 1: 0/2", messages)
        con.close()

    def test_oversize_pdf_and_duplicate_file_are_flagged(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / "proof.pdf"
            writer = PdfWriter()
            for _ in range(4):
                writer.add_blank_page(width=595, height=842)
            with path.open("wb") as f:
                writer.write(f)
            con = sqlite3.connect(":memory:")
            con.execute("""CREATE TABLE candidates
                (id TEXT, activity TEXT, source TEXT, url TEXT, file_path TEXT,
                 status TEXT, criterion TEXT, impact TEXT, corroboration TEXT)""")
            for ident, criterion in (("a", "Recognition"), ("b", "Optional 1")):
                con.execute("INSERT INTO candidates VALUES (?,?,?,?,?,?,?,?,?)",
                            (ident, "Project", "Proof file", "", str(path), "Evidence ready",
                             criterion, "Outcome", "Independent source"))
            messages = " ".join(message for _, message in gtv.assess(con))
            self.assertIn("PDF is 4 pages", messages)
            self.assertIn("same file appears", messages)
            con.close()


if __name__ == "__main__":
    unittest.main()
