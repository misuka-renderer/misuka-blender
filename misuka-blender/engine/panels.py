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
            col.prop(light, "shadow_soft_size", text="Radius")

            # Which export mode is running is a setting on the export operator,
            # so no panel can read it. Name both cases instead. label() does
            # not wrap, so this goes through the same helper as the acoustic
            # material help.
            notes = [
                "The radius is only used in an Acoustic export, to build a "
                "spherical emitter. A Visual export ignores it and writes an "
                "emitter with no size.",
                "For an emitter that behaves the same in both modes, give a "
                "sphere mesh an Emission material instead.",
            ]

            # Only convert_point_light() drops the color in Acoustic mode. The
            # spot, sun and area converters still write a tinted RGB value, so
            # this cannot be said for them yet.
            if light.type == 'POINT':
                notes.insert(0,
                    "Color is only used in a Visual export. An Acoustic "
                    "export builds a uniform emission spectrum from Power "
                    "alone."
                )

            draw_paragraphs(col, context, *notes)
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


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
