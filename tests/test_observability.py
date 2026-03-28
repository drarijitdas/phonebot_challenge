"""Unit tests for the observability module (init_tracing, shutdown_tracing).

All tests use mocks — no actual Phoenix server is started.

Patch strategy:
  - Patch at source before module reload so the reload picks up mocks.
  - "phoenix.active_session"  -> patched at source
  - "phoenix.launch_app"      -> patched at source
  - "phoenix.otel.register"   -> patched at source (so reload gets mock via from import)
  - After reload, also patch "phonebot.observability.register" for already-loaded module.
"""
import importlib
import os
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(url="http://localhost:6006"):
    session = MagicMock()
    session.url = url
    return session


@contextmanager
def _patched_obs(session=None, mock_register=None, env_overrides=None):
    """Context manager that patches Phoenix internals and reloads the observability module.

    Patches phoenix.otel.register at source so that importlib.reload() picks up
    the mock via 'from phoenix.otel import register'.
    """
    if session is None:
        session = _make_session()
    if mock_register is None:
        mock_register = MagicMock()

    env = env_overrides or {}

    with (
        patch.dict(os.environ, env),
        patch("phoenix.active_session", return_value=None),
        patch("phoenix.launch_app", return_value=session),
        patch("phoenix.otel.register", mock_register),
    ):
        import phonebot.observability as obs_module
        importlib.reload(obs_module)
        obs_module._port_in_use = lambda port: False
        yield obs_module, mock_register


@contextmanager
def _patched_obs_with_active_session(existing_session):
    """Variant that returns an existing active session (no launch_app call)."""
    mock_register = MagicMock()

    with (
        patch("phoenix.active_session", return_value=existing_session),
        patch("phoenix.launch_app") as mock_launch,
        patch("phoenix.otel.register", mock_register),
    ):
        import phonebot.observability as obs_module
        importlib.reload(obs_module)
        yield obs_module, mock_launch, mock_register


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestInitTracingReturnsUrl:
    """init_tracing() returns a string containing 'http'."""

    def test_init_tracing_returns_url(self):
        """init_tracing() returns a URL string with 'http'."""
        with _patched_obs() as (obs, _):
            result = obs.init_tracing()
            assert isinstance(result, str)
            assert "http" in result


class TestRegisterCalledWithAutoInstrument:
    """register() is called with auto_instrument=True and project_name from env var."""

    def test_register_called_with_auto_instrument(self):
        """register() is called with auto_instrument=True."""
        with _patched_obs() as (obs, mock_register):
            obs.init_tracing()
            mock_register.assert_called_once()
            call_kwargs = mock_register.call_args[1]
            assert call_kwargs.get("auto_instrument") is True


class TestLaunchAppUsesPersistentStorage:
    """px.launch_app() called with use_temp_dir=False."""

    def test_launch_app_uses_persistent_storage(self):
        """px.launch_app() is called with use_temp_dir=False for persistent SQLite."""
        with (
            patch("phoenix.active_session", return_value=None),
            patch("phoenix.launch_app") as mock_launch,
            patch("phoenix.otel.register"),
        ):
            mock_session = _make_session()
            mock_launch.return_value = mock_session

            import phonebot.observability as obs_module
            importlib.reload(obs_module)
            obs_module._port_in_use = lambda port: False
            obs_module.init_tracing()
            mock_launch.assert_called_once_with(use_temp_dir=False)


class TestActiveSessionSkipsRelaunch:
    """When px.active_session() returns a session, px.launch_app() is NOT called."""

    def test_active_session_skips_relaunch(self):
        """When a session is already active, launch_app() is not called."""
        existing_session = _make_session()
        with _patched_obs_with_active_session(existing_session) as (obs, mock_launch, _):
            obs.init_tracing()
            mock_launch.assert_not_called()


class TestShutdownTracingFlushes:
    """shutdown_tracing() calls force_flush() on the tracer provider."""

    def test_shutdown_tracing_flushes(self):
        """shutdown_tracing() calls force_flush() on stored tracer provider."""
        mock_tracer_provider = MagicMock()
        # register() returns the tracer provider — make the mock return it when called
        mock_register = MagicMock(return_value=mock_tracer_provider)

        with _patched_obs(mock_register=mock_register) as (obs, _):
            obs.init_tracing()
            obs.shutdown_tracing()
            mock_tracer_provider.force_flush.assert_called_once()


class TestInitTracingReadsPhoenixProjectEnv:
    """When PHOENIX_PROJECT env var is set, register() receives it as project_name."""

    def test_init_tracing_reads_phoenix_project_env(self):
        """register() receives project_name from PHOENIX_PROJECT env var."""
        with _patched_obs(env_overrides={"PHOENIX_PROJECT": "my-test-project"}) as (obs, mock_register):
            obs.init_tracing()
            call_kwargs = mock_register.call_args[1]
            assert call_kwargs.get("project_name") == "my-test-project"


class TestBatchFalseForCliScript:
    """register() is called with batch=False for reliable span flushing in CLI scripts."""

    def test_batch_false_for_cli_script(self):
        """register() is called with batch=False for synchronous export."""
        with _patched_obs() as (obs, mock_register):
            obs.init_tracing()
            call_kwargs = mock_register.call_args[1]
            assert call_kwargs.get("batch") is False


class TestRunPipelineAcceptsPromptVersion:
    """run_pipeline() signature accepts prompt_version parameter."""

    def test_run_pipeline_accepts_prompt_version(self):
        """run_pipeline() has a prompt_version parameter."""
        import inspect
        from phonebot.pipeline.extract import run_pipeline

        sig = inspect.signature(run_pipeline)
        assert "prompt_version" in sig.parameters

    def test_run_pipeline_default_prompt_version(self):
        """run_pipeline() has prompt_version default of 'v1'."""
        import inspect
        from phonebot.pipeline.extract import run_pipeline

        sig = inspect.signature(run_pipeline)
        assert sig.parameters["prompt_version"].default == "v1"
