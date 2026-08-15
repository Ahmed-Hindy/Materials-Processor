"""Blender Extension entry point for Materials Processor."""

import sys

from . import materials_processor as _materials_processor

# Blender loads extensions under their repository namespace (``bl_ext.*``),
# while the shared package deliberately uses ``materials_processor`` imports.
# Make the bundled package available under that stable application name before
# importing the add-on implementation.
sys.modules["materials_processor"] = _materials_processor

from .materials_processor.dcc.blender.addon import register, unregister  # noqa: E402

__all__ = ("register", "unregister")
