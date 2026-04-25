"""Command allowlist registry.

Only commands registered here can be executed through the dashboard.
New commands must be added explicitly — no arbitrary frontend input
reaches subprocess.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CommandSpec:
    """Specification for an allowed CLI command."""

    name: str
    description: str
    phase: int
    timeout: int = 30
    needs_config: bool = False
    allowed_flags: list[str] = field(default_factory=list)


# ── Registry ─────────────────────────────────────────────────────
# Only these commands can be invoked through the dashboard.
# The keys are the exact CLI subcommand names.

COMMAND_REGISTRY: dict[str, CommandSpec] = {
    "doctor": CommandSpec(
        name="doctor",
        description="Environment health check",
        phase=1,
        timeout=30,
    ),
    "info": CommandSpec(
        name="info",
        description="Project metadata and version",
        phase=1,
        timeout=10,
    ),
    "paths": CommandSpec(
        name="paths",
        description="Resolved project directory paths",
        phase=1,
        timeout=10,
    ),
    "validate-config": CommandSpec(
        name="validate-config",
        description="Validate a YAML config file",
        phase=1,
        timeout=15,
        needs_config=True,
        allowed_flags=["--type"],
    ),
}


def get_command(name: str) -> CommandSpec | None:
    """Look up a command by name. Returns None if not in allowlist."""
    return COMMAND_REGISTRY.get(name)


def is_allowed(name: str) -> bool:
    """Check if a command is in the allowlist."""
    return name in COMMAND_REGISTRY


def all_commands() -> dict[str, CommandSpec]:
    """Return the full registry."""
    return COMMAND_REGISTRY


def build_args(spec: CommandSpec, config_file: str | None, flags: dict[str, str | bool]) -> list[str]:
    """Build safe subprocess args from a command spec and user input.

    Only flags declared in the spec's allowed_flags are passed through.
    Config file names are sanitized (no path traversal).
    """
    args: list[str] = [spec.name]

    # Config file argument (positional for validate-config)
    if spec.needs_config and config_file:
        # Sanitize: only allow filenames within configs dir, no path traversal
        safe_name = config_file.replace("\\", "/").split("/")[-1]
        if not safe_name.endswith((".yaml", ".yml")):
            raise ValueError(f"Invalid config file: {safe_name}")
        args.append(safe_name)

    # Typed flags
    for flag_name, flag_value in flags.items():
        flag_key = f"--{flag_name}" if not flag_name.startswith("--") else flag_name
        if flag_key not in spec.allowed_flags:
            continue  # silently skip disallowed flags
        if isinstance(flag_value, bool):
            if flag_value:
                args.append(flag_key)
        else:
            args.extend([flag_key, str(flag_value)])

    return args
