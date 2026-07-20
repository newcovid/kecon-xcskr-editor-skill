from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "kecon_help.py"


class KeconHelpTests(unittest.TestCase):
    def test_search_finds_curated_help_topic(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "search", "CAN"],
            check=True,
            text=True,
            encoding="utf-8",
            capture_output=True,
        )

        self.assertIn("CAN", result.stdout)
        self.assertIn("功能块", result.stdout)
        self.assertIn("原文", result.stdout)


if __name__ == "__main__":
    unittest.main()
