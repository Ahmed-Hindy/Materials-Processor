"""Lightweight UI state containers."""

from dataclasses import dataclass, field


@dataclass
class ConversionUiState:
    """State container for the material conversion UI."""

    selected_node_paths: list[str] = field(default_factory=list)
    target_format: str | None = None
    converted_paths: list[str] = field(default_factory=list)
    failed_paths: list[str] = field(default_factory=list)
    is_running: bool = False
