"""Shared data models for DeskLink."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class ServerStatus:
    running: bool = False
    local_url: Optional[str] = None
    public_url: Optional[str] = None
    tools_count: int = 0
    auth_enabled: bool = True
    allowed_directories: List[Path] = field(default_factory=list)
