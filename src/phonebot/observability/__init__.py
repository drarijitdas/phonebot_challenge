"""Arize Phoenix tracing (Phase 4).

Provides init_tracing() and shutdown_tracing() functions for Phoenix OTEL integration.
"""
import os
from typing import Optional

import phoenix as px
from phoenix.otel import register

# Module-level tracer provider — stored so shutdown_tracing() can flush spans.
_tracer_provider: Optional[object] = None


def init_tracing() -> str:
    """Start Phoenix server and configure OTEL instrumentation.

    Reads PHOENIX_PROJECT env var (default: "phonebot-extraction") for project name.
    Uses PHOENIX_WORKING_DIR env var (default: ".phoenix") for persistent SQLite storage.
    Idempotent — if Phoenix is already running, skips launch_app() call.

    Returns:
        Phoenix UI URL string (e.g. "http://localhost:6006").
    """
    global _tracer_provider

    project_name = os.getenv("PHOENIX_PROJECT", "phonebot-extraction")
    working_dir = os.getenv("PHOENIX_WORKING_DIR", ".phoenix")

    # Ensure working directory exists for persistent storage (D-04)
    os.makedirs(working_dir, exist_ok=True)
    os.environ["PHOENIX_WORKING_DIR"] = working_dir

    # Start Phoenix server — idempotent: skip if already running (Pitfall 4)
    session = px.active_session()
    if session is None:
        session = px.launch_app(use_temp_dir=False)

    # Register OTEL tracer provider with auto-instrumentation (D-08)
    # batch=False: synchronous export for CLI scripts (RESEARCH Pattern 1)
    # project_name passed explicitly — do NOT rely on Phoenix auto-reading env var (Pitfall 6)
    _tracer_provider = register(
        project_name=project_name,
        auto_instrument=True,
        batch=False,
    )

    # Return session URL if available, else fallback
    return session.url if session else "http://localhost:6006"


def shutdown_tracing() -> None:
    """Flush all pending spans before process exit.

    Calls force_flush() on the stored tracer provider. Safe to call even if
    init_tracing() was not called (no-op in that case).
    """
    global _tracer_provider
    if _tracer_provider is not None:
        _tracer_provider.force_flush()
