from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcq_crawler.auth import host_from_url, load_host_auth_config, normalize_host


class AuthConfigTests(unittest.TestCase):
    def test_normalize_host_removes_www_and_port(self) -> None:
        self.assertEqual(normalize_host("WWW.Example.com:443"), "example.com")

    def test_host_from_url_extracts_hostname(self) -> None:
        self.assertEqual(
            host_from_url("https://www.examtopics.com/exams/amazon/aws-certified-cloud-practitioner-clf-c02/view/"),
            "examtopics.com",
        )

    def test_load_host_auth_config_from_hosts_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            auth_file = Path(tmp_dir) / "auth_hosts.yaml"
            auth_file.write_text(
                """
hosts:
  - host: examtopics.com
    login_url: https://www.examtopics.com/login/
    username_selector: "input[name='email']"
    password_selector: "input[name='password']"
    submit_selector: "button[type='submit']"
    success_selector: "a[href*='/logout']"
    username: test-user
    password: test-pass
                """.strip()
                + "\n",
                encoding="utf-8",
            )

            config = load_host_auth_config(
                auth_file,
                "https://www.examtopics.com/exams/amazon/aws-certified-cloud-practitioner-clf-c02/view/",
            )

            self.assertIsNotNone(config)
            assert config is not None
            self.assertEqual(config.host, "examtopics.com")
            self.assertEqual(config.username_selector, "input[name='email']")
            self.assertEqual(config.submit_selector, "button[type='submit']")

    def test_load_host_auth_config_from_host_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            auth_file = Path(tmp_dir) / "auth_hosts.yaml"
            auth_file.write_text(
                """
examtopics.com:
  login_url: https://www.examtopics.com/login/
  username_selector: "#id_username"
  password_selector: "#id_password"
  username: test-user
  password: test-pass
                """.strip()
                + "\n",
                encoding="utf-8",
            )

            config = load_host_auth_config(
                auth_file,
                "https://examtopics.com/exams/amazon/aws-certified-cloud-practitioner-clf-c02/view/",
            )

            self.assertIsNotNone(config)
            assert config is not None
            self.assertEqual(config.host, "examtopics.com")
            self.assertEqual(config.username, "test-user")
            self.assertEqual(config.password_selector, "#id_password")

    def test_load_host_auth_config_returns_none_when_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            auth_file = Path(tmp_dir) / "missing.yaml"
            config = load_host_auth_config(auth_file, "https://www.examtopics.com/login/")
            self.assertIsNone(config)


if __name__ == "__main__":
    unittest.main()
