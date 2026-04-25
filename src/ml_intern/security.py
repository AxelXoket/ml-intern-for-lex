"""Security utilities — subprocess env allowlist and secret redaction.

This module enforces the boundary between ml-intern and lex_study_foundation:
- Subprocess environments are built from an explicit allowlist
- Provider secrets are NEVER forwarded to child processes
- Output is redacted before buffering, streaming, or storing
"""

from __future__ import annotations

import os
import re
from pathlib import Path


# ── Subprocess Environment Allowlist ─────────────────────────────

# Only these OS variables are forwarded to lex_study_foundation subprocesses.
_ENV_ALLOWLIST: frozenset[str] = frozenset({
    # Windows process essentials (subprocess won't start without these)
    "SystemRoot",
    "SystemDrive",
    "COMSPEC",
    "WINDIR",
    # Temp directories
    "TEMP",
    "TMP",
    # User profile (some tools need this)
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    # Executable resolution
    "PATH",
    "PATHEXT",
    # CPU / platform detection (used by some build tools)
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
})

# These secrets are NEVER forwarded, even if they somehow appear in the env.
# If any of these are found in the subprocess env, a RuntimeError is raised.
_NEVER_FORWARD: frozenset[str] = frozenset({
    # ml-intern research secrets
    "ANTHROPIC_API_KEY",
    "HF_TOKEN",
    "GITHUB_TOKEN",
    # Other provider secrets that may exist in OS env
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_ACCESS_KEY_ID",
    "AZURE_OPENAI_API_KEY",
})


def build_subprocess_env(project_root: Path) -> dict[str, str]:
    """Construct a minimal, safe environment for lex_study_foundation subprocesses.

    Rules:
    - Only allowlisted OS vars are forwarded
    - Provider secrets are NEVER forwarded (enforced via RuntimeError)
    - PYTHONPATH is NOT injected by default
    - lex CLI loads its own secrets from its own .env (via CWD)

    Args:
        project_root: Path to lex_study_foundation repo root (used as CWD for subprocess).

    Returns:
        A clean environment dict safe for subprocess use.

    Raises:
        RuntimeError: If a denied secret is detected in the constructed env.
    """
    env: dict[str, str] = {}

    # Forward only allowlisted OS vars
    for key in _ENV_ALLOWLIST:
        val = os.environ.get(key)
        if val is not None:
            env[key] = val

    # Subprocess-specific overrides for clean output
    env["PYTHONIOENCODING"] = "utf-8"
    env["TERM"] = "dumb"
    env["NO_COLOR"] = "1"

    # SECURITY: Hard enforcement — not assert, not warning, a real exception.
    # If a forbidden key somehow appears, fail loudly.
    for key in _NEVER_FORWARD:
        if key in env:
            raise RuntimeError(
                f"SECURITY VIOLATION: '{key}' found in subprocess environment. "
                f"This key is in the deny list and must never be forwarded to "
                f"lex_study_foundation subprocesses. Remove it from the allowlist "
                f"or investigate how it appeared."
            )

    return env


# ── Secret Redaction ─────────────────────────────────────────────

# Patterns that match common secret formats in output/logs
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    # Generic key=value patterns (captures the value portion)
    re.compile(
        r'((?:api[_-]?key|token|secret|password|credential)\s*[=:]\s*)(\S+)',
        re.IGNORECASE,
    ),
    # Anthropic API keys
    re.compile(r'(sk-ant-[a-zA-Z0-9_-]{20,})'),
    # HuggingFace tokens
    re.compile(r'(hf_[a-zA-Z0-9]{20,})'),
    # GitHub Personal Access Tokens
    re.compile(r'(ghp_[a-zA-Z0-9]{36})'),
    # GitHub OAuth tokens
    re.compile(r'(gho_[a-zA-Z0-9]{36})'),
    # Google API keys
    re.compile(r'(AIza[0-9A-Za-z_-]{35})'),
    # OpenAI-style keys
    re.compile(r'(sk-[a-zA-Z0-9]{20,})'),
]


def redact_secrets(text: str) -> str:
    """Replace recognized secret patterns with [REDACTED].

    Applied to:
    - Output lines before buffering and streaming
    - Error messages in job responses
    - Session summary fields
    """
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(
            lambda m: (
                m.group(1) + "[REDACTED]"
                if m.lastindex and m.lastindex > 1
                else "[REDACTED]"
            ),
            text,
        )
    return text
