import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty
)
from bpy.types import Panel, PropertyGroup, Operator
import os
from os.path import basename, dirname

from ..io import acoustic_bands
from ..docs import draw_help_button

import json
# Read plugin data from JSON files
with open(os.path.join(dirname(__file__), "integrators.json")) as file:
    integrator_data = json.load(file)
with open(os.path.join(dirname(__file__), "samplers.json")) as file:
    sampler_data = json.load(file)
with open(os.path.join(dirname(__file__), "rfilters.json")) as file:
    rfilter_data = json.load(file)

# What the acoustic half of the Sampler panel changes about the plugin the JSON
# describes. Only the sample count differs, and only in what a sensible value
# is: the same rays are spread over time bins and frequency bands, so a count
# that gives a clean image gives a noisy energy-time curve.
ACOUSTIC_SAMPLER_OVERRIDES = {
    'sample_count' : {
        'description' : "Rays traced per frequency band. misuka traces an even square number of them most efficiently",
        'default' : 2 ** 18,
        # A Blender integer is a signed 32-bit one, so this is the real ceiling.
        # The slider stops well short of it, since nothing sensible goes there.
        'max' : 2 ** 32 - 1,
        'soft_max' : 2 ** 28,
    }
}

def plugin_limits(param_dict):
    '''
    The bounds one JSON parameter puts on its property.

    `min` and `max` are hard: Blender refuses a value outside them, typed or
    scripted. `soft_min` and `soft_max` only stop the slider, for a parameter
    whose sensible range is far narrower than its valid one. A hard bound is
    the slider bound too unless the JSON gives its own.
    '''
    limits = {key: param_dict[key] for key in
              ('min', 'max', 'soft_min', 'soft_max') if key in param_dict}

    for hard, soft in (('min', 'soft_min'), ('max', 'soft_max')):
        if hard in limits:
            limits.setdefault(soft, limits[hard])

    return limits


def create_plugin_props(name, arg_dict, depth=1, prefix="", overrides=None):
    '''
    Dynamically create a PropertyGroup for a given plugin defined in arg_dict.
    This allows us to avoid manually creating classes for each plugin (e.g. integrator, BSDF, etc.)

    Params
    ------

    name: the name of the Mitsuba plugin
    arg_dict: the labels, description and properties defined in the JSON plugin files
    depth: Recursion depth (for nested plugins, e.g. Stokes integrator) We only allow a certain amount of nesting, to avoid infinite definition of properties
    prefix: Prefix to use to declare a class with a unique name
    overrides: per-parameter keys that replace the JSON ones, for a second set
               of properties built from the same plugin. The default and the
               range that suit one context can be wrong in another: an acoustic
               run needs orders of magnitude more samples than an image.
               Needs its own `prefix`, since it declares its own class.
    '''
    overrides = overrides or {}
    prefix += name.title()
    plugin_props = type("%sProps" % prefix, (PropertyGroup, ), {
        "args": arg_dict
    })
    bpy.utils.register_class(plugin_props)
    custom_draw = set() # List of parameter names that need to call their own draw function (nested plugins)
    # A list rather than a set, so the panel draws the parameters in the order
    # the JSON file lists them.
    props_draw = [] # List of parameters to draw normally, using layout.prop()
    if 'parameters' in arg_dict:
        for param_name, param_dict in arg_dict['parameters'].items():
            param_dict = {**param_dict, **overrides.get(param_name, {})}
            param_type = param_dict['type']
            label = param_dict['label']
            description = param_dict['description'] if 'description' in param_dict else ''
            if 'advanced' in param_dict and param_dict['advanced']:
                continue # TODO
            if param_type == 'integer':
                props_draw.append(param_name)
                setattr(plugin_props, param_name, IntProperty(
                    name = label,
                    description = description,
                    default = param_dict.get('default', 0),
                    **plugin_limits(param_dict)
                ))
            elif param_type == 'boolean':
                props_draw.append(param_name)
                setattr(plugin_props, param_name, BoolProperty(
                    name = label,
                    description = description,
                    default = param_dict.get('default', False)
                ))
            elif param_type == 'float':
                props_draw.append(param_name)
                setattr(plugin_props, param_name, FloatProperty(
                    name = label,
                    description = description,
                    default = param_dict.get('default', 0.0),
                    **plugin_limits(param_dict)
                ))
            # Nested plugin
            elif param_type == 'integrator' or param_type == 'list' and param_dict['values_type'] == 'integrator':
                enum_integrators = []
                # Nested Property group encapsulating the nested integrators
                nested_props_name = "%sNestedIntProps" % prefix
                nested_props = type(nested_props_name, (PropertyGroup, ), {})
                bpy.utils.register_class(nested_props)
                # Property group containint one property group per integrator
                int_props = type("%sIntegratorProps" % prefix, (PropertyGroup, ), {})
                bpy.utils.register_class(int_props)
                for int_name, int_params in integrator_data.items():
                    is_nested = False
                    if 'parameters' in int_params:
                        for param in int_params['parameters'].values():
                            if param['type'] == 'integrator' or param.get('values_type', '') == 'integrator':
                                is_nested = True
                                break
                    if not is_nested or is_nested and depth <= 2:
                        setattr(int_props, int_name, PointerProperty(
                            name = label,
                            description = description,
                            type = create_plugin_props(int_name, int_params, depth=depth+1, prefix=prefix)
                        ))
                        enum_integrators.append((int_name, int_params['label'], int_params['description']))

                setattr(nested_props, "active_integrator", EnumProperty(
                    name = "Integrator",
                    items = enum_integrators
                ))
                setattr(nested_props, "available_integrators", PointerProperty(
                    type = int_props
                ))

                if param_type == 'integrator':
                    def draw_int(self, layout):
                        layout = layout.box()
                        layout.prop(self, "active_integrator")
                        getattr(self.available_integrators, self.active_integrator).draw(layout)
                    setattr(nested_props, "draw", draw_int)
                    setattr(plugin_props, param_name, PointerProperty(
                        name = label,
                        description = description,
                        type = nested_props
                    ))
                else: # List of integrators
                    # In this case, we store the list in a Collection Property and nest it in a PropertyGroup, to add a custom draw method
                    collection_name = "%sIntCollectionProps" % prefix
                    collection_props = type(collection_name, (PropertyGroup, ), {
                        '__annotations__' : {
                            'collection' : CollectionProperty(
                                name = label,
                                description = description,
                                type = nested_props
                            ),
                            'selection' : IntProperty(
                                name = "Selected Integrator",
                                default = 0
                            ),
                            'count' : IntProperty(default=0) # Count of created instances, to give unique names
                        }
                    })
                    def new(self, name="Integrator"):
                        new_int = self.collection.add()
                        if self.count == 0:
                            new_int.name = name
                        else: # Avoid duplicate names
                            zero_count = len(str(self.count))
                            new_int.name = "%s.%s%d" % (name, '0'*(3-zero_count), self.count)
                        self.count += 1
                    setattr(collection_props, "new", new)
                    bpy.utils.register_class(collection_props)
                    def find_class(self, context):
                        '''
                        Look for the given class in the mitsuba settings
                        '''
                        settings = getattr(context.scene.mitsuba.available_integrators, context.scene.mitsuba.visual_integrator)
                        while True:
                            for param in dir(settings):
                                prop = getattr(settings, param)
                                prop_type = type(prop).__name__
                                if 'IntCollection' in prop_type:
                                    if self.class_name == prop_type:
                                        return prop
                                    else:
                                        selection = prop.collection[prop.selection] # Currently selected integrator in the list
                                        settings = getattr(selection.available_integrators, selection.active_integrator)
                                        break # Go to the next depth in the param tree
                                elif 'NestedInt' in prop_type:
                                    settings = getattr(prop.available_integrators, prop.active_integrator)
                                    break # Go to the next depth in the param tree

                    def execute(self, context):
                        '''
                        add/remove an integrator
                        '''
                        if self.action == 'ADD':
                            settings = self.find_class(context)
                            settings.new()
                        else: # 'REMOVE
                            settings = self.find_class(context)
                            settings.collection.remove(settings.selection)
                            settings.selection = max(settings.selection-1, 0)
                        return {'FINISHED'}
                    # Custom operator to add an integrator
                    custom_name = "OT%s" % prefix
                    custom_id = "custom_ot.%s" % custom_name.lower()
                    custom_operator = type(custom_name, (Operator, ), {
                        'bl_label' : custom_name,
                        'bl_idname' : custom_id,
                        'bl_description' : "Add/Remove an integrator.",
                        'class_name' : collection_name,
                        '__annotations__' : {
                            'action' : EnumProperty(items=(
                                ('ADD', "Add", ""),
                                ('REMOVE', "Remove", "")
                            ))},
                        'find_class' : find_class,
                        'execute' : execute
                    })
                    bpy.utils.register_class(custom_operator)

                    def draw_coll(self, layout):
                        # TODO: add the option to hide this
                        layout.label(text = "Integrators List", icon='VIEW_CAMERA')
                        layout.template_list("UI_UL_list", "UL%s"%prefix, self, "collection", self, "selection", rows=4)
                        split = layout.split()
                        split.operator(custom_id, icon='ADD', text="").action = 'ADD'
                        split.operator(custom_id, icon='REMOVE', text="").action = 'REMOVE'
                        if len(self.collection) > self.selection:
                            layout.label(text="Integrator Settings", icon='TOOL_SETTINGS')
                            layout = layout.box()
                            # Nested integrator to display
                            integrator = self.collection[self.selection]
                            layout.prop(integrator, "active_integrator")
                            getattr(integrator.available_integrators, integrator.active_integrator).draw(layout)
                    setattr(collection_props, "draw", draw_coll)
                    setattr(plugin_props, param_name, PointerProperty(
                        name = label,
                        description = description,
                        type = collection_props))
                custom_draw.add(param_name)

            elif param_type == 'list':
                list_type = param_dict['values_type']
                if list_type == 'string':
                    choices = param_dict['choices']
                    for choice, label in choices.items():
                        props_draw.append(choice)
                        setattr(plugin_props, choice, BoolProperty(
                            name = label
                        ))
            else:
                raise NotImplementedError("Unsupported attribute type: %s in plugin '%s'" % (param_type, name))

    def draw(self, layout):
        if 'parameters' in arg_dict:
            for param_name in props_draw:
                layout.prop(self, param_name)
            for param_name in custom_draw:
                getattr(self, param_name).draw(layout)
    setattr(plugin_props, "draw", draw)

    def to_dict(self):
        '''
        Function that converts the plugin into a dict that can be loaded or saved by mitsuba's API
        '''
        plugin_params = {'type' : name}
        if 'parameters' in self.args:
            for param_name, param in self.args['parameters'].items():
                if param['type'] in ('boolean', 'float', 'integer'):
                    plugin_params[param_name] = getattr(self, param_name)
                elif param_type == 'integrator':
                    prop = getattr(self, param_name)
                    plugin_params[param_name] = getattr(prop.available_integrators, prop.active_integrator).to_dict()
                elif param_type == 'list':
                    list_type = param['values_type']
                    if list_type == 'integrator':
                        for integrator in self.integrators.collection:
                            # Make sure we don't have any leading underscores for names - Mitsuba will otherwise complain!
                            plugin_params[integrator.name.lstrip('_')] = getattr(integrator.available_integrators, integrator.active_integrator).to_dict()
                    elif list_type == 'string':
                        selected_items = []
                        for choice in param['choices']:
                            if getattr(self, choice):
                                selected_items.append("%s:%s" % (choice, choice)) #For AOVs, paris have same name and type
                        plugin_params[param_name] = ','.join(selected_items)
        return plugin_params
    setattr(plugin_props, "to_dict", to_dict)
    return plugin_props

class MitsubaRenderSettings(PropertyGroup):
    '''
    Mitsuba main rendering properties
    It creates classes for each plugin described in the JSON files dynamically.
    '''

    # One integrator per export mode, so both are set up and visible at once
    # and neither panel can hold a plugin the other mode needs. An acoustic
    # integrator is the only one a `tape` film can be rendered with, and it
    # cannot produce an image.
    enum_acoustic_integrators = [
        (name, integrator['label'], integrator['description'])
        for name, integrator in integrator_data.items()
        if name.startswith('acoustic')
    ]
    enum_visual_integrators = [
        (name, integrator['label'], integrator['description'])
        for name, integrator in integrator_data.items()
        if not name.startswith('acoustic')
    ]

    acoustic_integrator : EnumProperty(
        name = "Integrator",
        items = enum_acoustic_integrators,
        default = "acoustic_path"
    )

    visual_integrator : EnumProperty(
        name = "Integrator",
        items = enum_visual_integrators,
        default = "path"
    )
    # Dynamic class for integrator parameters
    IntegratorProperties = type("IntegratorProperties",
        (PropertyGroup, ),
        {
            '__annotations__' : {
                # One entry per integrator plugin
                name : PointerProperty(type=create_plugin_props(name, integrator)) for name, integrator in integrator_data.items()
            }
        }
    )
    bpy.utils.register_class(IntegratorProperties)
    available_integrators : PointerProperty(type = IntegratorProperties)

    # Acoustic `tape` film settings, the acoustic equivalent of the image
    # resolution they sit beside. Material coefficients are sampled at these
    # band centres, so this decides which bands actually get simulated.
    acoustic_band_resolution : EnumProperty(
        name = "Band Resolution",
        description = "Frequency bands the acoustic simulation runs at. Material coefficients are sampled at these centres",
        items = acoustic_bands.BAND_RESOLUTION_ITEMS,
        default = 'OCTAVE'
    )

    acoustic_interpolation : EnumProperty(
        name = "Interpolation",
        description = "Frequency axis the material Interpolate buttons work along. Band centres are evenly spaced on the logarithmic one",
        items = acoustic_bands.INTERPOLATION_ITEMS,
        default = 'LOG'
    )

    acoustic_max_time : FloatProperty(
        name = "Max Time",
        description = "How long a tail the impulse response captures, in seconds. Longer costs proportionally more time bins",
        default = 2.0,
        min = 0.001,
        soft_max = 10.0
    )

    acoustic_sampling_rate : FloatProperty(
        name = "Sampling Rate",
        description = "How finely the impulse response is sampled in time, in Hz. This is not an audio sample rate",
        default = 1000.0,
        min = 1.0,
        soft_max = 48000.0
    )

    @classmethod
    def register(cls):
        bpy.types.Scene.mitsuba = PointerProperty(
            name="misuka Render Settings",
            description="misuka render settings",
            type=cls,
        )

    @classmethod
    def unregister(cls):
        del bpy.types.Scene.mitsuba

class MitsubaCameraSettings(PropertyGroup):
    '''
    Mitsuba main camera properties
    It creates classes for each plugin described in the JSON files for rfilters and samplers dynamically.
    '''

    enum_samplers = [(name, sampler['label'], sampler['description']) for name, sampler in sampler_data.items()]

    acoustic_sampler : EnumProperty(
        name = "Sampler",
        items = enum_samplers,
        default = "independent"
    )

    visual_sampler : EnumProperty(
        name = "Sampler",
        items = enum_samplers,
        default = "independent"
    )

    # Dynamic classes for sampler parameters, one set per export mode.
    SamplerProperties = type("SamplerProperties",
        (PropertyGroup, ),
        {
            '__annotations__' : {
                # One entry per sampler plugin
                name : PointerProperty(type=create_plugin_props(name, sampler)) for name, sampler in sampler_data.items()
            }
        }
    )
    bpy.utils.register_class(SamplerProperties)

    AcousticSamplerProperties = type("AcousticSamplerProperties",
        (PropertyGroup, ),
        {
            '__annotations__' : {
                name : PointerProperty(type=create_plugin_props(
                    name, sampler,
                    prefix="Acoustic",
                    overrides=ACOUSTIC_SAMPLER_OVERRIDES
                )) for name, sampler in sampler_data.items()
            }
        }
    )
    bpy.utils.register_class(AcousticSamplerProperties)

    acoustic_samplers : PointerProperty(type = AcousticSamplerProperties)
    visual_samplers : PointerProperty(type = SamplerProperties)

    enum_rfilters = [(name, rfilter['label'], rfilter['description']) for name, rfilter in rfilter_data.items()]

    acoustic_rfilter : EnumProperty(
        name = "Reconstruction Filter",
        items = enum_rfilters,
        default = "gaussian"
    )

    visual_rfilter : EnumProperty(
        name = "Reconstruction Filter",
        items = enum_rfilters,
        default = "gaussian"
    )

    # Dynamic class for reconstruction filter parameters
    RfilterProperties = type("RfilterProperties",
        (PropertyGroup, ),
        {
            '__annotations__' : {
                # One entry per rfilter plugin
                name : PointerProperty(type=create_plugin_props(name, rfilter)) for name, rfilter in rfilter_data.items()
            }
        }
    )
    bpy.utils.register_class(RfilterProperties)
    # Separate storage per mode, since both dropdowns offer the same plugins and
    # a filter that suits an image rarely suits an impulse response.
    acoustic_rfilters : PointerProperty(type = RfilterProperties)
    visual_rfilters : PointerProperty(type = RfilterProperties)

    @classmethod
    def register(cls):
        bpy.types.Camera.mitsuba = PointerProperty(
            name="misuka Camera Settings",
            description="misuka camera settings",
            type=cls,
        )

    @classmethod
    def unregister(cls):
        del bpy.types.Camera.mitsuba

class MitsubaModePanel(bpy.types.Panel):
    '''
    Base for every panel that belongs to one export mode.

    The two modes are set up side by side, each under a heading of its own, so
    a scene ready for an acoustic run keeps its visual settings beside it
    rather than behind a dropdown change. The mode's name is the heading, so
    the panels under it are just Integrator, Sampler and Reconstruction Filter.
    '''

    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render'
    COMPAT_ENGINES = {'MITSUBA'}

    @classmethod
    def poll(cls, context):
        return context.engine in cls.COMPAT_ENGINES


class MITSUBA_RENDER_PT_acoustic(MitsubaModePanel):
    bl_idname = "MITSUBA_RENDER_PT_acoustic"
    bl_label = "Acoustic"

    def draw(self, context):
        pass


class MITSUBA_RENDER_PT_visual(MitsubaModePanel):
    bl_idname = "MITSUBA_RENDER_PT_visual"
    bl_label = "Visual"

    def draw(self, context):
        pass


class MitsubaIntegratorPanel(MitsubaModePanel):
    bl_label = "Integrator"

    def draw(self, context):
        layout = self.layout
        mts_settings = context.scene.mitsuba
        active = getattr(mts_settings, self.integrator_prop)
        layout.prop(mts_settings, self.integrator_prop, text="Integrator")
        getattr(mts_settings.available_integrators, active).draw(layout)


class MITSUBA_RENDER_PT_integrator_acoustic(MitsubaIntegratorPanel):
    bl_idname = "MITSUBA_RENDER_PT_integrator_acoustic"
    bl_parent_id = "MITSUBA_RENDER_PT_acoustic"
    integrator_prop = "acoustic_integrator"


class MITSUBA_RENDER_PT_integrator_visual(MitsubaIntegratorPanel):
    bl_idname = "MITSUBA_RENDER_PT_integrator_visual"
    bl_parent_id = "MITSUBA_RENDER_PT_visual"
    integrator_prop = "visual_integrator"

class MITSUBA_OUTPUT_PT_acoustic_film(bpy.types.Panel):
    '''
    Acoustic counterpart to Blender's Format panel.

    Image resolution and the acoustic band and time resolution are the same kind
    of setting, so they belong next to each other. An acoustic export needs the
    misuka engine, so this panel is gated on it like the rest of the acoustic UI.
    '''

    bl_idname = "MITSUBA_OUTPUT_PT_acoustic_film"
    bl_label = "Acoustic Format"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'output'
    COMPAT_ENGINES = {'MITSUBA'}


    @classmethod
    def poll(cls, context):
        return context.engine in cls.COMPAT_ENGINES

    def draw_header_preset(self, context):
        draw_help_button(self.layout, "guide/scene-settings.html")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        mts_settings = context.scene.mitsuba

        col = layout.column()
        col.prop(mts_settings, "acoustic_band_resolution")

        frequencies = acoustic_bands.resolution_frequencies(
            mts_settings.acoustic_band_resolution
        )
        col.label(
            text=f"{len(frequencies)} bands, "
                 f"{frequencies[0]} Hz to {frequencies[-1] / 1000:g} kHz"
        )

        col.prop(mts_settings, "acoustic_interpolation")

        col = layout.column()
        col.prop(mts_settings, "acoustic_max_time")
        col.prop(mts_settings, "acoustic_sampling_rate")

        # The film takes a bin count; showing what the two settings work out to
        # keeps the cost of raising either of them visible.
        col.label(text=f"{acoustic_bands.time_bins(mts_settings)} time bins")


class MitsubaSamplerPanel(MitsubaModePanel):
    '''
    The sample count each mode wants is orders of magnitude apart, so they are
    set up independently rather than sharing one panel with two counts in it.
    '''

    bl_label = "Sampler"

    def draw(self, context):
        layout = self.layout
        if hasattr(context.scene.camera, 'data'):
            cam_settings = context.scene.camera.data.mitsuba
            active = getattr(cam_settings, self.sampler_prop)
            layout.prop(cam_settings, self.sampler_prop, text="Sampler")
            getattr(getattr(cam_settings, self.samplers_prop), active).draw(layout)


class MITSUBA_CAMERA_PT_sampler_acoustic(MitsubaSamplerPanel):
    bl_idname = "MITSUBA_CAMERA_PT_sampler_acoustic"
    bl_parent_id = "MITSUBA_RENDER_PT_acoustic"
    sampler_prop = "acoustic_sampler"
    samplers_prop = "acoustic_samplers"


class MITSUBA_CAMERA_PT_sampler_visual(MitsubaSamplerPanel):
    bl_idname = "MITSUBA_CAMERA_PT_sampler_visual"
    bl_parent_id = "MITSUBA_RENDER_PT_visual"
    sampler_prop = "visual_sampler"
    samplers_prop = "visual_samplers"

class MitsubaRfilterPanel(MitsubaModePanel):
    '''
    An acoustic export smooths across time bins and a visual one across pixels,
    so the two want different filters and are set up independently.
    '''

    bl_label = "Reconstruction Filter"

    def draw(self, context):
        layout = self.layout
        if hasattr(context.scene.camera, 'data'):
            cam_settings = context.scene.camera.data.mitsuba
            active = getattr(cam_settings, self.rfilter_prop)
            layout.prop(cam_settings, self.rfilter_prop, text="Filter")
            getattr(getattr(cam_settings, self.rfilters_prop), active).draw(layout)


class MITSUBA_CAMERA_PT_rfilter_acoustic(MitsubaRfilterPanel):
    bl_idname = "MITSUBA_CAMERA_PT_rfilter_acoustic"
    bl_parent_id = "MITSUBA_RENDER_PT_acoustic"
    rfilter_prop = "acoustic_rfilter"
    rfilters_prop = "acoustic_rfilters"


class MITSUBA_CAMERA_PT_rfilter_visual(MitsubaRfilterPanel):
    bl_idname = "MITSUBA_CAMERA_PT_rfilter_visual"
    bl_parent_id = "MITSUBA_RENDER_PT_visual"
    rfilter_prop = "visual_rfilter"
    rfilters_prop = "visual_rfilters"

# Panels are drawn in registration order, both the headings and what sits under
# one, and an acoustic export is what the add-on is for, so Acoustic leads.
PANELS = (
    MITSUBA_RENDER_PT_acoustic,
    MITSUBA_RENDER_PT_integrator_acoustic,
    MITSUBA_CAMERA_PT_sampler_acoustic,
    MITSUBA_CAMERA_PT_rfilter_acoustic,
    MITSUBA_RENDER_PT_visual,
    MITSUBA_RENDER_PT_integrator_visual,
    MITSUBA_CAMERA_PT_sampler_visual,
    MITSUBA_CAMERA_PT_rfilter_visual,
    MITSUBA_OUTPUT_PT_acoustic_film,
)


def register():
    from . import panels
    panels.register()
    bpy.utils.register_class(MitsubaRenderSettings)
    bpy.utils.register_class(MitsubaCameraSettings)
    for panel in PANELS:
        bpy.utils.register_class(panel)

def unregister():
    from . import panels
    panels.unregister()
    bpy.utils.unregister_class(MitsubaRenderSettings)
    bpy.utils.unregister_class(MitsubaCameraSettings)
    for panel in reversed(PANELS):
        bpy.utils.unregister_class(panel)