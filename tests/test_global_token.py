"""Tests for global vs project GitHub token resolution."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import config as cfg


class GithubTokenLookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = {
            k: os.environ.get(k)
            for k in (cfg.GLOBAL_TOKEN_KEY, "GITHUB_TOKEN", "REPO_OWNER", "REPO_NAME")
        }

    def tearDown(self) -> None:
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_global_token_preferred_over_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            global_env = Path(tmp) / "global.env"
            project_env = Path(tmp) / "project.env"
            global_env.write_text(f"{cfg.GLOBAL_TOKEN_KEY}=global-pat\n")
            project_env.write_text("GITHUB_TOKEN=project-pat\n")

            os.environ.pop(cfg.GLOBAL_TOKEN_KEY, None)
            os.environ.pop("GITHUB_TOKEN", None)

            with patch.object(cfg, "GLOBAL_ENV_PATH", global_env), patch.object(
                cfg, "ENV_PATH", project_env
            ):
                self.assertEqual(cfg.get_github_token(), "global-pat")

    def test_falls_back_to_project_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            global_env = Path(tmp) / "global.env"
            project_env = Path(tmp) / "project.env"
            project_env.write_text("GITHUB_TOKEN=project-only\n")

            os.environ.pop(cfg.GLOBAL_TOKEN_KEY, None)
            os.environ.pop("GITHUB_TOKEN", None)

            with patch.object(cfg, "GLOBAL_ENV_PATH", global_env), patch.object(
                cfg, "ENV_PATH", project_env
            ):
                self.assertEqual(cfg.get_github_token(), "project-only")

    def test_save_global_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home_mosaic = Path(tmp) / ".mosaic"
            global_env = home_mosaic / ".env"
            with patch.object(cfg, "GLOBAL_MOSAIC_DIR", home_mosaic), patch.object(
                cfg, "GLOBAL_ENV_PATH", global_env
            ):
                path = cfg.save_global_github_token("secret-token")
                self.assertEqual(path, global_env)
                self.assertIn("MOSAIC_GITHUB_TOKEN=secret-token", global_env.read_text())
                self.assertEqual(os.environ.get(cfg.GLOBAL_TOKEN_KEY), "secret-token")


if __name__ == "__main__":
    unittest.main()
