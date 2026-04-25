"""Config file routes — list and read YAML config files from lex_study_foundation."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ml_intern.config import get_integration_settings
from ml_intern.schemas import ConfigFileContent, ConfigFileInfo


router = APIRouter(prefix="/api/configs", tags=["configs"])


@router.get("", response_model=list[ConfigFileInfo])
async def list_configs():
    """List available YAML config files from lex_study_foundation."""
    config = get_integration_settings()
    config_dir = config.config_dir
    files: list[ConfigFileInfo] = []

    if not config_dir.is_dir():
        return files

    for category_dir in sorted(config_dir.iterdir()):
        if not category_dir.is_dir():
            continue
        category = category_dir.name
        for yaml_file in sorted(category_dir.glob("*.yaml")):
            files.append(
                ConfigFileInfo(
                    name=yaml_file.name,
                    path=f"{category}/{yaml_file.name}",
                    size_bytes=yaml_file.stat().st_size,
                    category=category,
                )
            )
        for yml_file in sorted(category_dir.glob("*.yml")):
            files.append(
                ConfigFileInfo(
                    name=yml_file.name,
                    path=f"{category}/{yml_file.name}",
                    size_bytes=yml_file.stat().st_size,
                    category=category,
                )
            )

    return files


@router.get("/{category}/{name}", response_model=ConfigFileContent)
async def get_config_file(category: str, name: str):
    """Read a specific config file's content.

    Uses resolve() + is_relative_to() for path traversal defense
    instead of string replacement (which can be bypassed).
    """
    config = get_integration_settings()
    config_dir_resolved = config.config_dir.resolve()

    # Construct and resolve the target path
    file_path = (config.config_dir / category / name).resolve()

    # Path traversal check — OWASP recommended pattern
    if not file_path.is_relative_to(config_dir_resolved):
        raise HTTPException(status_code=403, detail="Path traversal denied")

    if not file_path.is_file() or file_path.suffix not in (".yaml", ".yml"):
        raise HTTPException(status_code=404, detail="Config file not found")

    content = file_path.read_text(encoding="utf-8")
    return ConfigFileContent(
        name=file_path.name,
        category=file_path.parent.name,
        content=content,
    )
