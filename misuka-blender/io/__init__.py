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
from ..docs import draw_help_button
from .acoustic_bands import (
        ABS_PROPS,
        ACOUSTIC_DEFAULT,
        OCTAVE_INDICES,
        SCAT_PROPS,
        THIRD_OCTAVES,
        band_updates_suppressed,
        interpolate_bands,
        nearest_band_index,
        scene_interpolation,
        scene_resolution,
        write_bands,
    )

from collections import namedtuple

import urllib.parse
import urllib.request
import urllib.error
import json

# ---------- Acoustic Material UI ----------

# The variant dropdown's "nothing picked" identifier. Every other identifier is
# a variant's index in the cache.
NO_VARIANT = "NONE"

Quantity = namedtuple("Quantity", (
    "label", "props", "keep_prop", "variant_type",
    "third_octave_key", "octave_key", "interpolate_op", "reset_op",
))

# Absorption and scattering run in parallel everywhere: each has its own band
# properties, its own Keep flags, its own operators and its own keys in an
# AcousticIndex variant. Saying that once is what stops the two drifting apart,
# which they already did once in apply_variant.
QUANTITIES = (
    Quantity("Absorption", ABS_PROPS, "acoustic_abs_keep", "absorption",
             "alpha_s_third_octave", "alpha_s_octave",
             "acoustic.interpolate_abs", "acoustic.reset_abs"),
    Quantity("Scattering", SCAT_PROPS, "acoustic_scat_keep", "scattering",
             "scatter_third_octave", "scatter_octave",
             "acoustic.interpolate_scat", "acoustic.reset_scat"),
)


class AcousticOperator:
    """Shared poll for the operators that act on the active material."""

    @classmethod
    def poll(cls, context):
        return getattr(context, "material", None) is not None


# Share of the coefficient table the frequency column takes, and the share of
# each quantity's half that its Keep checkbox takes. Blender splits a row by
# fraction, so these are shares of the panel, not pixel widths.
FREQ_COLUMN_FRACTION = 0.20
KEEP_COLUMN_FRACTION = 0.20

# Vertical scale for stacked text rows. A label occupies a full widget row, so
# unscaled paragraphs are spaced like buttons rather than like prose.
TEXT_LINE_SCALE = 0.7

# Assumed properties editor width when there is no region to measure, which is
# the case in background renders and when drawing outside a real UI. In UI
# units, so it is scaled like a real region width before use.
DEFAULT_PANEL_WIDTH = 320

# Rough width of one character, used only when the font cannot be measured.
FALLBACK_CHARACTER_WIDTH = 6.0

# What the region's width is not available to the text: panel margins, box
# padding, the label's inset and the scrollbar. Blender gives no way to ask a
# layout how wide it ended up, so this has to be assumed. Erring large costs an
# early line break, erring small makes Blender truncate with an ellipsis, so it
# is deliberately generous.
TEXT_INSET = 58


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

    # A region width is in device pixels, and blf measures in device pixels
    # too, so the assumed width has to be scaled to match. Left unscaled it
    # wraps at half width on a HiDPI display.
    region_width = (getattr(region, "width", 0)
                    or DEFAULT_PANEL_WIDTH * ui_scale)
    # Never go so narrow that single words start overflowing anyway.
    width = max(region_width - TEXT_INSET * ui_scale, 80 * ui_scale)
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


ACOUSTICINDEX_API = "https://acousticindex.com/api/v1"


class AcousticIndexError(Exception):
    '''A lookup failed in a way worth telling the user about.'''


def request_json(url, api_key):
    '''GET `url` with the key and parse the response.'''
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {api_key}"})

    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode())


def fetch_material(api_key, query):
    '''
    Look a material up on AcousticIndex by id, then by name.

    The id is tried first and verbatim: only AcousticIndex can say whether a
    string is one of its ids, and guessing from the shape of the name got it
    wrong both ways, treating a product name that happened to be long and
    hyphenated as an id.

    Anything the id endpoint rejects as unknown falls through to the search.
    An authentication failure does not, since the search would fail the same
    way and reporting a missing material would be misleading.
    '''
    try:
        return request_json(f"{ACOUSTICINDEX_API}/materials/{urllib.parse.quote(query)}",
                            api_key)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise AcousticIndexError(f"Not authorised: {error.code}") from error
        if error.code >= 500:
            raise AcousticIndexError(f"API request failed: {error.code}") from error
        # 404 and friends: not an id, so try it as a name.

    search_url = (f"{ACOUSTICINDEX_API}/materials/search"
                  f"?q={urllib.parse.quote(query)}&limit=1")

    try:
        results = request_json(search_url, api_key)
    except urllib.error.HTTPError as error:
        raise AcousticIndexError(f"Search failed: {error.code}") from error

    items = results.get("items", [])

    if not items:
        raise AcousticIndexError("No Acoustic Index material found.")

    try:
        return request_json(f"{ACOUSTICINDEX_API}/materials/{items[0]['id']}",
                            api_key)
    except urllib.error.HTTPError as error:
        raise AcousticIndexError(f"API request failed: {error.code}") from error


class ACOUSTIC_OT_load_from_api(AcousticOperator, bpy.types.Operator):
    bl_idname = "acoustic.load_from_api"
    bl_label = "Load Acoustic Data"
    bl_description = ("Look the material's name up on Acoustic Index as a "
                      "product id, then as a name, and fetch the match with "
                      "all its measured variants")

    def execute(self, context):

        mat = context.material

        # Set here and cleared only once a material is actually loaded, so
        # every early return below leaves it set without having to remember.
        # A failed lookup keeps the previous data, which is still applicable.
        mat["_acoustic_lookup_failed"] = True

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

        try:
            data = fetch_material(api_key, search_query)
        # OSError covers a dead network, ValueError a response that is not JSON.
        except (AcousticIndexError, OSError, ValueError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

        measurements = data.get("measurements", {})

        abs_variants = measurements.get("absorption_iso_354", [])
        scat_variants = measurements.get("scatter_iso_17497_1", [])

        for v in abs_variants:
            v["_type"] = "absorption"

        for v in scat_variants:
            v["_type"] = "scattering"

        variants = abs_variants + scat_variants

        if not variants:
            self.report({'WARNING'}, "No measurement data available.")
            return {'CANCELLED'}

        mat["_acoustic_variants_cache"] = variants

        # Clear the selection rather than land on a variant nobody chose. The
        # dropdown also holds an index into the cache we just replaced, so a
        # stale one would point at a variant this entry does not have.
        mat.acoustic_variant_enum = NO_VARIANT

        mat["_acoustic_loaded_label"] = data.get("label", "")
        mat["_acoustic_loaded_manufacturer"] = data.get("manufacturer", "")
        # What was actually looked up, so the panel can tell the user when the
        # material has been renamed since and the entry below is for the old name.
        mat["_acoustic_loaded_query"] = search_query
        mat["_acoustic_lookup_failed"] = False

        self.report({'INFO'}, f"{len(variants)} variants loaded")
        return {'FINISHED'}


def select_variant(mat):
    '''
    Resolve the variant enum to a variant dict, or None when there is nothing
    usable. The enum holds the variant's index in the cache, so the only
    variant that is ever applied is the one named in the dropdown.
    '''
    variants = mat.get("_acoustic_variants_cache", [])

    if not variants:
        return None

    selection = getattr(mat, "acoustic_variant_enum", NO_VARIANT)

    if not selection.isdigit():
        return None

    idx = int(selection)
    return variants[idx] if idx < len(variants) else None


class ACOUSTIC_OT_apply_variant(AcousticOperator, bpy.types.Operator):
    bl_idname = "acoustic.apply_variant"
    bl_label = "Apply Variant"
    bl_description = ("Write the selected variant's measured absorption and scattering coefficients into "
                      "the table, ticking the bands it covers")

    def invoke(self, context, event):
        # Nothing picked is a normal state now, so say so here rather than ask
        # for a confirmation and then refuse.
        if select_variant(context.material) is None:
            return self.execute(context)

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
            self.report({'ERROR'}, "Select a variant first.")
            return {'CANCELLED'}

        quantity = next((q for q in QUANTITIES
                         if q.variant_type == variant.get("_type")), None)

        if quantity is None:
            self.report({'ERROR'}, "Unknown variant type")
            return {'CANCELLED'}

        third_oct = variant.get(quantity.third_octave_key)
        oct_data = variant.get(quantity.octave_key)

        # Third-octave data is kept at its own resolution rather than averaged
        # down to octaves. Values always land on the full third-octave table;
        # the scene's band resolution decides which of them get exported.
        measured = third_oct or oct_data

        if not measured:
            self.report({'ERROR'}, f"No {quantity.variant_type} data")
            return {'CANCELLED'}

        # Keep only the bands that were actually measured, so the panel keeps
        # showing which numbers came from the lab and which we filled in.
        anchors = {}
        unmatched = 0

        for key, value in measured.items():
            try:
                # float, not int: 31.5 Hz is a preferred centre frequency
                freq = float(key)
            except (TypeError, ValueError):
                unmatched += 1
                continue

            band = nearest_band_index(freq, THIRD_OCTAVES)
            if band is None:
                unmatched += 1
            else:
                anchors[THIRD_OCTAVES[band]] = value

        if not anchors:
            self.report({'ERROR'}, f"No {quantity.variant_type} data on known bands")
            return {'CANCELLED'}

        values = interpolate_bands(
            anchors, THIRD_OCTAVES, interpolation=scene_interpolation(context.scene)
        )
        write_bands(mat, quantity.props, values)

        setattr(mat, quantity.keep_prop,
                [f in anchors for f in THIRD_OCTAVES])

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


def make_band_update(keep_prop, index):
    '''
    Build the update callback that ticks a band's Keep box when its value is
    edited, so typing a number is enough to keep it.
    '''
    def update(self, context):
        if band_updates_suppressed():
            return
        flags = list(getattr(self, keep_prop))
        if not flags[index]:
            flags[index] = True
            setattr(self, keep_prop, flags)

    return update


def register_acoustic_properties():

    for index, freq in enumerate(THIRD_OCTAVES):

        setattr(bpy.types.Material, ABS_PROPS[index], FloatProperty(
            name=f"{freq} Hz",
            description=(
                f"Fraction of incident sound energy absorbed at {freq} Hz. "
                "0 reflects everything, 1 absorbs everything. Measured Sabine "
                "coefficients can exceed 1, so up to 2 is accepted"
            ),
            default=ACOUSTIC_DEFAULT,
            min=0, max=2, soft_max=1.0,
            update=make_band_update("acoustic_abs_keep", index),
        ))

        setattr(bpy.types.Material, SCAT_PROPS[index], FloatProperty(
            name=f"{freq} Hz",
            description=(
                f"Fraction of reflected sound energy scattered at {freq} Hz. "
                "0 reflects like a mirror, 1 scatters in all directions"
            ),
            default=ACOUSTIC_DEFAULT,
            min=0, max=1,
            update=make_band_update("acoustic_scat_keep", index),
        ))

    keep_description = (
        "Bands whose value you set yourself, or that a database variant "
        "measured. Interpolate keeps these and overwrites the rest"
    )

    bpy.types.Material.acoustic_abs_keep = BoolVectorProperty(
        name="Absorption Bands Kept",
        description=keep_description,
        size=len(THIRD_OCTAVES),
        default=(False,) * len(THIRD_OCTAVES),
    )

    bpy.types.Material.acoustic_scat_keep = BoolVectorProperty(
        name="Scattering Bands Kept",
        description=keep_description,
        size=len(THIRD_OCTAVES),
        default=(False,) * len(THIRD_OCTAVES),
    )

    bpy.types.Material.acoustic_specular_lobe_width = FloatProperty(
        name="Specular Lobe Width",
        description=(
            "Angular width of the specular reflection lobe. Small "
            "values reflect like a mirror, larger ones spread the reflection out. "
            "See the misuka documentation for more details."
        ),
        default=0.001,
        min=0.001,
        max=1.0,
        precision=3
    )

    def get_variant_items(self, context):

        mat = getattr(context, "material", None)
        variants = mat.get("_acoustic_variants_cache", []) if mat else []

        # The list leads with a "nothing picked" entry, so a fresh lookup can
        # land there and the choice of variant stays the user's. It is not a
        # variant, and Apply Variant refuses to run on it.
        if not variants:
            return [(NO_VARIANT, "No Variants Loaded", "")]

        items = [(NO_VARIANT, "Select a Variant", "")]

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



def unregister_acoustic_properties():

    for name in ABS_PROPS + SCAT_PROPS:
        delattr(bpy.types.Material, name)

    for name in (
        "acoustic_abs_keep",
        "acoustic_scat_keep",
        "acoustic_specular_lobe_width",
        "acoustic_variant_enum",
    ):
        delattr(bpy.types.Material, name)


class AcousticPanel:
    '''Shared setup for the acoustic material panel and its subpanels.'''

    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"
    COMPAT_ENGINES = {'MITSUBA'}

    @classmethod
    def poll(cls, context):
        # An acoustic export needs the misuka engine, so its settings belong
        # there and nowhere else.
        if context.engine not in cls.COMPAT_ENGINES:
            return False
        return getattr(context, "material", None) is not None


class ACOUSTIC_PT_material(AcousticPanel, bpy.types.Panel):

    bl_idname = "ACOUSTIC_PT_material"
    bl_label = "Acoustic Material"
    # Under the material selector, above the Surface node tree, since the
    # acoustic coefficients are what this add-on is for.
    bl_order = 1

    def draw(self, context):
        # Everything lives in the subpanels below, which is what gives them
        # their own fold state, drag handles and nesting for free.
        pass


class ACOUSTIC_PT_database(AcousticPanel, bpy.types.Panel):

    bl_idname = "ACOUSTIC_PT_database"
    bl_parent_id = "ACOUSTIC_PT_material"
    bl_label = "Acoustic Index Database"

    def draw_header(self, context):
        draw_help_button(self.layout, "guide/acousticindex.html")

    def draw(self, context):

        mat = context.material
        col = self.layout.column()

        row = col.row()
        row.scale_y = 1.2
        row.operator(
            "acoustic.load_from_api",
            text="Load from Database",
            icon='IMPORT'
        )

        label = mat.get("_acoustic_loaded_label")
        manufacturer = mat.get("_acoustic_loaded_manufacturer")
        query = mat.get("_acoustic_loaded_query")

        if label:
            box = col.box()

            row = box.row()

            # The entry stays valid for the name it was looked up under, so
            # say which name that was rather than let a checkmark imply it
            # matches the material's current one. A .blend saved before the
            # query was recorded has neither key and reads as a plain match.
            if mat.get("_acoustic_lookup_failed"):
                row.label(text="Last lookup failed", icon='ERROR')
            elif query and query != mat.name.strip():
                row.label(text=f'Loaded for "{query}"', icon='INFO')
            else:
                row.label(text="Matched Database Entry", icon='CHECKMARK')

            # Product names and manufacturers are arbitrary length and would
            # otherwise be clipped at the panel edge.
            draw_paragraphs(box, context, *filter(None, (label, manufacturer)))

        col.separator()
        col.label(text="Variant Selection")
        col.prop(mat, "acoustic_variant_enum", text="")

        col.operator_context = 'INVOKE_DEFAULT'

        row = col.row()
        row.operator(
            "acoustic.apply_variant",
            text="Apply Variant",
            icon='CHECKMARK'
        )


class ACOUSTIC_PT_coefficients(AcousticPanel, bpy.types.Panel):

    bl_idname = "ACOUSTIC_PT_coefficients"
    bl_parent_id = "ACOUSTIC_PT_material"
    bl_label = "Coefficients"

    def draw_header(self, context):
        draw_help_button(self.layout, "guide/acoustic-materials.html")

    def draw(self, context):
        '''
        Draw both coefficient quantities side by side, one row per band.

        Two columns rather than two stacked tables: 30 bands twice over is a lot
        of scrolling, and absorption and scattering are usually read together.
        '''
        mat = context.material
        third_octave = scene_resolution(context.scene) == 'THIRD_OCTAVE'

        # One column per cell rather than one row per band: separate columns
        # stay aligned row for row on their own, each gets its own header, and
        # a value can be dragged down an aligned column to set several bands in
        # one go.
        #
        # split() rather than scale_x: scale_x multiplies a column's natural
        # width, which comes from its content, so the frequency column would
        # never grow with the panel. A split factor is a share of the row.
        table = self.layout.row()
        outer = table.split(factor=FREQ_COLUMN_FRACTION)

        freq_column = outer.column(align=True)
        # The two quantities divide up what the frequency column leaves.
        pair = outer.split(factor=0.5)

        quantity_columns = []
        for quantity in QUANTITIES:
            family = pair.split(factor=KEEP_COLUMN_FRACTION)

            keep_column = family.column(align=True)
            value_column = family.column(align=True)

            quantity_columns.append((quantity, keep_column, value_column))

        freq_column.label(text="")
        for quantity, keep_column, value_column in quantity_columns:
            # Left aligned, the default: centering sizes each widget from its
            # own content, putting a label and a checkbox on different axes.
            keep_column.label(text="Keep")
            value_column.label(text=quantity.label)

        for index, freq in enumerate(THIRD_OCTAVES):
            # Octave mode still shows the third-octave rows, greyed out, so the
            # values stay visible and changing resolution never loses them.
            enabled = third_octave or index in OCTAVE_INDICES

            row = freq_column.row()
            row.enabled = enabled
            row.label(text=f"{freq} Hz")

            for quantity, keep_column, value_column in quantity_columns:
                row = keep_column.row(align=True)
                row.enabled = enabled
                row.prop(mat, quantity.keep_prop, index=index, text="")

                row = value_column.row(align=True)
                row.enabled = enabled
                row.prop(mat, quantity.props[index], text="")

        freq_column.separator()
        for quantity, keep_column, value_column in quantity_columns:
            keep_column.separator()
            value_column.separator()
            value_column.operator(quantity.interpolate_op, text="Interpolate")
            value_column.operator(quantity.reset_op,
                                  text=f"Reset to {ACOUSTIC_DEFAULT}")


class ACOUSTIC_PT_specular(AcousticPanel, bpy.types.Panel):

    bl_idname = "ACOUSTIC_PT_specular"
    bl_parent_id = "ACOUSTIC_PT_material"
    bl_label = "Specular Reflection"

    def draw_header(self, context):
        draw_help_button(
            self.layout,
            "guide/acoustic-materials.html#specular-reflection")

    def draw(self, context):
        col = self.layout.column()
        col.prop(context.material, "acoustic_specular_lobe_width")

        row = col.row(align=True)
        row.operator(
            "acoustic.reset_specular_lobe_width",
            text="Reset to 0.001"
        )


class ACOUSTIC_OT_interpolate_base(AcousticOperator, bpy.types.Operator):
    '''
    Fill every unkept band of one quantity from the kept ones.

    The anchors come from the material's own Keep boxes rather than from a
    comparison against the default value, so a band can be kept at any value,
    the default included.
    '''

    quantity = None

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):

        mat = context.material
        flags = getattr(mat, self.quantity.keep_prop)

        anchors = {
            freq: getattr(mat, self.quantity.props[index])
            for index, freq in enumerate(THIRD_OCTAVES)
            if flags[index]
        }

        if not anchors:
            self.report({'WARNING'}, "Tick at least one band first")
            return {'CANCELLED'}

        # Fill the whole table, including bands the current resolution greys
        # out, so the curve stays coherent if the resolution changes later.
        values = interpolate_bands(
            anchors, THIRD_OCTAVES, interpolation=scene_interpolation(context.scene)
        )
        write_bands(mat, self.quantity.props, values)

        return {'FINISHED'}


class ACOUSTIC_OT_interpolate_abs(ACOUSTIC_OT_interpolate_base):
    bl_idname = "acoustic.interpolate_abs"
    bl_label = "Change Absorption Values"
    bl_description = ("Overwrite every absorption band that is not ticked, by "
                      "interpolating between the ticked ones. Select linear or logarithmic interpolation in Output properties")

    quantity = QUANTITIES[0]


class ACOUSTIC_OT_interpolate_scat(ACOUSTIC_OT_interpolate_base):
    bl_idname = "acoustic.interpolate_scat"
    bl_label = "Change Scattering Values"
    bl_description = ("Overwrite every scattering band that is not ticked, by "
                      "interpolating between the ticked ones. Select linear or logarithmic interpolation in Output properties")

    quantity = QUANTITIES[1]


class ACOUSTIC_OT_reset_base(AcousticOperator, bpy.types.Operator):
    '''Return every band of one quantity to the default and untick them all.'''

    quantity = None

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):

        mat = context.material

        write_bands(mat, self.quantity.props, [ACOUSTIC_DEFAULT] * len(self.quantity.props))
        setattr(mat, self.quantity.keep_prop, [False] * len(self.quantity.props))

        return {'FINISHED'}


class ACOUSTIC_OT_reset_abs(ACOUSTIC_OT_reset_base):
    bl_idname = "acoustic.reset_abs"
    bl_label = "Reset Absorption"
    bl_description = (f"Set every absorption band back to {ACOUSTIC_DEFAULT} "
                      "and untick them all")

    quantity = QUANTITIES[0]


class ACOUSTIC_OT_reset_scat(ACOUSTIC_OT_reset_base):
    bl_idname = "acoustic.reset_scat"
    bl_label = "Reset Scattering"
    bl_description = (f"Set every scattering band back to {ACOUSTIC_DEFAULT} "
                      "and untick them all")

    quantity = QUANTITIES[1]


class ACOUSTIC_OT_reset_specular_lobe_width(AcousticOperator, bpy.types.Operator):
    bl_idname = "acoustic.reset_specular_lobe_width"
    bl_label = "Reset Specular Lobe Width"
    bl_description = "Set the specular lobe width back to its default"

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

    # The two modes swap out most of the scene, not just one setting, so this
    # is a choice between two kinds of export rather than a modifier on one.
    export_mode: EnumProperty(
        name="Export Mode",
        description="What kind of scene to write",
        items=(
            ('ACOUSTIC', "Acoustic",
             "Acoustic scene: acoustic_path integrator, microphone sensor, "
             "tape film and acousticbsdf materials"),
            ('VISUAL', "Visual",
             "Visual scene for rendering an image, with the integrator, sensor "
             "and materials the render engine implies"),
        ),
        default='ACOUSTIC',
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
        self.converter.export_ctx.acoustic_mode = self.export_mode == 'ACOUSTIC'
        mts_settings = context.scene.mitsuba
        self.converter.export_ctx.acoustic_band_resolution = mts_settings.acoustic_band_resolution
        self.converter.export_ctx.acoustic_time_bins = acoustic_bands.time_bins(mts_settings)
        self.converter.export_ctx.acoustic_max_time = mts_settings.acoustic_max_time
        self.converter.export_ctx.acoustic_sample_count = mts_settings.acoustic_sample_count

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
    ACOUSTIC_PT_database,
    ACOUSTIC_PT_coefficients,
    ACOUSTIC_PT_specular,
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
