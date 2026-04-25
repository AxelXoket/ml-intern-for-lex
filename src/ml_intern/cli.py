"""CLI entry point for ml-intern.

Usage::

    ml-intern              → shows help
    ml-intern serve        → starts dashboard on configured host:port
    ml-intern serve --port 9000  → override port
"""

from __future__ import annotations

import typer

app = typer.Typer(
    name="ml-intern",
    help="Companion dashboard for lex_study_foundation",
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=False,
    invoke_without_command=True,
)


@app.callback()
def main() -> None:
    """ml-intern — Companion dashboard for lex_study_foundation."""


@app.command()
def serve(
    host: str | None = typer.Option(None, "--host", help="Override bind host"),
    port: int | None = typer.Option(None, "--port", "-p", help="Override bind port"),
) -> None:
    """Start the companion dashboard."""
    import uvicorn

    from ml_intern.config import get_integration_settings

    settings = get_integration_settings()
    bind_host = host or settings.ml_intern_host
    bind_port = port or settings.ml_intern_port

    uvicorn.run(
        "ml_intern.main:app",
        host=bind_host,
        port=bind_port,
    )

