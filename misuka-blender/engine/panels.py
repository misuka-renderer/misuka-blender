'''
Properties editor panels for the misuka engine.

Blender's light, material and world panels are tagged EEVEE-only or
Cycles-only, so `engine.get_panels()` never sweeps them up and they do not draw
under misuka. Rather than tagging Blender's classes with MITSUBA, we draw our
own, the way Cycles does. That keeps the panels to what the exporter actually
reads and survives Blender reshaping its own UI, which it did to the light panel
between 4.2 and 5.2.
'''

import bpy
from bpy.props import FloatProperty

from ..io import draw_paragraphs


class MitsubaPanel:
    '''Shared setup for the misuka Properties panels.'''

    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    COMPAT_ENGINES = {'MITSUBA'}

    @classmethod
    def poll(cls, context):
        return context.engine in cls.COMPAT_ENGINES


def find_node_input(node, name):
    for socket in node.inputs:
        if socket.identifier == name:
            return socket
    return None


def node_view(layout, id_data, input_name):
    '''
    Draw one input of a shader output node, the way the Properties editor does.

    Blender's own `panel_node_draw` asks for the EEVEE output node and Cycles
    ships a copy asking for the CYCLES one, so neither matches what misuka
    exports. 'ALL' picks the target-agnostic output node, which is what
    `io.exporter.materials` reads.
    '''
    if not id_data.use_nodes:
        return False

    ntree = id_data.node_tree
    node = ntree.get_output_node('ALL')
    if node is None:
        layout.label(text="No output node")
        return True

    socket = find_node_input(node, input_name)
    if socket is None:
        layout.label(text="Incompatible output node")
        return True

    layout.template_node_view(ntree, node, socket)
    return True


def export_notes(light):
    '''
    What each export mode does with this light.

    Only a point light becomes an acoustic source, a sphere carrying an area
    emitter, so the other types say plainly that an Acoustic export skips them.
    '''
    if light.type == 'POINT':
        return [
            "Color is only used in a Visual export. An Acoustic export builds "
            "a uniform emission spectrum from Power alone.",
            "The radius is only used in an Acoustic export, to build a "
            "spherical emitter. A Visual export ignores it and writes an "
            "emitter with no size.",
            "For an emitter that behaves the same in both modes, give a "
            "sphere mesh an Emission material instead.",
        ]

    notes = [
        "An Acoustic export only supports point lights, so this light is "
        "skipped. A Visual export uses it normally.",
    ]

    if light.type == 'SPOT':
        notes.append(
            "The radius does nothing here. A Visual export writes a spot "
            "emitter with no size."
        )

    notes.append(
        "For an emitter an Acoustic export can use, switch this light to "
        "Point, or give a sphere mesh an Emission material."
    )
    return notes


class MITSUBA_LIGHT_PT_light(MitsubaPanel, bpy.types.Panel):
    '''
    Replaces DATA_PT_EEVEE_light, and DATA_PT_light along with it, since that
    one only draws the type row this panel already has.
    '''

    bl_idname = "MITSUBA_LIGHT_PT_light"
    bl_label = "Light / Emitter"
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        return context.light and super().poll(context)

    def draw(self, context):
        layout = self.layout
        light = context.light

        layout.row().prop(light, "type", expand=True)
        layout.use_property_split = True

        col = layout.column()
        col.prop(light, "color")
        col.prop(light, "energy")

        col.separator()

        if light.type in {'POINT', 'SPOT'}:
            col.prop(light, "mitsuba_emitter_radius")
        elif light.type == 'AREA':
            col.prop(light, "shape")

            sub = col.column(align=True)
            if light.shape in {'SQUARE', 'DISK'}:
                sub.prop(light, "size")
            elif light.shape in {'RECTANGLE', 'ELLIPSE'}:
                sub.prop(light, "size", text="Size X")
                sub.prop(light, "size_y", text="Y")

        # A SUN light exports as `directional`, which has no angular size, so
        # there is nothing beyond color and energy to show.

        # Which export mode is running is a setting on the export operator, so
        # no panel can read it. Name both cases instead. label() does not wrap,
        # so the notes go through the same helper as the acoustic material
        # help.
        col.separator()
        draw_paragraphs(col, context, *export_notes(light))


class MITSUBA_LIGHT_PT_beam_shape(MitsubaPanel, bpy.types.Panel):
    '''
    Replaces DATA_PT_spot, which parents to DATA_PT_EEVEE_light and so stays
    hidden under misuka however its own COMPAT_ENGINES is tagged.
    '''

    bl_idname = "MITSUBA_LIGHT_PT_beam_shape"
    bl_parent_id = "MITSUBA_LIGHT_PT_light"
    bl_label = "Beam Shape"
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        light = context.light
        return light and light.type == 'SPOT' and super().poll(context)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        light = context.light

        col = layout.column()
        col.prop(light, "spot_size", text="Size")
        col.prop(light, "spot_blend", text="Blend", slider=True)
        col.prop(light, "show_cone")


class MITSUBA_MATERIAL_PT_context(MitsubaPanel, bpy.types.Panel):
    '''
    The material slot list. Without it there is no New button, so an object
    cannot be given its first material, and ACOUSTIC_PT_material never polls.
    '''

    bl_idname = "MITSUBA_MATERIAL_PT_context"
    bl_label = ""
    bl_context = "material"
    bl_options = {'HIDE_HEADER'}
    # The material selector, so it sits above every other material panel.
    # io.register() runs before engine.register(), so without an explicit
    # order the acoustic panels would come first on a tie at 0.
    bl_order = 0

    @classmethod
    def poll(cls, context):
        ob = context.object
        mat = context.material

        if (ob and ob.type == 'GPENCIL') or (mat and mat.grease_pencil):
            return False

        return (ob or mat) and super().poll(context)

    def draw(self, context):
        layout = self.layout

        mat = context.material
        ob = context.object
        slot = context.material_slot
        space = context.space_data

        if ob:
            is_sortable = len(ob.material_slots) > 1
            rows = 5 if is_sortable else 3

            row = layout.row()
            row.template_list(
                "MATERIAL_UL_matslots", "",
                ob, "material_slots",
                ob, "active_material_index",
                rows=rows
            )

            col = row.column(align=True)
            col.operator("object.material_slot_add", icon='ADD', text="")
            col.operator("object.material_slot_remove", icon='REMOVE', text="")

            col.separator()
            col.menu("MATERIAL_MT_context_menu", icon='DOWNARROW_HLT', text="")

            if is_sortable:
                col.separator()
                col.operator(
                    "object.material_slot_move", icon='TRIA_UP', text=""
                ).direction = 'UP'
                col.operator(
                    "object.material_slot_move", icon='TRIA_DOWN', text=""
                ).direction = 'DOWN'

        row = layout.row()

        if ob:
            row.template_ID(ob, "active_material", new="material.new")

            if slot:
                icon_link = 'MESH_DATA' if slot.link == 'DATA' else 'OBJECT_DATA'
                row.prop(slot, "link", text="", icon=icon_link, icon_only=True)

            if ob.mode == 'EDIT':
                row = layout.row(align=True)
                row.operator("object.material_slot_assign", text="Assign")
                row.operator("object.material_slot_select", text="Select")
                row.operator("object.material_slot_deselect", text="Deselect")

        elif mat:
            row.template_ID(space, "pin_id")


class MITSUBA_MATERIAL_PT_surface(MitsubaPanel, bpy.types.Panel):
    '''Replaces EEVEE_MATERIAL_PT_surface.'''

    bl_idname = "MITSUBA_MATERIAL_PT_surface"
    bl_label = "Surface"
    bl_context = "material"
    bl_order = 2

    @classmethod
    def poll(cls, context):
        return context.material and super().poll(context)

    def draw(self, context):
        layout = self.layout
        mat = context.material

        if not node_view(layout, mat, "Surface"):
            layout.prop(mat, "use_nodes", icon='NODETREE')
            layout.use_property_split = True
            # EEVEE also offers metallic, specular and roughness here, but the
            # exporter's non-node path reads only diffuse_color.
            layout.prop(mat, "diffuse_color", text="Base Color")


class MITSUBA_WORLD_PT_surface(MitsubaPanel, bpy.types.Panel):
    '''Replaces EEVEE_WORLD_PT_surface.'''

    bl_idname = "MITSUBA_WORLD_PT_surface"
    bl_label = "Surface"
    bl_context = "world"

    @classmethod
    def poll(cls, context):
        return context.world and super().poll(context)

    def draw(self, context):
        layout = self.layout
        world = context.world

        layout.use_property_split = True

        if not node_view(layout, world, "Surface"):
            # 4.2 lets a world go without nodes and 5.2 does not, so the toggle
            # only appears where it does something.
            layout.prop(world, "use_nodes", icon='NODETREE')
            layout.prop(world, "color")


# Blender's own Radius is `shadow_soft_size`, whose tooltip reads "Light size
# for ray shadow sampling (Raytraced shadows)". None of that is true under
# misuka, which has no raytraced shadows and reads the value only when an
# Acoustic export builds a spherical emitter. A tooltip cannot be overridden on
# a built-in property, so the panel draws a proxy that reads and writes the
# same field and carries wording that matches what the exporter does with it.

POINT_RADIUS_DESCRIPTION = (
    "Radius of the sphere an Acoustic export writes for this emitter. "
    "It does not affect shadows, and a Visual export ignores it and writes an "
    "emitter with no size"
)

SPOT_RADIUS_DESCRIPTION = (
    "Unused. It does not affect shadows, an Acoustic export skips spot "
    "emitters, and a Visual export writes a spot emitter with no size"
)


def _get_emitter_radius(self):
    return self.shadow_soft_size


def _set_emitter_radius(self, value):
    self.shadow_soft_size = value


def emitter_radius_property(description):
    return FloatProperty(
        name="Radius",
        description=description,
        subtype='DISTANCE',
        unit='LENGTH',
        min=0.0,
        soft_max=100.0,
        # Blender divides `step` by 100, so this is the 0.1 the built-in uses.
        step=10,
        precision=3,
        get=_get_emitter_radius,
        set=_set_emitter_radius,
    )


# `shadow_soft_size` lives on the subtypes, not on Light, so the proxy does too.
radius_owners = (
    (bpy.types.PointLight, POINT_RADIUS_DESCRIPTION),
    (bpy.types.SpotLight, SPOT_RADIUS_DESCRIPTION),
)


classes = (
    MITSUBA_LIGHT_PT_light,
    MITSUBA_LIGHT_PT_beam_shape,
    MITSUBA_MATERIAL_PT_context,
    MITSUBA_MATERIAL_PT_surface,
    MITSUBA_WORLD_PT_surface,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    for owner, description in radius_owners:
        owner.mitsuba_emitter_radius = emitter_radius_property(description)


def unregister():
    for owner, _ in radius_owners:
        del owner.mitsuba_emitter_radius
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
