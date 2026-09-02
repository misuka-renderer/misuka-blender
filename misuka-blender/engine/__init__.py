import bpy
from .final import MitsubaRenderEngine

def get_panels():
    # Blender builds the node editor copies of a panel with a plain dict copy,
    # so a panel and its NODE_ twin share one COMPAT_ENGINES set object and both
    # land in the sweep below. Excluding only one name therefore does nothing:
    # the loop reaches the other and writes MITSUBA into the set they share.
    # Every exclusion needs both names. Cycles does the same.
    exclude_panels = {
        'VIEWLAYER_PT_filter',
        'VIEWLAYER_PT_layer_passes',
        'RENDER_PT_simplify',
        'RENDER_PT_color_management',
        'RENDER_PT_freestyle',
        # engine.panels draws these instead. DATA_PT_light is only the light
        # type row, which MITSUBA_LIGHT_PT_light already has, and DATA_PT_spot
        # parents to the EEVEE panel, so it never draws under misuka anyway.
        # NODE_DATA_PT_spot does not exist in 4.2 or 5.2; naming it costs
        # nothing and keeps the pair complete if Blender adds it.
        'DATA_PT_light',
        'NODE_DATA_PT_light',
        'DATA_PT_spot',
        'NODE_DATA_PT_spot',
    }

    by_name = {
        panel.__name__: panel for panel in bpy.types.Panel.__subclasses__()
    }

    def is_excluded(panel):
        # Blender does not draw a child panel whose parent is hidden, so
        # tagging one whose parent we excluded only adds MITSUBA to something
        # that can never appear. Walk up rather than naming the children:
        # Blender reworked the color management ones between 4.2 and 5.2.
        seen = set()
        name = panel.__name__
        while name and name not in seen:
            if name in exclude_panels:
                return True
            seen.add(name)
            parent = by_name.get(name)
            name = getattr(parent, 'bl_parent_id', None) if parent else None
        return False

    panels = []
    for panel in bpy.types.Panel.__subclasses__():
        if hasattr(panel, 'COMPAT_ENGINES') and 'BLENDER_RENDER' in panel.COMPAT_ENGINES:
            if not is_excluded(panel):
                panels.append(panel)

    return panels

def register():
    from . import properties
    properties.register()
    bpy.utils.register_class(MitsubaRenderEngine)
    for panel in get_panels():
        panel.COMPAT_ENGINES.add('MITSUBA')

def unregister():
    from . import properties
    properties.unregister()
    bpy.utils.unregister_class(MitsubaRenderEngine)
    for panel in get_panels():
        if 'MITSUBA' in panel.COMPAT_ENGINES:
            panel.COMPAT_ENGINES.remove('MITSUBA')
