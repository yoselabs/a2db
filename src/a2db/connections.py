"""Connection storage — save/load/list database connections as TOML files."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class ConnectionInfo:
    """A saved database connection."""

    project: str
    env: str
    db: str
    dsn: str

    @property
    def scheme(self) -> str:
        """Extract the DSN scheme (e.g., 'postgresql', 'sqlite')."""
        return urlparse(self.dsn).scheme.split("+")[0]

    @property
    def resolved_dsn(self) -> str:
        """DSN with ${ENV_VAR} references expanded from the environment."""
        return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), m.group(0)), self.dsn)


class ConnectionStore:
    """Manages connection TOML files in a config directory."""

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir

    def _path(self, project: str, env: str, db: str) -> Path:
        return self.config_dir / f"{project}-{env}-{db}.toml"

    def save(self, project: str, env: str, db: str, dsn: str) -> Path:
        """Save a connection. Creates or overwrites the TOML file."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(project, env, db)

        def _escape(value: str) -> str:
            return value.replace("\\", "\\\\").replace('"', '\\"')

        content = f'project = "{_escape(project)}"\nenv = "{_escape(env)}"\ndb = "{_escape(db)}"\ndsn = "{_escape(dsn)}"\n'
        path.write_text(content)
        return path

    def load(self, project: str, env: str, db: str) -> ConnectionInfo:
        """Load a connection by its triple. Raises FileNotFoundError if missing."""
        path = self._path(project, env, db)
        if not path.exists():
            raise FileNotFoundError(f"Connection not found: {project}/{env}/{db}")
        data = tomllib.loads(path.read_text())
        return ConnectionInfo(
            project=data["project"],
            env=data["env"],
            db=data["db"],
            dsn=data["dsn"],
        )

    def delete(self, project: str, env: str, db: str) -> None:
        """Delete a connection. Raises FileNotFoundError if missing."""
        path = self._path(project, env, db)
        if not path.exists():
            raise FileNotFoundError(f"Connection not found: {project}/{env}/{db}")
        path.unlink()

    def list_connections(self, project: str | None = None) -> list[ConnectionInfo]:
        """List all saved connections, optionally filtered by project."""
        if not self.config_dir.exists():
            return []
        results = []
        for path in sorted(self.config_dir.glob("*.toml")):
            data = tomllib.loads(path.read_text())
            info = ConnectionInfo(
                project=data["project"],
                env=data["env"],
                db=data["db"],
                dsn=data["dsn"],
            )
            if project is None or info.project == project:
                results.append(info)
        return results
