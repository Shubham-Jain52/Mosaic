"""Tests for chat API key lookup, verify, provider aliases, and persistence."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ai.chat import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_GROQ_CHAT_MODEL,
    GROQ_API_BASE,
    OPENAI_API_BASE,
    OPENROUTER_API_BASE,
    ChatError,
    ChatSettings,
    default_chat_model_for_base,
    format_api_base_for_display,
    get_chat_settings,
    peek_chat_settings,
    resolve_chat_provider,
    sample_models_for_provider,
    verify_chat_settings,
)
from core import config as cfg
from cli import main as cli_main


class ChatSettingsLookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._keys = (
            "CHAT_API_KEY",
            "OPENAI_API_KEY",
            "EMBEDDING_API_KEY",
            "CHAT_MODEL",
            "CHAT_API_BASE",
        )
        self._backup = {k: os.environ.get(k) for k in self._keys}

    def tearDown(self) -> None:
        for key, value in self._backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _clear_chat_env(self) -> None:
        for key in self._keys:
            os.environ.pop(key, None)

    def test_peek_returns_none_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            global_env = Path(tmp) / "global.env"
            project_env = Path(tmp) / "project.env"
            self._clear_chat_env()
            with patch.object(cfg, "GLOBAL_ENV_PATH", global_env), patch.object(
                cfg, "ENV_PATH", project_env
            ):
                self.assertIsNone(peek_chat_settings())
                with self.assertRaises(ChatError):
                    get_chat_settings()

    def test_peek_loads_from_global_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            global_env = Path(tmp) / "global.env"
            project_env = Path(tmp) / "project.env"
            global_env.write_text(
                "CHAT_API_KEY=global-chat-key\nCHAT_MODEL=gpt-4o-mini\n"
            )
            self._clear_chat_env()
            with patch.object(cfg, "GLOBAL_ENV_PATH", global_env), patch.object(
                cfg, "ENV_PATH", project_env
            ):
                settings = peek_chat_settings()
                self.assertIsNotNone(settings)
                assert settings is not None
                self.assertEqual(settings.api_key, "global-chat-key")
                self.assertEqual(settings.model, "gpt-4o-mini")

    def test_openai_key_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            global_env = Path(tmp) / "global.env"
            project_env = Path(tmp) / "project.env"
            project_env.write_text("OPENAI_API_KEY=openai-fallback\n")
            self._clear_chat_env()
            with patch.object(cfg, "GLOBAL_ENV_PATH", global_env), patch.object(
                cfg, "ENV_PATH", project_env
            ):
                settings = peek_chat_settings()
                self.assertIsNotNone(settings)
                assert settings is not None
                self.assertEqual(settings.api_key, "openai-fallback")

    def test_save_chat_settings_global(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home_mosaic = Path(tmp) / ".mosaic"
            global_env = home_mosaic / ".env"
            with patch.object(cfg, "GLOBAL_MOSAIC_DIR", home_mosaic), patch.object(
                cfg, "GLOBAL_ENV_PATH", global_env
            ):
                path = cfg.save_chat_settings(
                    api_key="gsk-test-not-openai",
                    model=DEFAULT_GROQ_CHAT_MODEL,
                    api_base=GROQ_API_BASE,
                    env_path=global_env,
                )
                self.assertEqual(path, global_env)
                text = global_env.read_text()
                self.assertIn("CHAT_API_KEY=gsk-test-not-openai", text)
                self.assertIn(f"CHAT_MODEL={DEFAULT_GROQ_CHAT_MODEL}", text)
                self.assertIn(f"CHAT_API_BASE={GROQ_API_BASE}", text)
                self.assertEqual(os.environ.get("CHAT_API_KEY"), "gsk-test-not-openai")


class ResolveChatProviderTests(unittest.TestCase):
    def test_aliases_case_insensitive(self) -> None:
        for raw in ("Groq", "groq", "GROQ", "2"):
            resolved = resolve_chat_provider(raw)
            self.assertEqual(resolved.provider_id, "groq")
            self.assertEqual(resolved.api_base, GROQ_API_BASE)
            self.assertTrue(resolved.from_alias)

        for raw in ("openai", "OpenAI", "OAI", "1", ""):
            resolved = resolve_chat_provider(raw)
            self.assertEqual(resolved.provider_id, "openai")
            self.assertIsNone(resolved.api_base)

        for raw in ("OpenRouter", "openrouter", "open-router", "3"):
            resolved = resolve_chat_provider(raw)
            self.assertEqual(resolved.provider_id, "openrouter")
            self.assertEqual(resolved.api_base, OPENROUTER_API_BASE)

    def test_custom_url_passthrough(self) -> None:
        url = "https://api.together.xyz/v1"
        resolved = resolve_chat_provider(url)
        self.assertEqual(resolved.provider_id, "custom")
        self.assertEqual(resolved.api_base, url)
        self.assertFalse(resolved.from_alias)

    def test_known_url_maps_provider(self) -> None:
        resolved = resolve_chat_provider(GROQ_API_BASE)
        self.assertEqual(resolved.provider_id, "groq")
        self.assertEqual(resolved.api_base, GROQ_API_BASE.rstrip("/"))

    def test_unknown_name_raises(self) -> None:
        with self.assertRaises(ChatError) as ctx:
            resolve_chat_provider("NotAProvider")
        self.assertIn("Unknown chat provider", str(ctx.exception))

    def test_custom_choice_needs_url(self) -> None:
        resolved = resolve_chat_provider("custom")
        self.assertEqual(resolved.provider_id, "custom")
        self.assertIsNone(resolved.api_base)


class SampleModelsTests(unittest.TestCase):
    def test_samples_per_provider(self) -> None:
        openai_samples = sample_models_for_provider("openai")
        self.assertIn("gpt-4o-mini", openai_samples)
        self.assertTrue(len(openai_samples) >= 2)

        groq_samples = sample_models_for_provider("Groq")
        self.assertEqual(groq_samples[0], DEFAULT_GROQ_CHAT_MODEL)
        self.assertIn("openai/gpt-oss-20b", groq_samples)

        openrouter_samples = sample_models_for_provider("openrouter")
        self.assertTrue(len(openrouter_samples) >= 2)

        self.assertEqual(sample_models_for_provider("custom"), [])

    def test_default_model_for_base(self) -> None:
        self.assertEqual(
            default_chat_model_for_base(GROQ_API_BASE),
            DEFAULT_GROQ_CHAT_MODEL,
        )
        self.assertEqual(default_chat_model_for_base(None), DEFAULT_CHAT_MODEL)
        self.assertEqual(default_chat_model_for_base(""), DEFAULT_CHAT_MODEL)
        self.assertEqual(
            default_chat_model_for_base(OPENAI_API_BASE),
            DEFAULT_CHAT_MODEL,
        )


class VerifyChatSettingsTests(unittest.TestCase):
    def test_verify_calls_completion_ping(self) -> None:
        mock_client = MagicMock()
        mock_openai = MagicMock(return_value=mock_client)
        with patch.dict("sys.modules", {"openai": MagicMock(OpenAI=mock_openai)}):
            # Re-import path: verify imports OpenAI inside the function
            with patch("openai.OpenAI", mock_openai):
                verify_chat_settings(
                    ChatSettings(api_key="sk-test", model="gpt-4o-mini")
                )
        mock_openai.assert_called_once_with(api_key="sk-test")
        mock_client.chat.completions.create.assert_called_once()
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-4o-mini")
        self.assertEqual(kwargs["max_tokens"], 1)
        self.assertEqual(kwargs["messages"], [{"role": "user", "content": "ping"}])

    def test_verify_passes_custom_base_url(self) -> None:
        mock_client = MagicMock()
        mock_openai = MagicMock(return_value=mock_client)
        with patch("openai.OpenAI", mock_openai):
            verify_chat_settings(
                ChatSettings(
                    api_key="gsk-groq-key",
                    model=DEFAULT_GROQ_CHAT_MODEL,
                    api_base=GROQ_API_BASE,
                )
            )
        mock_openai.assert_called_once_with(
            api_key="gsk-groq-key",
            base_url=GROQ_API_BASE,
        )

    def test_verify_raises_on_api_failure_includes_base_not_key(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("bad key")
        mock_openai = MagicMock(return_value=mock_client)
        with patch("openai.OpenAI", mock_openai):
            with self.assertRaises(ChatError) as ctx:
                verify_chat_settings(
                    ChatSettings(
                        api_key="sk-secret-should-not-leak",
                        model="gpt-4o-mini",
                        api_base=GROQ_API_BASE,
                    )
                )
        msg = str(ctx.exception)
        self.assertIn("verification failed", msg.lower())
        self.assertIn(GROQ_API_BASE, msg)
        self.assertIn("gpt-4o-mini", msg)
        self.assertNotIn("sk-secret-should-not-leak", msg)

    def test_format_api_base_for_display(self) -> None:
        self.assertEqual(format_api_base_for_display(None), OPENAI_API_BASE)
        self.assertEqual(format_api_base_for_display(GROQ_API_BASE), GROQ_API_BASE)


class EnsureChatCredentialsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._keys = (
            "CHAT_API_KEY",
            "OPENAI_API_KEY",
            "EMBEDDING_API_KEY",
            "CHAT_MODEL",
            "CHAT_API_BASE",
        )
        self._backup = {k: os.environ.get(k) for k in self._keys}
        for key in self._keys:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_skips_prompt_when_key_present(self) -> None:
        os.environ["CHAT_API_KEY"] = "already-set"
        with patch.object(cli_main, "getpass") as mock_getpass, patch.object(
            cli_main, "typer"
        ) as mock_typer, patch.object(cli_main, "verify_chat_settings") as mock_verify:
            mock_typer.prompt = MagicMock()
            mock_typer.confirm = MagicMock()
            cli_main._ensure_chat_credentials()
            mock_getpass.getpass.assert_not_called()
            mock_typer.prompt.assert_not_called()
            mock_verify.assert_not_called()

    def test_prompts_verifies_and_saves_global(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home_mosaic = Path(tmp) / ".mosaic"
            global_env = home_mosaic / ".env"
            project_env = Path(tmp) / "project.env"

            def prompt_side_effect(text, default="", show_default=True):
                if "Choose provider" in text:
                    return "1"
                if "Choose model" in text:
                    return "1"
                return default

            with patch.object(cfg, "GLOBAL_MOSAIC_DIR", home_mosaic), patch.object(
                cfg, "GLOBAL_ENV_PATH", global_env
            ), patch.object(cfg, "ENV_PATH", project_env), patch.object(
                cli_main, "GLOBAL_ENV_PATH", global_env
            ), patch.object(cli_main, "ENV_PATH", project_env), patch.object(
                cli_main, "peek_chat_settings", return_value=None
            ), patch.object(
                cli_main.getpass, "getpass", return_value="sk-new"
            ), patch.object(
                cli_main.typer,
                "prompt",
                side_effect=prompt_side_effect,
            ), patch.object(
                cli_main.typer, "confirm", return_value=True
            ), patch.object(
                cli_main, "verify_chat_settings"
            ) as mock_verify, patch.object(
                cli_main.typer, "echo"
            ), patch.object(
                cli_main.typer, "secho"
            ):
                cli_main._ensure_chat_credentials()
                mock_verify.assert_called_once()
                settings = mock_verify.call_args.args[0]
                self.assertEqual(settings.api_key, "sk-new")
                self.assertIsNone(settings.api_base)
                self.assertEqual(settings.model, "gpt-4o-mini")
                text = global_env.read_text()
                self.assertIn("CHAT_API_KEY=sk-new", text)
                self.assertIn("CHAT_MODEL=gpt-4o-mini", text)
                self.assertNotIn("CHAT_API_BASE", text)
                self.assertEqual(os.environ.get("CHAT_API_KEY"), "sk-new")

    def test_prompts_groq_alias_and_saves_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home_mosaic = Path(tmp) / ".mosaic"
            global_env = home_mosaic / ".env"
            project_env = Path(tmp) / "project.env"
            echo_lines: list = []

            def prompt_side_effect(text, default="", show_default=True):
                if "Choose provider" in text:
                    return "Groq"
                if "Choose model" in text:
                    return "1"
                return default

            def echo_side_effect(*args, **kwargs):
                if args:
                    echo_lines.append(str(args[0]))

            with patch.object(cfg, "GLOBAL_MOSAIC_DIR", home_mosaic), patch.object(
                cfg, "GLOBAL_ENV_PATH", global_env
            ), patch.object(cfg, "ENV_PATH", project_env), patch.object(
                cli_main, "GLOBAL_ENV_PATH", global_env
            ), patch.object(cli_main, "ENV_PATH", project_env), patch.object(
                cli_main, "peek_chat_settings", return_value=None
            ), patch.object(
                cli_main.getpass, "getpass", return_value="gsk_groq_key"
            ), patch.object(
                cli_main.typer, "prompt", side_effect=prompt_side_effect
            ), patch.object(
                cli_main.typer, "confirm", return_value=True
            ), patch.object(
                cli_main, "verify_chat_settings"
            ) as mock_verify, patch.object(
                cli_main.typer, "echo", side_effect=echo_side_effect
            ), patch.object(
                cli_main.typer, "secho"
            ):
                cli_main._ensure_chat_credentials()
                mock_verify.assert_called_once()
                settings = mock_verify.call_args.args[0]
                self.assertEqual(settings.api_key, "gsk_groq_key")
                self.assertEqual(settings.api_base, GROQ_API_BASE)
                self.assertEqual(settings.model, DEFAULT_GROQ_CHAT_MODEL)
                text = global_env.read_text()
                self.assertIn("CHAT_API_KEY=gsk_groq_key", text)
                self.assertIn(f"CHAT_MODEL={DEFAULT_GROQ_CHAT_MODEL}", text)
                self.assertIn(f"CHAT_API_BASE={GROQ_API_BASE}", text)
                joined = "\n".join(echo_lines)
                self.assertIn("Resolved provider Groq", joined)
                self.assertIn(GROQ_API_BASE, joined)
                self.assertIn("Verifying chat credentials", joined)
                self.assertIn("Chat credentials verified", joined)
                self.assertNotIn("gsk_groq_key", joined)
