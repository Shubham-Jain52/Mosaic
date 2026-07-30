"""Tests for mosaic init .gitignore updates."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.gitignore_util import ensure_mosaic_gitignore


class EnsureMosaicGitignoreTests(unittest.TestCase):
    def test_creates_gitignore_with_mosaic_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".gitignore"
            added = ensure_mosaic_gitignore(path)
            self.assertEqual(added, [".env", ".mosaic/", "mosaic.db"])
            text = path.read_text()
            self.assertIn(".env", text)
            self.assertIn(".mosaic/", text)
            self.assertIn("mosaic.db", text)
            self.assertIn("Mosaic (added by mosaic init)", text)

    def test_idempotent_when_already_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".gitignore"
            path.write_text(".env\n.mosaic/\nmosaic.db\n")
            added = ensure_mosaic_gitignore(path)
            self.assertEqual(added, [])
            # Unchanged aside from possible trailing content
            self.assertEqual(path.read_text().count(".env"), 1)

    def test_appends_only_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".gitignore"
            path.write_text("node_modules/\n.env\n")
            added = ensure_mosaic_gitignore(path)
            self.assertEqual(added, [".mosaic/", "mosaic.db"])
            text = path.read_text()
            self.assertIn("node_modules/", text)
            self.assertIn(".mosaic/", text)
            self.assertIn("mosaic.db", text)
            self.assertEqual(text.count(".env"), 1)


if __name__ == "__main__":
    unittest.main()
