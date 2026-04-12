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

import urllib.parse
import urllib.request
import urllib.error
import json


class ACOUSTIC_OT_load_from_api(bpy.types.Operator):
    bl_idname = "acoustic.load_from_api"
    bl_label = "Load Acoustic Data"

    def execute(self, context):

        mat = context.material
        prefs = context.preferences.addons["misuka_blender"].preferences

        api_key = prefs.acousticindex_api_key.strip()

        if not api_key:
            self.report({'ERROR'}, "No API key set.")
            return {'CANCELLED'}

        search_query = mat.name.strip()

        if not search_query:
            self.report({'ERROR'}, "Material name required.")
            return {'CANCELLED'}

        search_url = (
            "https://acousticindex.com/api/v1/materials/search"
            f"?q={urllib.parse.quote(search_query)}&limit=1"
        )

        search_req = urllib.request.Request(
            search_url,
            headers={
                "Authorization": f"Bearer {api_key}"
            }
        )

        try:
            with urllib.request.urlopen(search_req) as response:
                search_data = json.loads(response.read().decode())

        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            print("SEARCH API ERROR:", error_body)

            self.report({'ERROR'}, f"Search failed: {e.code}")
            return {'CANCELLED'}

        items = search_data.get("items", [])

        if not items:
            self.report({'ERROR'}, "No AcousticIndex material found.")
            return {'CANCELLED'}

        product_id = items[0]["id"]

        url = f"https://acousticindex.com/api/v1/materials/{product_id}"

        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {api_key}"
            }
        )

        try:
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())

        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            print("LOAD API ERROR:", error_body)

            self.report({'ERROR'}, f"API request failed: {e.code}")
            return {'CANCELLED'}

        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        variants = data.get("variants", [])

        if not variants:
            self.report(
                {'WARNING'},
                f"No acoustic data available for '{data.get('label', 'material')}'"
            )
            return {'CANCELLED'}

        #Select variant with highest overall absorption
        variant = max(variants, key=lambda v: v.get("calculated_absorption", 0))

        #get frequency-dependent absorption data
        #First: third octave data, if not available, try direct octave data
        third_oct = variant.get("alpha_s_third_octave")
        oct_data = variant.get("alpha_s_octave")

        if third_oct:
            # Third octave path
            third_oct_clean = {int(k): v for k, v in third_oct.items()}

            iso_octaves = [63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]

            from .exporter.materials import interpolate_octaves
            oct_vals = interpolate_octaves(third_oct_clean, iso_octaves)

        elif oct_data:
            #Direct octave path
            iso_octaves = [63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]

            freqs = sorted(int(k) for k in oct_data.keys())
            #missing octave values to nearest available frequency
            def get_oct(f):
                if str(f) in oct_data:
                    return oct_data[str(f)]
                if f < freqs[0]:
                    return oct_data[str(freqs[0])]
                if f > freqs[-1]:
                    return oct_data[str(freqs[-1])]
                return 0.5 

            oct_vals = [get_oct(f) for f in iso_octaves]

        else:
            self.report({'WARNING'}, "No usable absorption data available.")
            return {'CANCELLED'}

        print("Acoustic data loaded for:", data.get("label"))

        props = [
            "acoustic_abs_63","acoustic_abs_125","acoustic_abs_250",
            "acoustic_abs_500","acoustic_abs_1000","acoustic_abs_2000",
            "acoustic_abs_4000","acoustic_abs_8000","acoustic_abs_16000"
        ]

        for p, v in zip(props, oct_vals):
            setattr(mat, p, v)

        self.report({'INFO'}, f"Loaded acoustic data for '{data.get('label')}'")
        return {'FINISHED'}
    

def register_acoustic_properties():

    bpy.types.Material.acoustic_abs_63 = FloatProperty(name="Absorption 63Hz", default=0.5, min=0, max=1)
    bpy.types.Material.acoustic_abs_125 = FloatProperty(name="Absorption 125Hz", default=0.5, min=0, max=1)
    bpy.types.Material.acoustic_abs_250 = FloatProperty(name="Absorption 250Hz", default=0.5, min=0, max=1)
    bpy.types.Material.acoustic_abs_500 = FloatProperty(name="Absorption 500Hz", default=0.5, min=0, max=1)
    bpy.types.Material.acoustic_abs_1000 = FloatProperty(name="Absorption 1000Hz", default=0.5, min=0, max=1)
    bpy.types.Material.acoustic_abs_2000 = FloatProperty(name="Absorption 2000Hz", default=0.5, min=0, max=1)
    bpy.types.Material.acoustic_abs_4000 = FloatProperty(name="Absorption 4000Hz", default=0.5, min=0, max=1)
    bpy.types.Material.acoustic_abs_8000 = FloatProperty(name="Absorption 8000Hz", default=0.5, min=0, max=1)
    bpy.types.Material.acoustic_abs_16000 = FloatProperty(name="Absorption 16000Hz", default=0.5, min=0, max=1)

    bpy.types.Material.acoustic_scat_63 = FloatProperty(name="Scattering 63Hz", default=0.25, min=0, max=1)
    bpy.types.Material.acoustic_scat_125 = FloatProperty(name="Scattering 125Hz", default=0.25, min=0, max=1)
    bpy.types.Material.acoustic_scat_250 = FloatProperty(name="Scattering 250Hz", default=0.25, min=0, max=1)
    bpy.types.Material.acoustic_scat_500 = FloatProperty(name="Scattering 500Hz", default=0.25, min=0, max=1)
    bpy.types.Material.acoustic_scat_1000 = FloatProperty(name="Scattering 1000Hz", default=0.25, min=0, max=1)
    bpy.types.Material.acoustic_scat_2000 = FloatProperty(name="Scattering 2000Hz", default=0.25, min=0, max=1)
    bpy.types.Material.acoustic_scat_4000 = FloatProperty(name="Scattering 4000Hz", default=0.25, min=0, max=1)
    bpy.types.Material.acoustic_scat_8000 = FloatProperty(name="Scattering 8000Hz", default=0.25, min=0, max=1)
    bpy.types.Material.acoustic_scat_16000 = FloatProperty(name="Scattering 16000Hz", default=0.25, min=0, max=1)


class ACOUSTIC_PT_material(bpy.types.Panel):

    bl_label = "Acoustic Material"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"

    def draw(self, context):

        layout = self.layout
        mat = context.material

        addon_name = __name__.split(".")[0]
        prefs = context.preferences.addons[addon_name].preferences

        if mat is None:
            return

        col = layout.column()

# Header
        col.label(text="AcousticIndex Database")

        # db use instructions
        box = col.box()
        box.label(text="How to use:", icon='QUESTION')
        box.label(text="1. Rename material to match database name")
        box.label(text="2. Enter your API Key")
        box.label(text="3. Click 'Load from Database'")

        # API Key (volle Breite)
        col.prop(prefs, "acousticindex_api_key", text="API Key")

        # Button (volle Breite + hervorgehoben)
        row = col.row()
        row.scale_y = 1.2
        row.operator(
            "acoustic.load_from_api",
            text="Load from Database",
            icon='IMPORT'
        )

        col.separator()

        #manual input
        col.label(text="Absorption")

        col.prop(mat, "acoustic_abs_63")
        col.prop(mat, "acoustic_abs_125")
        col.prop(mat, "acoustic_abs_250")
        col.prop(mat, "acoustic_abs_500")
        col.prop(mat, "acoustic_abs_1000")
        col.prop(mat, "acoustic_abs_2000")
        col.prop(mat, "acoustic_abs_4000")
        col.prop(mat, "acoustic_abs_8000")
        col.prop(mat, "acoustic_abs_16000")

        row = col.row(align=True)
        row.operator("acoustic.interpolate_abs", text="Interpolate 1 or 2 Values")
        row.operator("acoustic.reset_abs", text="Reset to 0.5")

        col.separator()

        col.label(text="Scattering")

        col.prop(mat, "acoustic_scat_63")
        col.prop(mat, "acoustic_scat_125")
        col.prop(mat, "acoustic_scat_250")
        col.prop(mat, "acoustic_scat_500")
        col.prop(mat, "acoustic_scat_1000")
        col.prop(mat, "acoustic_scat_2000")
        col.prop(mat, "acoustic_scat_4000")
        col.prop(mat, "acoustic_scat_8000")
        col.prop(mat, "acoustic_scat_16000")

        row = col.row(align=True)
        row.operator("acoustic.interpolate_scat", text="Interpolate 1 or 2 Values")
        row.operator("acoustic.reset_scat", text="Reset to 0.25")
        

class ACOUSTIC_OT_interpolate_abs(bpy.types.Operator):
    bl_idname = "acoustic.interpolate_abs"
    bl_label = "Interpolate Absorption"

    def execute(self, context):

        mat = context.material
        iso_octaves = [63,125,250,500,1000,2000,4000,8000,16000]

        props = [
            "acoustic_abs_63","acoustic_abs_125","acoustic_abs_250",
            "acoustic_abs_500","acoustic_abs_1000","acoustic_abs_2000",
            "acoustic_abs_4000","acoustic_abs_8000","acoustic_abs_16000"
        ]

        data = {}

        for f, p in zip(iso_octaves, props):
            v = getattr(mat, p)
            if v != 0.5:
                data[f] = v

        if len(data) > 2:
            freqs = sorted(data.keys())
            data = {
                freqs[0]: data[freqs[0]],
                freqs[-1]: data[freqs[-1]]
            }

        if data:
            vals = interpolate_octaves(data, iso_octaves)

            for p, v in zip(props, vals):
                setattr(mat, p, v)

        return {'FINISHED'}
    
class ACOUSTIC_OT_interpolate_scat(bpy.types.Operator):
    bl_idname = "acoustic.interpolate_scat"
    bl_label = "Interpolate Scattering"

    def execute(self, context):

        mat = context.material
        iso_octaves = [63,125,250,500,1000,2000,4000,8000,16000]

        props = [
            "acoustic_scat_63","acoustic_scat_125","acoustic_scat_250",
            "acoustic_scat_500","acoustic_scat_1000","acoustic_scat_2000",
            "acoustic_scat_4000","acoustic_scat_8000","acoustic_scat_16000"
        ]

        data = {}

        for f, p in zip(iso_octaves, props):
            v = getattr(mat, p)
            if v != 0.25:
                data[f] = v

        if len(data) > 2:
            freqs = sorted(data.keys())
            data = {
                freqs[0]: data[freqs[0]],
                freqs[-1]: data[freqs[-1]]
            }

        if data:
            vals = interpolate_octaves(data, iso_octaves)

            for p, v in zip(props, vals):
                setattr(mat, p, v)

        return {'FINISHED'}

class ACOUSTIC_OT_reset_abs(bpy.types.Operator):
    bl_idname = "acoustic.reset_abs"
    bl_label = "Reset Absorption"

    def execute(self, context):

        mat = context.material

        props = [
            "acoustic_abs_63","acoustic_abs_125","acoustic_abs_250",
            "acoustic_abs_500","acoustic_abs_1000","acoustic_abs_2000",
            "acoustic_abs_4000","acoustic_abs_8000","acoustic_abs_16000"
        ]

        for p in props:
            setattr(mat, p, 0.5)

        return {'FINISHED'}
    
class ACOUSTIC_OT_reset_scat(bpy.types.Operator):
    bl_idname = "acoustic.reset_scat"
    bl_label = "Reset Scattering"

    def execute(self, context):

        mat = context.material

        props = [
            "acoustic_scat_63","acoustic_scat_125","acoustic_scat_250",
            "acoustic_scat_500","acoustic_scat_1000","acoustic_scat_2000",
            "acoustic_scat_4000","acoustic_scat_8000","acoustic_scat_16000"
        ]

        for p in props:
            setattr(mat, p, 0.25)

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
    ACOUSTIC_OT_reset_abs,
    ACOUSTIC_OT_reset_scat,
    ACOUSTIC_OT_interpolate_abs,
    ACOUSTIC_OT_interpolate_scat,
    ACOUSTIC_OT_load_from_api
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
    del bpy.types.Material.acoustic_abs_16000

    del bpy.types.Material.acoustic_scat_63
    del bpy.types.Material.acoustic_scat_125
    del bpy.types.Material.acoustic_scat_250
    del bpy.types.Material.acoustic_scat_500
    del bpy.types.Material.acoustic_scat_1000
    del bpy.types.Material.acoustic_scat_2000
    del bpy.types.Material.acoustic_scat_4000
    del bpy.types.Material.acoustic_scat_8000
    del bpy.types.Material.acoustic_scat_16000

    bpy.types.TOPBAR_MT_file_export.remove(menu_export_func)
    bpy.types.TOPBAR_MT_file_import.remove(menu_import_func)
