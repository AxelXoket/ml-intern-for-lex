"""Explicit configuration contract for ml-intern.

Two separate settings classes enforce conceptual boundaries:
- IntegrationSettings: connection to lex_study_foundation (runtime/integration)
- ResearchProviderSettings: ml-intern's own research tokens (never forwarded to lex)

Dotenv loading is deterministic:
- Resolved from package location (absolute path), NOT from CWD
- Override via ML_INTERN_ENV_FILE environment variable
- Precedence: OS env vars > repo-local .env > pydantic defaults

Note on editable vs non-editable installs:
  The default .env resolution uses Path(__file__) to find the repo root.
  This works correctly for editable installs (uv sync / uv tool install -e .).
  For non-editable installs, set ML_INTERN_ENV_FILE explicitly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ── .env Resolution ──────────────────────────────────────────────

# Package location: src/ml_intern/config.py
# Repo root: 3 levels up (config.py → ml_intern → src → repo root)
INTERN_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = INTERN_REPO_ROOT  # backward compat alias


def resolve_env_file() -> Path | None:
    """Deterministic .env path resolution. Never CWD-dependent.

    Priority:
    1. ML_INTERN_ENV_FILE environment variable (explicit override)
    2. Repo-root .env (resolved from package location)

    Returns None if neither exists (settings will rely on OS env vars only).
    """
    # Explicit override
    override = os.environ.get("ML_INTERN_ENV_FILE")
    if override:
        p = Path(override).resolve()
        if p.is_file():
            return p
        print(
            f"\n  [WARNING] ML_INTERN_ENV_FILE points to missing file: {p}\n"
            f"  Falling back to OS environment variables only.\n",
            file=sys.stderr,
        )
        return None

    # Default: repo-root .env
    default = _REPO_ROOT / ".env"
    if default.is_file():
        return default

    return None


# ── Integration Settings ────────────────────────────────────────

class IntegrationSettings(BaseSettings):
    """Connection to lex_study_foundation — runtime/integration boundary.

    These settings control how ml-intern finds and invokes the main project.
    """

    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=False,
    )

    # ── Required ─────────────────────────────────────────────
    lex_python_exe: str = Field(
        description="Absolute path to Python executable in lex_study_foundation venv",
    )
    lex_project_root: str = Field(
        description="Absolute path to lex_study_foundation repo root",
    )

    # ── Optional ─────────────────────────────────────────────
    lex_config_dir: str | None = Field(
        default=None,
        description="Override config file directory (default: {ROOT}/configs)",
    )
    ml_intern_host: str = Field(default="127.0.0.1")
    ml_intern_port: int = Field(default=8642, ge=1024, le=65535)

    # ── Validators ───────────────────────────────────────────
    @field_validator("lex_python_exe")
    @classmethod
    def _validate_python_exe(cls, v: str) -> str:
        p = Path(v)
        if not p.is_file():
            print(
                f"\n  [FATAL] LEX_PYTHON_EXE does not exist: {v}\n"
                f"  Set this in .env or as an environment variable.\n",
                file=sys.stderr,
            )
            raise ValueError(f"LEX_PYTHON_EXE not found: {v}")
        return str(p.resolve())

    @field_validator("lex_project_root")
    @classmethod
    def _validate_project_root(cls, v: str) -> str:
        p = Path(v)
        if not p.is_dir():
            print(
                f"\n  [FATAL] LEX_PROJECT_ROOT does not exist: {v}\n"
                f"  Set this in .env or as an environment variable.\n",
                file=sys.stderr,
            )
            raise ValueError(f"LEX_PROJECT_ROOT not found: {v}")
        return str(p.resolve())

    # ── Derived ──────────────────────────────────────────────
    @property
    def config_dir(self) -> Path:
        if self.lex_config_dir:
            return Path(self.lex_config_dir)
        return Path(self.lex_project_root) / "configs"

    @property
    def python_exe(self) -> Path:
        return Path(self.lex_python_exe)

    @property
    def project_root(self) -> Path:
        return Path(self.lex_project_root)


# ── Research Provider Settings ──────────────────────────────────

class ResearchProviderSettings(BaseSettings):
    """ml-intern's own research tokens — NEVER forwarded to lex subprocesses.

    These tokens belong to ml-intern only. They enable optional
    research-oriented features (disabled by default in V1).
    """

    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=False,
    )

    # ── Feature gate ─────────────────────────────────────────
    research_enabled: bool = Field(
        default=False,
        description="Enable research/provider-backed features (disabled by default)",
    )

    # ── Provider tokens (all optional) ───────────────────────
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key for Claude-backed research features",
    )
    hf_token: str = Field(
        default="",
        description="HuggingFace token for model/dataset access",
    )
    github_token: str = Field(
        default="",
        description="GitHub token for repo inspection (prefer fine-grained PAT, minimum scope)",
    )

    # ── Derived ──────────────────────────────────────────────
    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def has_hf(self) -> bool:
        return bool(self.hf_token)

    @property
    def has_github(self) -> bool:
        return bool(self.github_token)

    @property
    def research_status(self) -> str:
        """Return human-readable research status for UI display."""
        if not self.research_enabled:
            return "disabled"
        if not any([self.has_anthropic, self.has_hf, self.has_github]):
            return "unconfigured"
        return "available"


# ── Singletons ──────────────────────────────────────────────────

_integration: IntegrationSettings | None = None
_research: ResearchProviderSettings | None = None


def get_integration_settings() -> IntegrationSettings:
    """Return cached integration settings. Fails fast on missing required values."""
    global _integration
    if _integration is None:
        env_file = resolve_env_file()
        _integration = IntegrationSettings(_env_file=env_file)  # type: ignore[call-arg]
    return _integration


def get_research_settings() -> ResearchProviderSettings:
    """Return cached research provider settings."""
    global _research
    if _research is None:
        env_file = resolve_env_file()
        _research = ResearchProviderSettings(_env_file=env_file)  # type: ignore[call-arg]
    return _research
