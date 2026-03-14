if "bpy" in locals():
    import importlib
    if "bl_utils" in locals():
        importlib.reload(bl_utils)
    if "importer" in locals():
        importlib.reload(importer)
    if "exporter" in locals():
        importlib.reload(exporter)

import bpy
from bpy.props import (
        StringProperty,
        BoolProperty,
        FloatProperty,
    )
from bpy_extras.io_utils import (
        ImportHelper,
        ExportHelper,
        orientation_helper,
        axis_conversion
    )

from . import bl_utils
from . import importer
from . import exporter
from .exporter.materials import interpolate_octaves

# ---------- Acoustic Material UI ----------

def register_acoustic_properties():

    bpy.types.Material.acoustic_abs_63 = FloatProperty(name="Absorption 63Hz", default=0.5, min=0, max=1)
    bpy.types.Material.acoustic_abs_125 = FloatProperty(name="Absorption 125Hz", default=0.5, min=0, max=1)
    bpy.types.Material.acoustic_abs_250 = FloatProperty(name="Absorption 250Hz", default=0.5, min=0, max=1)
    bpy.types.Material.acoustic_abs_500 = FloatProperty(name="Absorption 500Hz", default=0.5, min=0, max=1)
    bpy.types.Material.acoustic_abs_1000 = FloatProperty(name="Absorption 1000Hz", default=0.5, min=0, max=1)
    bpy.types.Material.acoustic_abs_2000 = FloatProperty(name="Absorption 2000Hz", default=0.5, min=0, max=1)
    bpy.types.Material.acoustic_abs_4000 = FloatProperty(name="Absorption 4000Hz", default=0.5, min=0, max=1)
    bpy.types.Material.acoustic_abs_8000 = FloatProperty(name="Absorption 8000Hz", default=0.5, min=0, max=1)

    bpy.types.Material.acoustic_scattering = FloatProperty(name="Scattering", default=0.5, min=0, max=1)


class ACOUSTIC_PT_material(bpy.types.Panel):

    bl_label = "Acoustic Material"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"

    def draw(self, context):

        layout = self.layout
        mat = context.material

        if mat is None:
            return

        col = layout.column()

        col.operator("acoustic.reset", text="Reset All Values")

        col.separator()

        col.label(text="Absorption")

        col.prop(mat, "acoustic_abs_63")
        col.prop(mat, "acoustic_abs_125")
        col.prop(mat, "acoustic_abs_250")
        col.prop(mat, "acoustic_abs_500")
        col.prop(mat, "acoustic_abs_1000")
        col.prop(mat, "acoustic_abs_2000")
        col.prop(mat, "acoustic_abs_4000")
        col.prop(mat, "acoustic_abs_8000")

        col.operator("acoustic.interpolate", text="Interpolate")

        col.separator()

        col.prop(mat, "acoustic_scattering")
        

class ACOUSTIC_OT_interpolate(bpy.types.Operator):

    bl_idname = "acoustic.interpolate"
    bl_label = "Interpolate Missing Values"

    def execute(self, context):

        mat = context.material

        if mat is None:
            return {'CANCELLED'}

        iso_octaves = [63,125,250,500,1000,2000,4000,8000]

        props = [
            "acoustic_abs_63",
            "acoustic_abs_125",
            "acoustic_abs_250",
            "acoustic_abs_500",
            "acoustic_abs_1000",
            "acoustic_abs_2000",
            "acoustic_abs_4000",
            "acoustic_abs_8000"
        ]

        values = [getattr(mat, p) for p in props]

        # build dict of manually set values
        abs_data = {}

        for f, v in zip(iso_octaves, values):
            if v != 0.5:
                abs_data[f] = v

        if len(abs_data) > 2:
            freqs = sorted(abs_data.keys())
            abs_data = {
                freqs[0]: abs_data[freqs[0]],
                freqs[-1]: abs_data[freqs[-1]]
            }

        if abs_data:
            new_vals = interpolate_octaves(abs_data, iso_octaves)

            for p, v in zip(props, new_vals):
                setattr(mat, p, v)

        return {'FINISHED'}

class ACOUSTIC_OT_reset(bpy.types.Operator):
    bl_idname = "acoustic.reset"
    bl_label = "Reset Acoustic Values"

    def execute(self, context):

        mat = context.material

        freqs = [
            "acoustic_abs_63",
            "acoustic_abs_125",
            "acoustic_abs_250",
            "acoustic_abs_500",
            "acoustic_abs_1000",
            "acoustic_abs_2000",
            "acoustic_abs_4000",
            "acoustic_abs_8000",
        ]

        for f in freqs:
            setattr(mat, f, 0.5)

        mat.acoustic_scattering = 0.5

        return {'FINISHED'}


@orientation_helper(axis_forward='-Z', axis_up='Y')
class ImportMistuba(bpy.types.Operator, ImportHelper):
    """Import a Mitsuba scene"""
    bl_idname = "import_scene.mitsuba"
    bl_label = "Mitsuba Import"

    filename_ext = ".xml"
    filter_glob: StringProperty(default="*.xml", options={'HIDDEN'})

    override_scene: BoolProperty(
        name = 'Override Current Scene',
        description = 'Override the current scene with the imported Mitsuba scene. '
                      'Otherwise, creates a new scene for Mitsuba objects.',
        default = True,
    )

    def execute(self, context):
        # Set blender to object mode
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        axis_mat = axis_conversion(
            to_forward=self.axis_forward,
            to_up=self.axis_up,
        ).to_4x4()

        if self.override_scene:
            # Clear the current scene
            scene = bl_utils.init_empty_scene(context, name=bpy.context.scene.name)
        else:
            # Create a new scene for Mitsuba objects
            scene = bl_utils.init_empty_scene(context, name='Mitsuba')
        collection = scene.collection

        try:
            importer.load_mitsuba_scene(context, scene, collection, self.filepath, axis_mat)
        except (RuntimeError, NotImplementedError) as e:
            print(e)
            self.report({'ERROR'}, "Failed to load Mitsuba scene. See error log.")
            return {'CANCELLED'}

        bpy.context.window.scene = scene

        self.report({'INFO'}, "Scene imported successfully.")

        return {'FINISHED'}


@orientation_helper(axis_forward='-Z', axis_up='Y')
class ExportMitsuba(bpy.types.Operator, ExportHelper):
    """Export as a Mitsuba scene"""
    bl_idname = "export_scene.mitsuba"
    bl_label = "Mitsuba Export"

    filename_ext = ".xml"
    filter_glob: StringProperty(default="*.xml", options={'HIDDEN'})

    use_selection: BoolProperty(
	        name = "Selection Only",
	        description="Export selected objects only",
	        default = False,
	    )

    split_files: BoolProperty(
            name = "Split File",
            description = "Split scene XML file in smaller fragments",
            default = False
    )

    export_ids: BoolProperty(
            name = "Export IDs",
            description = "Add an 'id' field for each object (shape, emitter, camera...)",
            default = False
    )

    ignore_background: BoolProperty(
            name = "Ignore Default Background",
            description = "Ignore blender's default constant gray background when exporting to Mitsuba.",
            default = True
    )

    #MISUKA check box in export window
    acoustic_mode: bpy.props.BoolProperty(                  
        name="MISUKA: Acoustic Mode",
        description="Export MISUKA acoustic scene",
        default=True
    )


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reset()

    def reset(self):
        self.converter = exporter.SceneConverter()

    def execute(self, context):
        # Conversion matrix to shift the "Up" Vector. This can be useful when exporting single objects to an existing mitsuba scene.
        axis_mat = axis_conversion(
	            to_forward=self.axis_forward,
	            to_up=self.axis_up,
	        ).to_4x4()

        self.converter.export_ctx.axis_mat = axis_mat
        # Add IDs to all base plugins (shape, emitter, sensor...)
        self.converter.export_ctx.export_ids = self.export_ids
        self.converter.export_ctx.acoustic_mode = self.acoustic_mode #add acoustic mode to export context

        self.converter.use_selection = self.use_selection

        # Set path to scene .xml file
        self.converter.set_path(self.filepath, split_files=self.split_files)

        window_manager = context.window_manager

        deps_graph = context.evaluated_depsgraph_get()

        total_progress = len(deps_graph.object_instances)
        window_manager.progress_begin(0, total_progress)

        self.converter.scene_to_dict(deps_graph, window_manager)
        #write data to scene .xml file
        self.converter.dict_to_xml()

        window_manager.progress_end()

        self.report({'INFO'}, "Scene exported successfully!")

        #reset the exporter
        self.reset()

        return {'FINISHED'}


def menu_export_func(self, context):
    self.layout.operator(ExportMitsuba.bl_idname, text="Mitsuba (.xml)")

def menu_import_func(self, context):
    self.layout.operator(ImportMistuba.bl_idname, text="Mitsuba (.xml)")


classes = (
    ImportMistuba,
    ExportMitsuba,
    ACOUSTIC_PT_material,
    ACOUSTIC_OT_reset,
    ACOUSTIC_OT_interpolate
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    register_acoustic_properties()

    bpy.types.TOPBAR_MT_file_export.append(menu_export_func)
    bpy.types.TOPBAR_MT_file_import.append(menu_import_func)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    del bpy.types.Material.acoustic_abs_63
    del bpy.types.Material.acoustic_abs_125
    del bpy.types.Material.acoustic_abs_250
    del bpy.types.Material.acoustic_abs_500
    del bpy.types.Material.acoustic_abs_1000
    del bpy.types.Material.acoustic_abs_2000
    del bpy.types.Material.acoustic_abs_4000
    del bpy.types.Material.acoustic_abs_8000
    del bpy.types.Material.acoustic_scattering

    bpy.types.TOPBAR_MT_file_export.remove(menu_export_func)
    bpy.types.TOPBAR_MT_file_import.remove(menu_import_func)
