"""Blender Extension entry point for Materials Processor."""

from materials_processor.dcc.blender.addon import register, unregister

__all__ = ("register", "unregister")
