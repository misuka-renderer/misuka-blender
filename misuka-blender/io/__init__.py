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
        addon_name = __name__.split(".")[0]
        addon = context.preferences.addons.get(addon_name)

        if not addon:
            self.report({'ERROR'}, "Addon Preferences not found")
            return {'CANCELLED'}

        api_key = addon.preferences.acousticindex_api_key.strip()

        if not api_key:
            self.report({'ERROR'}, "No API Key set in Addon Preferences")
            return {'CANCELLED'}

        search_query = mat.name.strip()

        if not search_query:
            self.report({'ERROR'}, "Material name required.")
            return {'CANCELLED'}

        # ID or search
        if "-" in search_query and len(search_query) > 30:
            product_id = search_query

        else:
            search_url = (
                "https://acousticindex.com/api/v1/materials/search"
                f"?q={urllib.parse.quote(search_query)}&limit=1"
            )

            search_req = urllib.request.Request(
                search_url,
                headers={"Authorization": f"Bearer {api_key}"}
            )

            try:
                with urllib.request.urlopen(search_req) as response:
                    search_data = json.loads(response.read().decode())
            except urllib.error.HTTPError as e:
                self.report({'ERROR'}, f"Search failed: {e.code}")
                return {'CANCELLED'}

            items = search_data.get("items", [])
            if not items:
                self.report({'ERROR'}, "No AcousticIndex material found.")
                return {'CANCELLED'}

            product_id = items[0]["id"]

        # --- load material detail ---
        url = f"https://acousticindex.com/api/v1/materials/{product_id}"

        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {api_key}"}
        )

        try:
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())

        except urllib.error.HTTPError as e:
            self.report({'ERROR'}, f"API request failed: {e.code}")
            return {'CANCELLED'}

        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        # --- extract measurement variants ---
        measurements = data.get("measurements", {})

        abs_variants = measurements.get("absorption_iso_354", [])
        scat_variants = measurements.get("scatter_iso_17497_1", [])

        # tag type so we can distinguish later
        for v in abs_variants:
            v["_type"] = "absorption"

        for v in scat_variants:
            v["_type"] = "scattering"

        variants = abs_variants + scat_variants

        if not variants:
            self.report({'WARNING'}, "No measurement data available.")
            return {'CANCELLED'}

        # store variants + raw data
        mat["_acoustic_variants_cache"] = variants
        mat["_acoustic_raw_data"] = data

        #show feedback for UI ---
        mat["_acoustic_loaded_label"] = data.get("label", "")
        mat["_acoustic_loaded_manufacturer"] = data.get("manufacturer", "")

        self.report({'INFO'}, f"{len(variants)} variants loaded")
        return {'FINISHED'}
        
    
class ACOUSTIC_OT_apply_variant(bpy.types.Operator):
    bl_idname = "acoustic.apply_variant"
    bl_label = "Apply Variant"

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):

        layout = self.layout
        mat = context.material
        variants = mat.get("_acoustic_variants_cache", [])

        text = "Overwrite values?"

        if variants:
            selection = getattr(mat, "acoustic_variant_enum", "NONE")

            if selection == "NONE":
                abs_variants = [v for v in variants if v.get("_type") == "absorption"]
                scat_variants = [v for v in variants if v.get("_type") == "scattering"]

                if abs_variants:
                    variant = max(
                        abs_variants,
                        key=lambda v: v.get("calculated_absorption", 0)
                    )
                elif scat_variants:
                    variant = scat_variants[0]
                else:
                    variant = None
            else:
                idx = int(selection)
                variant = variants[idx] if idx < len(variants) else None

            if variant:
                vtype = variant.get("_type")

                if vtype == "absorption":
                    text = "Overwrite absorption values?"

                elif vtype == "scattering":
                    text = "Overwrite scattering values?"

        layout.label(text=text, icon='ERROR')

    def execute(self, context):

        mat = context.material
        variants = mat.get("_acoustic_variants_cache", [])

        if not variants:
            self.report({'ERROR'}, "No variants loaded.")
            return {'CANCELLED'}

        selection = getattr(mat, "acoustic_variant_enum", "NONE")

        if selection == "NONE":

            # prefer absorption if available
            abs_variants = [v for v in variants if v.get("_type") == "absorption"]
            scat_variants = [v for v in variants if v.get("_type") == "scattering"]

            if abs_variants:
                variant = max(abs_variants, key=lambda v: v.get("calculated_absorption", 0))

            elif scat_variants:
                # no ranking available → fallback
                variant = scat_variants[0]

            else:
                self.report({'ERROR'}, "No usable variants")
                return {'CANCELLED'}

        else:
            idx = int(selection)

            if idx >= len(variants):
                self.report({'ERROR'}, "Variant index out of range")
                return {'CANCELLED'}

            variant = variants[idx]

        iso_octaves = [63,125,250,500,1000,2000,4000,8000,16000]

        variant_type = variant.get("_type")

        # =========================================================
        # --- ABSORPTION ---
        # =========================================================
        if variant_type == "absorption":

            third_oct = variant.get("alpha_s_third_octave")
            oct_data = variant.get("alpha_s_octave")

            if third_oct:
                third_oct_clean = {int(k): v for k, v in third_oct.items()}
                oct_vals = interpolate_octaves(third_oct_clean, iso_octaves)

            elif oct_data:
                freqs = sorted(int(k) for k in oct_data.keys())

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
                self.report({'ERROR'}, "No absorption data")
                return {'CANCELLED'}

            absorp_props = [
                "acoustic_abs_63","acoustic_abs_125","acoustic_abs_250",
                "acoustic_abs_500","acoustic_abs_1000","acoustic_abs_2000",
                "acoustic_abs_4000","acoustic_abs_8000","acoustic_abs_16000"
            ]

            for p, v in zip(absorp_props, oct_vals):
                setattr(mat, p, v)

        # =========================================================
        # --- SCATTERING ---
        # =========================================================
        elif variant_type == "scattering":

            s_terz = variant.get("scatter_third_octave")
            s_oct = variant.get("scatter_octave")

            if s_terz:
                s_terz_clean = {int(k): v for k, v in s_terz.items()}
                s_vals = interpolate_octaves(s_terz_clean, iso_octaves)

            elif s_oct:
                freqs = sorted(int(k) for k in s_oct.keys())

                def get_s(f):
                    if f in s_oct:
                        return s_oct[f]
                    if f < freqs[0]:
                        return s_oct[freqs[0]]
                    if f > freqs[-1]:
                        return s_oct[freqs[-1]]
                    return 0.25

                s_vals = [get_s(f) for f in iso_octaves]

            else:
                s_vals = [0.25] * len(iso_octaves)

            scatter_props = [
                "acoustic_scat_63","acoustic_scat_125","acoustic_scat_250",
                "acoustic_scat_500","acoustic_scat_1000","acoustic_scat_2000",
                "acoustic_scat_4000","acoustic_scat_8000","acoustic_scat_16000"
            ]

            for p, v in zip(scatter_props, s_vals):
                setattr(mat, p, v)

        else:
            self.report({'ERROR'}, "Unknown variant type")
            return {'CANCELLED'}

        self.report({'INFO'}, "Variant applied")
        return {'FINISHED'}
    
def register_acoustic_properties():

    bpy.types.Material.acoustic_abs_63 = FloatProperty(name="Absorption 63Hz", default=0.5, min=0, max=2)
    bpy.types.Material.acoustic_abs_125 = FloatProperty(name="Absorption 125Hz", default=0.5, min=0, max=2)
    bpy.types.Material.acoustic_abs_250 = FloatProperty(name="Absorption 250Hz", default=0.5, min=0, max=2)
    bpy.types.Material.acoustic_abs_500 = FloatProperty(name="Absorption 500Hz", default=0.5, min=0, max=2)
    bpy.types.Material.acoustic_abs_1000 = FloatProperty(name="Absorption 1000Hz", default=0.5, min=0, max=2)
    bpy.types.Material.acoustic_abs_2000 = FloatProperty(name="Absorption 2000Hz", default=0.5, min=0, max=2)
    bpy.types.Material.acoustic_abs_4000 = FloatProperty(name="Absorption 4000Hz", default=0.5, min=0, max=2)
    bpy.types.Material.acoustic_abs_8000 = FloatProperty(name="Absorption 8000Hz", default=0.5, min=0, max=2)
    bpy.types.Material.acoustic_abs_16000 = FloatProperty(name="Absorption 16000Hz", default=0.5, min=0, max=2)

    bpy.types.Material.acoustic_scat_63 = FloatProperty(name="Scattering 63Hz", default=0.25, min=0, max=1)
    bpy.types.Material.acoustic_scat_125 = FloatProperty(name="Scattering 125Hz", default=0.25, min=0, max=1)
    bpy.types.Material.acoustic_scat_250 = FloatProperty(name="Scattering 250Hz", default=0.25, min=0, max=1)
    bpy.types.Material.acoustic_scat_500 = FloatProperty(name="Scattering 500Hz", default=0.25, min=0, max=1)
    bpy.types.Material.acoustic_scat_1000 = FloatProperty(name="Scattering 1000Hz", default=0.25, min=0, max=1)
    bpy.types.Material.acoustic_scat_2000 = FloatProperty(name="Scattering 2000Hz", default=0.25, min=0, max=1)
    bpy.types.Material.acoustic_scat_4000 = FloatProperty(name="Scattering 4000Hz", default=0.25, min=0, max=1)
    bpy.types.Material.acoustic_scat_8000 = FloatProperty(name="Scattering 8000Hz", default=0.25, min=0, max=1)
    bpy.types.Material.acoustic_scat_16000 = FloatProperty(name="Scattering 16000Hz", default=0.25, min=0, max=1)

    bpy.types.Material.acoustic_specular_lobe_width = FloatProperty(
    name="Specular Lobe Width",
    default=0.001,
    min=0.001,
    max=1.0,
    precision=3
)

    def get_variant_items(self, context):

        mat = getattr(context, "material", None)

        if mat is None:
            return [("NONE", "Auto Selection", "")]
        
        variants = mat.get("_acoustic_variants_cache", [])

        items = []

        # --- auto selection label ---
        has_abs = any(v.get("_type") == "absorption" for v in variants)
        has_scat = any(v.get("_type") == "scattering" for v in variants)

        if has_abs:
            auto_label = "Auto Selection (best Absorption)"
        elif has_scat:
            auto_label = "Auto Selection (Scattering)"
        else:
            auto_label = "Auto Selection"

        items.append(("NONE", auto_label, ""))

        # --- variant items ---
        for i, v in enumerate(variants):
            label = v.get("label", f"Variant {i+1}")
            variant_type = v.get("_type")

            if variant_type == "scattering":
                label = label.replace("Scatter", "Scattering")

            extra = []

            # thickness
            thickness = v.get("thickness_mm")
            if thickness:
                extra.append(f"{thickness}mm")

            # air gap (optional)
            air_gap = v.get("air_gap_mm")
            if air_gap:
                extra.append(f"air {air_gap}mm")

            # performance (absorption only)
            alpha = v.get("calculated_absorption")
            if alpha is not None:
                extra.append(f"a={alpha:.2f}")

            if extra:
                label = f"{label} ({', '.join(extra)})"

            items.append((str(i), label, ""))

        return items


    bpy.types.Material.acoustic_variant_enum = bpy.props.EnumProperty(
        name="Variant",
        items=get_variant_items,
    )

    bpy.types.Material.show_acoustic_help = BoolProperty(
        name="Database Instructions",
        default=True
    )

    bpy.types.Material.show_acoustic_info = BoolProperty(
        name="Show Info",
        default=True
    )


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

        # Header
        col.label(text="AcousticIndex Database")

        # db use instructions
        row = col.row()
        row.prop(mat, "show_acoustic_help", icon="TRIA_DOWN" if mat.show_acoustic_help else "TRIA_RIGHT", icon_only=True, emboss=False)
        row.label(text="Database: How to use")

        if mat.show_acoustic_help:
            box = col.box()
            box.label(text="1. Rename material to match database name/id")
            box.label(text="2. Set API Key in Addon Preferences")
            box.label(text="3. Click 'Load from Database'")
            box.label(text="4. Select variant")
            box.label(text="5. Click 'Apply Variant'")

        col.separator()

        row = col.row()
        row.label(text="API Key in Addon Preferences", icon='PREFERENCES')
        # Button 
        row = col.row()
        row.scale_y = 1.2
        row.operator(
            "acoustic.load_from_api",
            text="Load from Database",
            icon='IMPORT'
        )

        # --- DB feedback ---
        label = mat.get("_acoustic_loaded_label")
        manufacturer = mat.get("_acoustic_loaded_manufacturer")

        if label:
            box = col.box()

            row = box.row()
            row.label(text="Matched Database Entry", icon='CHECKMARK')

            box.label(text=label)

            if manufacturer:
                box.label(text=manufacturer)

        col.separator()
        col.label(text="Variant Selection")
        col.prop(mat, "acoustic_variant_enum", text="")

        # IMPORTANT: force invoke() instead of execute()
        col.operator_context = 'INVOKE_DEFAULT'

        row = col.row()
        row.operator(
            "acoustic.apply_variant",
            text="Apply Variant",
            icon='CHECKMARK'
        )

        col.separator()

        row = col.row()
        row.prop(mat, "show_acoustic_info", icon="TRIA_DOWN" if mat.show_acoustic_info else "TRIA_RIGHT", icon_only=True, emboss=False)
        row.label(text="Manual Input: How to use")

        if mat.show_acoustic_info:
            box = col.box()
            box.label(text="• Set one or more frequency values")
            box.label(text="• 1 value → all bands set equal")
            box.label(text="• 2+ values → interpolated between set points")
            box.label(text="• Outer bands use nearest value")
            box.label(text="• Use Reset to redefine interpolation")

            box.separator()

            # --- key rule (highlighted) ---
            row = box.row()
            row.alert = True
            row.label(text="Only values different from default are used for interpolation", icon='INFO')

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
        row.operator("acoustic.interpolate_abs", text="Interpolate Values")
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
        row.operator("acoustic.interpolate_scat", text="Interpolate Values")
        row.operator("acoustic.reset_scat", text="Reset to 0.25")

        col.separator()

        col.label(text="Specular Lobe Width")
        col.prop(mat, "acoustic_specular_lobe_width")

        row = col.row(align=True)
        row.operator(
            "acoustic.reset_specular_lobe_width",
            text="Reset to 0.001"
        )


class ACOUSTIC_OT_interpolate_abs(bpy.types.Operator):
    bl_idname = "acoustic.interpolate_abs"
    bl_label = "Change Absorption Values"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):

        mat = context.material

        iso_octaves = [63,125,250,500,1000,2000,4000,8000,16000]

        props = [
            "acoustic_abs_63","acoustic_abs_125","acoustic_abs_250",
            "acoustic_abs_500","acoustic_abs_1000","acoustic_abs_2000",
            "acoustic_abs_4000","acoustic_abs_8000","acoustic_abs_16000"
        ]

        data = {}

        # collect all user-defined values (≠ default)
        for f, p in zip(iso_octaves, props):
            v = getattr(mat, p)
            if abs(v - 0.5) > 1e-6:
                data[f] = v

        if not data:
            return {'FINISHED'}

        vals = interpolate_octaves(data, iso_octaves)

        for p, v in zip(props, vals):
            setattr(mat, p, v)

        return {'FINISHED'}
    
class ACOUSTIC_OT_interpolate_scat(bpy.types.Operator):
    bl_idname = "acoustic.interpolate_scat"
    bl_label = "Change Scattering Values"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):

        mat = context.material

        iso_octaves = [63,125,250,500,1000,2000,4000,8000,16000]

        props = [
            "acoustic_scat_63","acoustic_scat_125","acoustic_scat_250",
            "acoustic_scat_500","acoustic_scat_1000","acoustic_scat_2000",
            "acoustic_scat_4000","acoustic_scat_8000","acoustic_scat_16000"
        ]

        data = {}

        # collect user-defined values (≠ default 0.25)
        for f, p in zip(iso_octaves, props):
            v = getattr(mat, p)
            if abs(v - 0.25) > 1e-6:
                data[f] = v

        if not data:
            return {'FINISHED'}

        vals = interpolate_octaves(data, iso_octaves)

        for p, v in zip(props, vals):
            setattr(mat, p, v)

        return {'FINISHED'}

class ACOUSTIC_OT_reset_abs(bpy.types.Operator):
    bl_idname = "acoustic.reset_abs"
    bl_label = "Reset Absorption"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):

        mat = context.material

        props = [
            "acoustic_abs_63","acoustic_abs_125","acoustic_abs_250",
            "acoustic_abs_500","acoustic_abs_1000","acoustic_abs_2000",
            "acoustic_abs_4000","acoustic_abs_8000","acoustic_abs_16000"
        ]

        for p in props:
            setattr(mat, p, 0.5)

        # clear interpolation state
        mat["acoustic_abs_set"] = []
        mat["_last_abs_values"] = {}

        return {'FINISHED'}
    
class ACOUSTIC_OT_reset_scat(bpy.types.Operator):
    bl_idname = "acoustic.reset_scat"
    bl_label = "Reset Scattering"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):

        mat = context.material

        props = [
            "acoustic_scat_63","acoustic_scat_125","acoustic_scat_250",
            "acoustic_scat_500","acoustic_scat_1000","acoustic_scat_2000",
            "acoustic_scat_4000","acoustic_scat_8000","acoustic_scat_16000"
        ]

        for p in props:
            setattr(mat, p, 0.25)

        # clear interpolation state
        mat["acoustic_scat_set"] = []
        mat["_last_scat_values"] = {}

        return {'FINISHED'}   

class ACOUSTIC_OT_reset_specular_lobe_width(bpy.types.Operator):
    bl_idname = "acoustic.reset_specular_lobe_width"
    bl_label = "Reset Specular Lobe Width"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):

        mat = context.material
        mat.acoustic_specular_lobe_width = 0.001

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


@orientation_helper(axis_forward='Y', axis_up='Z')
class ExportMitsuba(bpy.types.Operator, ExportHelper):
    """Export as a misuka scene"""
    bl_idname = "export_scene.mitsuba"
    bl_label = "misuka Export"

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

    #misuka check box in export window
    acoustic_mode: bpy.props.BoolProperty(                  
        name="misuka: Acoustic Mode",
        description="Export misuka acoustic scene",
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
    self.layout.operator(ExportMitsuba.bl_idname, text="misuka (.xml)")

def menu_import_func(self, context):
    self.layout.operator(ImportMistuba.bl_idname, text="misuka (.xml)")


classes = (
    ImportMistuba,
    ExportMitsuba,
    ACOUSTIC_PT_material,
    ACOUSTIC_OT_reset_abs,
    ACOUSTIC_OT_reset_scat,
    ACOUSTIC_OT_reset_specular_lobe_width,
    ACOUSTIC_OT_interpolate_abs,
    ACOUSTIC_OT_interpolate_scat,
    ACOUSTIC_OT_load_from_api,
    ACOUSTIC_OT_apply_variant
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

    del bpy.types.Material.acoustic_specular_lobe_width

    del bpy.types.Material.acoustic_variant_enum

    bpy.types.TOPBAR_MT_file_export.remove(menu_export_func)
    bpy.types.TOPBAR_MT_file_import.remove(menu_import_func)

    del bpy.types.Material.show_acoustic_help
    del bpy.types.Material.show_acoustic_info
