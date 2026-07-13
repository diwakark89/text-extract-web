from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


class DependencyConstraintTests(unittest.TestCase):
    def test_websockets_dependency_is_pinned_below_playwright_compat_break(self) -> None:
        pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
        with pyproject_path.open("rb") as handle:
            data = tomllib.load(handle)

        dependencies = data["project"]["dependencies"]
        self.assertTrue(any(dep.startswith("websockets<") for dep in dependencies), dependencies)


if __name__ == "__main__":
    unittest.main()
