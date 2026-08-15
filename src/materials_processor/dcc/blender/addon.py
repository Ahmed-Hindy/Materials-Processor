"""Blender Addon interface for the Materials Processor."""

import logging

from materials_processor.dcc.blender.adapters import (
    BlenderMaterialConversionError,
    BlenderMaterialReader,
    convert_active_material,
)

logger = logging.getLogger(__name__)

bl_info = {
    "name": "Materials Processor Blender Integration",
    "author": "Ahmed Hindy",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "Shader Editor > Sidebar > Materials Processor",
    "description": "Ingest, Standardize, and Recreate shader networks in Blender",
    "warning": "",
    "doc_url": "",
    "category": "Material",
}

try:
    import bpy
    from bpy.types import Panel, Operator
except ImportError:
    bpy = None
    Panel = object
    Operator = object

class NODE_OT_MaterialsProcessor_Ingest(Operator):
    """Ingest active material and print standardized schema."""

    bl_idname = "node.matproc_ingest"
    bl_label = "Ingest Material"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not bpy:
            self.report({'ERROR'}, "Blender environment not active.")
            return {'CANCELLED'}

        active_obj = getattr(context, "active_object", None)
        material = active_obj.active_material if active_obj else None
        if not material:
            self.report({'WARNING'}, "No active material found.")
            return {'CANCELLED'}

        try:
            mat_data = BlenderMaterialReader().read(material)

            logger.info("Successfully ingested material: %s", mat_data)
            self.report({'INFO'}, f"Ingested material '{material.name}' successfully.")
            return {'FINISHED'}

        except Exception as e:
            logger.error("Failed to ingest material: %s", e, exc_info=True)
            self.report({'ERROR'}, f"Failed to ingest material: {e}")
            return {'CANCELLED'}


class NODE_OT_MaterialsProcessor_ConvertActiveMaterial(Operator):
    """Strictly rebuild the active material into a separate Blender material."""

    bl_idname = "node.matproc_convert_active_material"
    bl_label = "Convert to Rebuilt Material"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not bpy:
            self.report({'ERROR'}, "Blender environment not active.")
            return {'CANCELLED'}

        active_obj = getattr(context, "active_object", None)
        material = active_obj.active_material if active_obj else None
        if not material:
            self.report({'WARNING'}, "No active material found.")
            return {'CANCELLED'}

        try:
            converted = convert_active_material(active_obj)
        except BlenderMaterialConversionError as exc:
            logger.warning("Strict conversion rejected '%s': %s", material.name, exc)
            self.report({'ERROR'}, f"Cannot convert '{material.name}': {exc.issues[0].detail}")
            return {'CANCELLED'}
        except Exception as exc:
            logger.error("Failed to convert material '%s': %s", material.name, exc, exc_info=True)
            self.report({'ERROR'}, f"Failed to convert '{material.name}': {exc}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Created '{converted.name}' from '{material.name}'.")
        return {'FINISHED'}


class NODE_PT_MaterialsProcessor_Panel(Panel):
    """Sidebar Panel inside Blender Shader Editor."""

    bl_label = "Materials Processor"
    bl_idname = "NODE_PT_matproc_panel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Materials Processor"

    def draw(self, context):
        layout = self.layout
        active_obj = getattr(context, "active_object", None)
        material = active_obj.active_material if active_obj else None

        if material:
            layout.label(text=f"Active Material: {material.name}")
            layout.operator("node.matproc_ingest", text="Ingest & Standardize")
            layout.operator("node.matproc_convert_active_material", text="Convert to Rebuilt Material")
        else:
            layout.label(text="No active material.")


classes = (
    NODE_OT_MaterialsProcessor_Ingest,
    NODE_OT_MaterialsProcessor_ConvertActiveMaterial,
    NODE_PT_MaterialsProcessor_Panel,
)


def register():
    """Register Blender operators and panels."""
    if bpy:
        for cls in classes:
            bpy.utils.register_class(cls)
        logger.info("Materials Processor Addon Registered.")


def unregister():
    """Unregister Blender operators and panels."""
    if bpy:
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)
        logger.info("Materials Processor Addon Unregistered.")


if __name__ == "__main__":
    register()
