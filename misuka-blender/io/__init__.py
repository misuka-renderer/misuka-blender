if "bpy" in locals():
    import importlib
    if "bl_utils" in locals():
        importlib.reload(bl_utils)
    if "acoustic_bands" in locals():
        importlib.reload(acoustic_bands)
    if "importer" in locals():
        importlib.reload(importer)
    if "exporter" in locals():
        importlib.reload(exporter)

import bpy

from bpy.props import (
        StringProperty,
        BoolProperty,
        BoolVectorProperty,
        EnumProperty,
        FloatProperty,
    )
from bpy_extras.io_utils import (
        ImportHelper,
        ExportHelper,
        orientation_helper,
        axis_conversion
    )

from . import bl_utils
from . import acoustic_bands
from . import importer
from . import exporter
from .acoustic_bands import (
        ABS_PROPS,
        ACOUSTIC_DEFAULT,
        INTERPOLATION_ITEMS,
        OCTAVE_INDICES,
        SCAT_PROPS,
        THIRD_OCTAVES,
        band_updates_suppressed,
        interpolate_bands,
        nearest_band_index,
        scene_resolution,
        write_bands,
    )

import urllib.parse
import urllib.request
import urllib.error
import json

# ---------- Acoustic Material UI ----------

# Width of the per-band "Keep" checkbox column relative to a value column.
# Wide enough for the header word, narrow enough that the tick still reads as
# belonging to the value beside it.
KEEP_COLUMN_SCALE = 0.4

# Vertical scale for stacked text rows. A label occupies a full widget row, so
# unscaled paragraphs are spaced like buttons rather than like prose.
TEXT_LINE_SCALE = 0.7

# Assumed properties editor width when there is no region to measure, which is
# the case in background renders and when drawing outside a real UI.
DEFAULT_PANEL_WIDTH = 320

# Rough width of one character, used only when the font cannot be measured.
FALLBACK_CHARACTER_WIDTH = 6.0

# Padding inside the enclosing box, so the last word does not touch the edge.
TEXT_PADDING = 16


def text_measurer(ui_scale):
    '''
    Return a function giving the pixel width of a string in the widget font.

    Blender's UI font is proportional, so estimating from a character count
    either wraps far short of the panel edge or overruns it. `blf` measures the
    real thing. It needs a font size, which moved out of `blf.size` in 4.0.
    '''
    try:
        import blf

        points = bpy.context.preferences.ui_styles[0].widget.points * ui_scale

        if bpy.app.version >= (4, 0, 0):
            blf.size(0, points)
        else:
            blf.size(0, points, 72)

        if blf.dimensions(0, "reference")[0] > 0:
            return lambda text: blf.dimensions(0, text)[0]

    except Exception:
        pass

    # Headless, or a Blender build without a usable font.
    return lambda text: len(text) * FALLBACK_CHARACTER_WIDTH * ui_scale


def wrap_text(text, max_width, measure):
    '''Greedily break `text` into lines no wider than `max_width` pixels.'''
    lines = []
    line = ""

    for word in text.split():
        candidate = f"{line} {word}" if line else word

        if line and measure(candidate) > max_width:
            lines.append(line)
            line = word
        else:
            line = candidate

    if line:
        lines.append(line)

    return lines


def draw_paragraphs(layout, context, *paragraphs):
    '''
    Draw text wrapped to the current panel width.

    `UILayout.label` has no wrapping of its own, so the text is broken up here
    against the region width. That also means the help text reflows when the
    properties editor is resized, instead of being cut off at a fixed width.
    '''
    region = getattr(context, "region", None)
    # Blender reports a UI scale of 0 when running headless.
    ui_scale = bpy.context.preferences.system.ui_scale or 1.0

    width = (getattr(region, "width", 0) or DEFAULT_PANEL_WIDTH) - TEXT_PADDING * ui_scale
    measure = text_measurer(ui_scale)

    # An aligned column drops the gap Blender leaves between separate widgets,
    # which is what makes unaligned labels read as double spaced.
    column = layout.column(align=True)
    column.scale_y = TEXT_LINE_SCALE

    for index, paragraph in enumerate(paragraphs):
        if index:
            column.separator()
        for line in wrap_text(paragraph, width, measure):
            column.label(text=line)


class ACOUSTIC_OT_load_from_api(bpy.types.Operator):
    bl_idname = "acoustic.load_from_api"
    bl_label = "Load Acoustic Data"

    @classmethod
    def poll(cls, context):
        return getattr(context, "material", None) is not None

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


def select_variant(mat):
    '''
    Resolve the variant enum to a variant dict, or None when there is nothing
    usable. "Auto Selection" prefers the most absorbent absorption variant,
    since that is the measurement people are usually after.
    '''
    variants = mat.get("_acoustic_variants_cache", [])

    if not variants:
        return None

    selection = getattr(mat, "acoustic_variant_enum", "NONE")

    if selection != "NONE":
        idx = int(selection)
        return variants[idx] if idx < len(variants) else None

    abs_variants = [v for v in variants if v.get("_type") == "absorption"]
    if abs_variants:
        return max(abs_variants, key=lambda v: v.get("calculated_absorption", 0))

    scat_variants = [v for v in variants if v.get("_type") == "scattering"]
    if scat_variants:
        # no ranking available -> fallback
        return scat_variants[0]

    return None


class ACOUSTIC_OT_apply_variant(bpy.types.Operator):
    bl_idname = "acoustic.apply_variant"
    bl_label = "Apply Variant"

    @classmethod
    def poll(cls, context):
        return getattr(context, "material", None) is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):

        layout = self.layout
        variant = select_variant(context.material)

        vtype = variant.get("_type") if variant else None

        if vtype == "absorption":
            text = "Overwrite absorption values?"
        elif vtype == "scattering":
            text = "Overwrite scattering values?"
        else:
            text = "Overwrite values?"

        layout.label(text=text, icon='ERROR')

    def execute(self, context):

        mat = context.material

        if not mat.get("_acoustic_variants_cache", []):
            self.report({'ERROR'}, "No variants loaded.")
            return {'CANCELLED'}

        variant = select_variant(mat)

        if variant is None:
            self.report({'ERROR'}, "No usable variants")
            return {'CANCELLED'}

        variant_type = variant.get("_type")

        if variant_type == "absorption":
            third_oct = variant.get("alpha_s_third_octave")
            oct_data = variant.get("alpha_s_octave")
            props = ABS_PROPS
            flag_prop = "acoustic_abs_band_set"

        elif variant_type == "scattering":
            third_oct = variant.get("scatter_third_octave")
            oct_data = variant.get("scatter_octave")
            props = SCAT_PROPS
            flag_prop = "acoustic_scat_band_set"

        else:
            self.report({'ERROR'}, "Unknown variant type")
            return {'CANCELLED'}

        # Third-octave data is kept at its own resolution rather than averaged
        # down to octaves. Values always land on the full third-octave table;
        # the scene's band resolution decides which of them get exported.
        measured = third_oct or oct_data

        if not measured:
            self.report({'ERROR'}, f"No {variant_type} data")
            return {'CANCELLED'}

        # Mark only the bands that were actually measured, so the panel keeps
        # showing which numbers came from the lab and which we filled in.
        anchors = {}
        unmatched = 0

        for key, value in measured.items():
            try:
                freq = int(key)
            except (TypeError, ValueError):
                unmatched += 1
                continue

            band = nearest_band_index(freq, THIRD_OCTAVES)
            if band is None:
                unmatched += 1
            else:
                anchors[THIRD_OCTAVES[band]] = value

        if not anchors:
            self.report({'ERROR'}, f"No {variant_type} data on known bands")
            return {'CANCELLED'}

        values = interpolate_bands(
            anchors, THIRD_OCTAVES, interpolation=mat.acoustic_interpolation
        )
        write_bands(mat, props, values)

        setattr(mat, flag_prop, [f in anchors for f in THIRD_OCTAVES])

        if third_oct and scene_resolution(context.scene) != 'THIRD_OCTAVE':
            self.report(
                {'WARNING'},
                "Variant has third-octave data. Set Band Resolution to Third "
                "Octave in Output properties to simulate it"
            )
        elif unmatched:
            self.report(
                {'WARNING'},
                f"Variant applied, {unmatched} value(s) outside the band table ignored"
            )
        else:
            self.report({'INFO'}, "Variant applied")

        return {'FINISHED'}


def make_band_update(flag_prop, index):
    '''
    Build the update callback that ticks a band's "set" checkbox when its value
    is edited, so typing a number is enough to mark it as an anchor.
    '''
    def update(self, context):
        if band_updates_suppressed():
            return
        flags = list(getattr(self, flag_prop))
        if not flags[index]:
            flags[index] = True
            setattr(self, flag_prop, flags)

    return update


def register_acoustic_properties():

    for index, freq in enumerate(THIRD_OCTAVES):

        setattr(bpy.types.Material, ABS_PROPS[index], FloatProperty(
            name=f"{freq} Hz",
            description=(
                "Absorption coefficient in this band. 0 reflects all energy, "
                "1 absorbs all of it. Measured Sabine coefficients can exceed 1, "
                "so values up to 2 are accepted"
            ),
            default=ACOUSTIC_DEFAULT,
            min=0, max=2, soft_max=1.0,
            update=make_band_update("acoustic_abs_band_set", index),
        ))

        setattr(bpy.types.Material, SCAT_PROPS[index], FloatProperty(
            name=f"{freq} Hz",
            description=(
                "Scattering coefficient in this band. 0 reflects purely "
                "specularly, 1 scatters all reflected energy diffusely"
            ),
            default=ACOUSTIC_DEFAULT,
            min=0, max=1,
            update=make_band_update("acoustic_scat_band_set", index),
        ))

    band_set_description = (
        "Bands you have set yourself. Interpolate Values treats these as "
        "anchors and overwrites the rest"
    )

    bpy.types.Material.acoustic_abs_band_set = BoolVectorProperty(
        name="Absorption Bands Set",
        description=band_set_description,
        size=len(THIRD_OCTAVES),
        default=(False,) * len(THIRD_OCTAVES),
    )

    bpy.types.Material.acoustic_scat_band_set = BoolVectorProperty(
        name="Scattering Bands Set",
        description=band_set_description,
        size=len(THIRD_OCTAVES),
        default=(False,) * len(THIRD_OCTAVES),
    )

    bpy.types.Material.acoustic_interpolation = EnumProperty(
        name="Interpolation",
        description="Frequency axis Interpolate Values works along",
        items=INTERPOLATION_ITEMS,
        default='LOG',
    )

    bpy.types.Material.acoustic_specular_lobe_width = FloatProperty(
        name="Specular Lobe Width",
        description=(
            "Angular width of the specular reflection lobe. Small values give a "
            "mirror-like reflection, larger ones spread it out"
        ),
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
        name="Manual Input Instructions",
        default=True
    )

    bpy.types.Material.show_acoustic_bands = BoolProperty(
        name="Coefficient Table",
        default=True
    )


def unregister_acoustic_properties():

    for name in ABS_PROPS + SCAT_PROPS:
        delattr(bpy.types.Material, name)

    for name in (
        "acoustic_abs_band_set",
        "acoustic_scat_band_set",
        "acoustic_interpolation",
        "acoustic_specular_lobe_width",
        "acoustic_variant_enum",
        "show_acoustic_help",
        "show_acoustic_info",
        "show_acoustic_bands",
    ):
        delattr(bpy.types.Material, name)


class ACOUSTIC_PT_material(bpy.types.Panel):

    bl_label = "Acoustic Material"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"

    @classmethod
    def poll(cls, context):
        return getattr(context, "material", None) is not None

    def draw_bands(self, col, mat, context):
        '''
        Draw both coefficient families side by side, one row per band.

        Two columns rather than two stacked tables: 27 bands twice over is a lot
        of scrolling, and absorption and scattering are usually read together.
        '''

        row = col.row()
        row.prop(
            mat, "show_acoustic_bands",
            icon="TRIA_DOWN" if mat.show_acoustic_bands else "TRIA_RIGHT",
            icon_only=True, emboss=False
        )
        row.label(text="Coefficients")

        if not mat.show_acoustic_bands:
            return

        third_octave = scene_resolution(context.scene) == 'THIRD_OCTAVE'

        box = col.box()
        columns = box.row()

        # One column per cell rather than one row per band: separate columns
        # stay aligned row for row on their own, and each gets its own header.
        # The checkbox columns are narrowed so "Keep" sits over the tick rather
        # than claiming an even share of the width.
        freq_column = columns.column(align=True)

        families = []
        for label, props, flag_prop, interpolate_op, reset_op in (
            ("Absorption", ABS_PROPS, "acoustic_abs_band_set",
             "acoustic.interpolate_abs", "acoustic.reset_abs"),
            ("Scattering", SCAT_PROPS, "acoustic_scat_band_set",
             "acoustic.interpolate_scat", "acoustic.reset_scat"),
        ):
            family = columns.row(align=True)

            keep_column = family.column(align=True)
            keep_column.scale_x = KEEP_COLUMN_SCALE

            families.append((
                keep_column, family.column(align=True),
                label, props, flag_prop, interpolate_op, reset_op,
            ))

        freq_column.label(text="")
        for keep_column, value_column, label, *_ in families:
            keep_column.label(text="Keep")
            value_column.label(text=label)

        for index, freq in enumerate(THIRD_OCTAVES):
            # Octave mode still shows the third-octave rows, greyed out, so the
            # values stay visible and changing resolution never loses them.
            enabled = third_octave or index in OCTAVE_INDICES

            row = freq_column.row()
            row.enabled = enabled
            row.label(text=f"{freq} Hz")

            for keep_column, value_column, _, props, flag_prop, _, _ in families:
                row = keep_column.row(align=True)
                row.enabled = enabled
                row.prop(mat, flag_prop, index=index, text="")

                row = value_column.row(align=True)
                row.enabled = enabled
                row.prop(mat, props[index], text="")

        freq_column.separator()
        for keep_column, value_column, _, _, _, interpolate_op, reset_op in families:
            keep_column.separator()
            value_column.separator()
            value_column.operator(interpolate_op, text="Interpolate")
            value_column.operator(reset_op, text=f"Reset to {ACOUSTIC_DEFAULT}")

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
        row.label(text="Manual Input")

        if mat.show_acoustic_info:
            # Only what is not already covered by a tooltip or visible in the
            # table itself. The band values, the Keep ticks and the two
            # dropdowns all carry their own descriptions.
            draw_paragraphs(
                col.box(), context,
                "Values are exported exactly as shown. Greyed bands are not "
                "exported; Band Resolution in Output properties picks which.",
                "Tick Keep to mark a band as yours. Editing a value ticks it "
                "for you.",
                "Interpolate overwrites every unticked band from the ticked "
                "ones, holding the nearest value beyond the outermost.",
            )

        col.separator()

        col.prop(mat, "acoustic_interpolation")

        self.draw_bands(col, mat, context)

        col.separator()

        col.label(text="Specular Lobe Width")
        col.prop(mat, "acoustic_specular_lobe_width")

        row = col.row(align=True)
        row.operator(
            "acoustic.reset_specular_lobe_width",
            text="Reset to 0.001"
        )


class ACOUSTIC_OT_interpolate_base(bpy.types.Operator):
    '''
    Fill every unticked band of one family from the ticked ones.

    The anchors come from the material's own "band set" checkboxes rather than
    from a comparison against the default value, so a band can be anchored at
    any value, the default included.
    '''

    props = ()
    flag_prop = ""

    @classmethod
    def poll(cls, context):
        return getattr(context, "material", None) is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):

        mat = context.material
        flags = getattr(mat, self.flag_prop)

        anchors = {
            freq: getattr(mat, self.props[index])
            for index, freq in enumerate(THIRD_OCTAVES)
            if flags[index]
        }

        if not anchors:
            self.report({'WARNING'}, "Tick at least one band first")
            return {'CANCELLED'}

        # Fill the whole table, including bands the current resolution greys
        # out, so the curve stays coherent if the resolution changes later.
        values = interpolate_bands(
            anchors, THIRD_OCTAVES, interpolation=mat.acoustic_interpolation
        )
        write_bands(mat, self.props, values)

        return {'FINISHED'}


class ACOUSTIC_OT_interpolate_abs(ACOUSTIC_OT_interpolate_base):
    bl_idname = "acoustic.interpolate_abs"
    bl_label = "Change Absorption Values"

    props = ABS_PROPS
    flag_prop = "acoustic_abs_band_set"


class ACOUSTIC_OT_interpolate_scat(ACOUSTIC_OT_interpolate_base):
    bl_idname = "acoustic.interpolate_scat"
    bl_label = "Change Scattering Values"

    props = SCAT_PROPS
    flag_prop = "acoustic_scat_band_set"


class ACOUSTIC_OT_reset_base(bpy.types.Operator):
    '''Return every band of one family to the default and untick them all.'''

    props = ()
    flag_prop = ""

    @classmethod
    def poll(cls, context):
        return getattr(context, "material", None) is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):

        mat = context.material

        write_bands(mat, self.props, [ACOUSTIC_DEFAULT] * len(self.props))
        setattr(mat, self.flag_prop, [False] * len(self.props))

        return {'FINISHED'}


class ACOUSTIC_OT_reset_abs(ACOUSTIC_OT_reset_base):
    bl_idname = "acoustic.reset_abs"
    bl_label = "Reset Absorption"

    props = ABS_PROPS
    flag_prop = "acoustic_abs_band_set"


class ACOUSTIC_OT_reset_scat(ACOUSTIC_OT_reset_base):
    bl_idname = "acoustic.reset_scat"
    bl_label = "Reset Scattering"

    props = SCAT_PROPS
    flag_prop = "acoustic_scat_band_set"


class ACOUSTIC_OT_reset_specular_lobe_width(bpy.types.Operator):
    bl_idname = "acoustic.reset_specular_lobe_width"
    bl_label = "Reset Specular Lobe Width"

    @classmethod
    def poll(cls, context):
        return getattr(context, "material", None) is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):

        mat = context.material
        mat.acoustic_specular_lobe_width = 0.001

        return {'FINISHED'}


@orientation_helper(axis_forward='-Z', axis_up='Y')
class ImportMistuba(bpy.types.Operator, ImportHelper):
    """Import a misuka scene"""
    bl_idname = "import_scene.mitsuba"
    bl_label = "misuka Import"

    filename_ext = ".xml"
    filter_glob: StringProperty(default="*.xml", options={'HIDDEN'})

    override_scene: BoolProperty(
        name = 'Override Current Scene',
        description = 'Override the current scene with the imported misuka scene. '
                      'Otherwise, creates a new scene for misuka objects.',
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
            # Create a new scene for misuka objects
            scene = bl_utils.init_empty_scene(context, name='misuka')
        collection = scene.collection

        try:
            importer.load_mitsuba_scene(context, scene, collection, self.filepath, axis_mat)
        except (RuntimeError, NotImplementedError) as e:
            print(e)
            self.report({'ERROR'}, "Failed to load misuka scene. See error log.")
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

    export_ids: BoolProperty(
            name = "Export IDs",
            description = "Add an 'id' field for each object (shape, emitter, camera...)",
            default = False
    )

    ignore_background: BoolProperty(
            name = "Ignore Default Background",
            description = "Ignore blender's default constant gray background when exporting to misuka.",
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
        # Acoustic film settings live on the scene, beside the image resolution.
        mts_settings = context.scene.mitsuba
        self.converter.export_ctx.acoustic_band_resolution = mts_settings.acoustic_band_resolution
        self.converter.export_ctx.acoustic_time_bins = mts_settings.acoustic_time_bins

        self.converter.use_selection = self.use_selection

        # Set path to scene .xml file
        self.converter.set_path(self.filepath)

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
    ACOUSTIC_OT_apply_variant,
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

    unregister_acoustic_properties()

    bpy.types.TOPBAR_MT_file_export.remove(menu_export_func)
    bpy.types.TOPBAR_MT_file_import.remove(menu_import_func)
