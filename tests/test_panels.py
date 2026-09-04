'''
Panel visibility under the misuka render engine.

`engine.get_panels()` only ever adds MITSUBA to panels Blender tags
BLENDER_RENDER, so anything tagged EEVEE-only or Cycles-only stays hidden, and
so does any child panel whose parent is hidden. That is how Color, Power,
Radius, Beam Shape, the material slot list and both Surface panels went missing.

These run inside Blender with the addon enabled (see scripts/run_tests.py).
'''
import importlib

import bpy
import pytest


panels = importlib.import_module('misuka-blender.engine.panels')
engine_props = importlib.import_module('misuka-blender.engine.properties')
io_module = importlib.import_module('misuka-blender.io')


@pytest.fixture
def engine():
    '''Run a test under a chosen engine and put the scene back afterwards.'''
    original = bpy.context.scene.render.engine

    def use(name):
        bpy.context.scene.render.engine = name
        return bpy.context

    yield use
    bpy.context.scene.render.engine = original


@pytest.fixture
def make_light():
    '''
    Build a light of a given type.

    Setting light.type swaps the datablock's RNA type, so a spot light has to
    be created as one. A POINT reference kept across the change has no
    spot_size.
    '''
    created = []

    def make(light_type):
        data = bpy.data.lights.new(name='TestLight', type=light_type)
        obj = bpy.data.objects.new(name='TestLight', object_data=data)
        bpy.context.scene.collection.objects.link(obj)
        created.append((obj, data.name))
        return bpy.data.lights[data.name]

    yield make

    for obj, name in created:
        bpy.data.objects.remove(obj)
        bpy.data.lights.remove(bpy.data.lights[name])


class StubLayout:
    '''
    Minimal stand-in for Blender's UILayout, as in test_acoustic.

    Panels cannot be drawn in background mode. Every prop() resolves the
    property for real, so a mistyped name fails the test.
    '''

    def __init__(self, drawn):
        self.drawn = drawn
        self.use_property_split = False
        self.use_property_decorate = False

    def column(self, **kwargs):
        return StubLayout(self.drawn)

    row = box = split = column

    def separator(self, **kwargs):
        pass

    def label(self, text='', icon='NONE', **kwargs):
        self.drawn.append(('label', text))

    def operator(self, idname, text='', **kwargs):
        self.drawn.append(('operator', idname))
        return StubLayout(self.drawn)

    def menu(self, idname, **kwargs):
        self.drawn.append(('menu', idname))

    def template_list(self, *args, **kwargs):
        self.drawn.append(('template_list', args[0]))

    def template_ID(self, data, name, **kwargs):
        self.drawn.append(('template_ID', name))

    def template_node_view(self, ntree, node, socket):
        self.drawn.append(('template_node_view', socket.identifier))

    def prop(self, data, name, index=-1, **kwargs):
        getattr(data, name)
        self.drawn.append(('prop', name))


class StubContext:
    '''Just enough context for a panel's draw().'''

    def __init__(self, **kwargs):
        self.scene = bpy.context.scene
        self.engine = bpy.context.scene.render.engine
        self.light = None
        self.material = None
        self.material_slot = None
        self.world = None
        self.object = None
        self.space_data = None
        for key, value in kwargs.items():
            setattr(self, key, value)


def draw(panel, **kwargs):
    drawn = []
    stub = type('Stub', (), {'draw': panel.draw})()
    stub.layout = StubLayout(drawn)
    stub.draw(StubContext(**kwargs))
    return [name for kind, name in drawn]


# --- The reported bug -------------------------------------------------------

def test_a_point_light_shows_color_power_and_radius(engine, make_light):
    point_light = make_light('POINT')
    ctx = engine('MITSUBA')
    assert panels.MITSUBA_LIGHT_PT_light.poll(
        StubContext(light=point_light, engine=ctx.scene.render.engine))

    drawn = draw(panels.MITSUBA_LIGHT_PT_light, light=point_light)
    assert 'color' in drawn
    assert 'energy' in drawn
    assert 'mitsuba_emitter_radius' in drawn


def test_the_radius_tooltip_does_not_promise_shadows(engine):
    '''
    Blender's own Radius is `shadow_soft_size`, tooltipped "Light size for ray
    shadow sampling". misuka has no raytraced shadows and reads the value only
    to size a spherical emitter in an Acoustic export, so the panel draws a
    proxy whose wording matches.
    '''
    engine('MITSUBA')
    for cls in (bpy.types.PointLight, bpy.types.SpotLight):
        prop = cls.bl_rna.properties['mitsuba_emitter_radius']
        assert prop.name == 'Radius'
        assert 'shadow sampling' not in prop.description
        assert 'does not affect shadows' in prop.description


def test_the_radius_proxy_reads_and_writes_the_blender_field(engine, make_light):
    '''The proxy stores nothing of its own, so both directions must agree.'''
    engine('MITSUBA')
    light = make_light('POINT')

    light.mitsuba_emitter_radius = 0.5
    assert light.shadow_soft_size == pytest.approx(0.5)

    light.shadow_soft_size = 1.25
    assert light.mitsuba_emitter_radius == pytest.approx(1.25)


def test_the_radius_row_names_both_export_modes(engine, make_light):
    '''
    Radius is the source sphere radius in an Acoustic export and discarded in a
    Visual one. Which mode runs is a setting on the export operator, so the
    panel cannot read it and has to name both.
    '''
    point_light = make_light('POINT')
    engine('MITSUBA')
    drawn = []
    stub = type('Stub', (), {'draw': panels.MITSUBA_LIGHT_PT_light.draw})()
    stub.layout = StubLayout(drawn)
    stub.draw(StubContext(light=point_light))

    labels = ' '.join(text for kind, text in drawn if kind == 'label')
    assert 'Acoustic' in labels
    assert 'Visual' in labels


def test_only_a_point_light_claims_the_color_is_dropped(engine, make_light):
    '''
    convert_point_light() is the only converter with an acoustic branch. The
    spot, sun and area ones still write energy * color, so the note would be
    wrong on them.
    '''
    engine('MITSUBA')

    def notes(light):
        drawn = []
        stub = type('Stub', (), {'draw': panels.MITSUBA_LIGHT_PT_light.draw})()
        stub.layout = StubLayout(drawn)
        stub.draw(StubContext(light=light))
        return ' '.join(text for kind, text in drawn if kind == 'label')

    assert 'Color is only used' in notes(make_light('POINT'))
    assert 'Color is only used' not in notes(make_light('SPOT'))
    assert 'Color is only used' not in notes(make_light('AREA'))


@pytest.mark.parametrize('light_type', ['SPOT', 'SUN', 'AREA'])
def test_a_non_point_light_says_an_acoustic_export_skips_it(
        engine, make_light, light_type):
    '''Matches what export_light() actually does with them.'''
    engine('MITSUBA')

    drawn = []
    stub = type('Stub', (), {'draw': panels.MITSUBA_LIGHT_PT_light.draw})()
    stub.layout = StubLayout(drawn)
    stub.draw(StubContext(light=make_light(light_type)))

    text = ' '.join(t for kind, t in drawn if kind == 'label')
    assert 'only supports point lights' in text
    assert 'skipped' in text


def test_a_spot_light_shows_beam_shape(engine, make_light):
    spot = make_light('SPOT')
    engine('MITSUBA')

    assert panels.MITSUBA_LIGHT_PT_beam_shape.poll(StubContext(light=spot))
    drawn = draw(panels.MITSUBA_LIGHT_PT_beam_shape, light=spot)
    assert 'spot_size' in drawn
    assert 'spot_blend' in drawn


def test_beam_shape_is_only_for_spot_lights(engine, make_light):
    point_light = make_light('POINT')
    engine('MITSUBA')
    assert not panels.MITSUBA_LIGHT_PT_beam_shape.poll(
        StubContext(light=point_light))


def test_exactly_one_panel_is_titled_light(engine):
    '''
    DATA_PT_light carries BLENDER_RENDER, so it gets MITSUBA from the sweep and
    would sit next to ours drawing a second, near-empty "Light" panel.
    '''
    engine('MITSUBA')
    titled = [
        cls.__name__
        for cls in bpy.types.Panel.__subclasses__()
        if getattr(cls, 'bl_space_type', '') == 'PROPERTIES'
        and getattr(cls, 'bl_context', '') == 'data'
        and getattr(cls, 'bl_label', '').startswith('Light')
        and 'MITSUBA' in getattr(cls, 'COMPAT_ENGINES', set())
    ]
    assert titled == ['MITSUBA_LIGHT_PT_light']


def test_the_node_editor_twin_does_not_leak_mitsuba_back_in():
    '''
    A panel and its NODE_ copy share one COMPAT_ENGINES set object, so adding
    MITSUBA to either adds it to both. Excluding one name alone does nothing.
    '''
    twin = getattr(bpy.types, 'NODE_DATA_PT_light', None)
    if twin is None:
        pytest.skip('This Blender has no NODE_DATA_PT_light')

    assert 'MITSUBA' not in bpy.types.DATA_PT_light.COMPAT_ENGINES
    assert 'MITSUBA' not in twin.COMPAT_ENGINES


# --- Material and world -----------------------------------------------------

def test_the_material_slot_list_is_reachable(engine):
    '''
    Without it there is no New button, so an object never gets a material and
    ACOUSTIC_PT_material never polls.
    '''
    engine('MITSUBA')
    mesh = bpy.data.meshes.new('TestMesh')
    obj = bpy.data.objects.new('TestObject', mesh)
    bpy.context.scene.collection.objects.link(obj)
    try:
        assert panels.MITSUBA_MATERIAL_PT_context.poll(StubContext(object=obj))
        drawn = draw(panels.MITSUBA_MATERIAL_PT_context, object=obj)
        assert 'MATERIAL_UL_matslots' in drawn
        assert 'active_material' in drawn
    finally:
        bpy.data.objects.remove(obj)
        bpy.data.meshes.remove(mesh)


def test_the_material_surface_falls_back_to_diffuse_color_only(engine):
    '''
    EEVEE also offers metallic, specular and roughness on the non-node path.
    The exporter reads none of them (materials.py), so neither do we.
    '''
    engine('MITSUBA')
    mat = bpy.data.materials.new('TestMaterial')
    mat.use_nodes = False
    try:
        if mat.use_nodes:
            pytest.skip('This Blender pins materials to nodes')

        assert panels.MITSUBA_MATERIAL_PT_surface.poll(StubContext(material=mat))
        drawn = draw(panels.MITSUBA_MATERIAL_PT_surface, material=mat)
        assert 'diffuse_color' in drawn
        assert 'metallic' not in drawn
        assert 'roughness' not in drawn
    finally:
        bpy.data.materials.remove(mat)


def test_the_world_surface_shows_the_output_node(engine):
    engine('MITSUBA')
    world = bpy.data.worlds.new('TestWorld')
    world.use_nodes = True
    try:
        assert panels.MITSUBA_WORLD_PT_surface.poll(StubContext(world=world))
        drawn = draw(panels.MITSUBA_WORLD_PT_surface, world=world)
        assert 'Surface' in drawn
    finally:
        bpy.data.worlds.remove(world)


def test_the_panels_read_the_same_output_node_as_the_exporter():
    '''
    The exporter used to look the node up by name. Both sides now ask for the
    target-agnostic one, so a Cycles-target output node cannot make the panel
    show something other than what gets exported.
    '''
    mat = bpy.data.materials.new('TestMaterial')
    mat.use_nodes = True
    try:
        tree = mat.node_tree
        extra = tree.nodes.new('ShaderNodeOutputMaterial')
        extra.target = 'CYCLES'
        extra.is_active_output = True

        assert tree.get_output_node('ALL') != extra
        assert tree.get_output_node('ALL') == tree.nodes['Material Output']
    finally:
        bpy.data.materials.remove(mat)


# --- Acoustic settings live on the misuka engine ----------------------------

def acoustic_panels():
    '''
    Every acoustic panel the add-on registers.

    Discovered rather than listed, so a panel added or retired later is still
    covered. The two help panels are already on their way out once the docs
    land, see misuka-renderer/misuka-blender#14.
    '''
    found = [
        getattr(io_module, name)
        for name in dir(io_module)
        if name.startswith('ACOUSTIC_PT_')
    ]
    assert found, 'no acoustic panels found'
    return found

MISUKA_PANELS = (
    'MITSUBA_RENDER_PT_acoustic',
    'MITSUBA_RENDER_PT_integrator_acoustic',
    'MITSUBA_CAMERA_PT_sampler_acoustic',
    'MITSUBA_CAMERA_PT_rfilter_acoustic',
    'MITSUBA_RENDER_PT_visual',
    'MITSUBA_RENDER_PT_integrator_visual',
    'MITSUBA_CAMERA_PT_sampler_visual',
    'MITSUBA_CAMERA_PT_rfilter_visual',
    'MITSUBA_OUTPUT_PT_acoustic_film',
)

# One heading per export mode, with the same three panels under each.
ENGINE_SETTINGS = (
    ('MITSUBA_RENDER_PT_acoustic', 'Acoustic', (
        ('MITSUBA_RENDER_PT_integrator_acoustic', 'Integrator'),
        ('MITSUBA_CAMERA_PT_sampler_acoustic', 'Sampler'),
        ('MITSUBA_CAMERA_PT_rfilter_acoustic', 'Reconstruction Filter'),
    )),
    ('MITSUBA_RENDER_PT_visual', 'Visual', (
        ('MITSUBA_RENDER_PT_integrator_visual', 'Integrator'),
        ('MITSUBA_CAMERA_PT_sampler_visual', 'Sampler'),
        ('MITSUBA_CAMERA_PT_rfilter_visual', 'Reconstruction Filter'),
    )),
)


def test_the_engine_settings_are_grouped_by_export_mode():
    '''
    The mode names the group, so each panel under it is labelled with what it
    is. They used to sit side by side at the top level, each carrying its mode
    in its own label.
    '''
    registered = list(engine_props.PANELS)

    for parent_name, heading, children in ENGINE_SETTINGS:
        parent = getattr(engine_props, parent_name)

        assert parent.bl_label == heading
        assert not hasattr(parent, 'bl_parent_id'), parent_name

        for child_name, label in children:
            child = getattr(engine_props, child_name)

            assert child.bl_parent_id == parent_name, child_name
            assert child.bl_label == label, child_name

        # Blender draws panels in registration order, so a group is registered
        # as a block, its heading first.
        block = [parent] + [getattr(engine_props, name) for name, _ in children]
        start = registered.index(parent)
        assert registered[start:start + len(block)] == block, parent_name


@pytest.mark.parametrize('other', ['BLENDER_EEVEE_NEXT', 'CYCLES'])
def test_acoustic_material_panels_are_misuka_only(engine, other):
    mat = bpy.data.materials.new('TestMaterial')
    try:
        for panel in acoustic_panels():
            name = panel.__name__

            engine('MITSUBA')
            assert panel.poll(StubContext(material=mat)), name

            if other not in {e.identifier for e
                             in bpy.types.RenderSettings.bl_rna
                             .properties['engine'].enum_items}:
                continue
            engine(other)
            assert not panel.poll(StubContext(material=mat)), name
    finally:
        bpy.data.materials.remove(mat)


def test_the_camera_sampler_and_filter_no_longer_leak(engine):
    '''They had no COMPAT_ENGINES and no poll, so they drew under every engine.'''
    for name in MISUKA_PANELS:
        panel = getattr(engine_props, name)
        assert panel.COMPAT_ENGINES == {'MITSUBA'}, name

        engine('MITSUBA')
        assert panel.poll(StubContext()), name

        engine('CYCLES')
        assert not panel.poll(StubContext()), name


# --- Guard against the next instance of this bug ----------------------------

def visible_under_misuka(cls):
    return 'MITSUBA' in getattr(cls, 'COMPAT_ENGINES', set())


def test_no_panel_is_orphaned_under_misuka():
    '''
    Blender does not draw a child panel whose parent does not poll. That is how
    Beam Shape disappeared: DATA_PT_spot carries BLENDER_RENDER, so the sweep
    tagged it, but it parents to the EEVEE-only DATA_PT_EEVEE_light.

    Parents with no COMPAT_ENGINES at all are engine independent and always
    draw, so they are not orphans.
    '''
    by_name = {
        cls.__name__: cls
        for cls in bpy.types.Panel.__subclasses__()
    }

    orphans = []
    for cls in bpy.types.Panel.__subclasses__():
        if getattr(cls, 'bl_space_type', '') != 'PROPERTIES':
            continue
        if not visible_under_misuka(cls):
            continue

        parent_name = getattr(cls, 'bl_parent_id', None)
        if not parent_name:
            continue

        parent = by_name.get(parent_name)
        if parent is None or not hasattr(parent, 'COMPAT_ENGINES'):
            continue
        if not visible_under_misuka(parent):
            orphans.append(f'{cls.__name__} -> {parent_name}')

    assert orphans == []


# One row per property the exporter reads, so a Blender rename fails loudly
# here rather than silently blanking a panel again.
REQUIRED_PANELS = (
    ('MITSUBA_LIGHT_PT_light', 'color, energy, mitsuba_emitter_radius, shape, size'),
    ('MITSUBA_LIGHT_PT_beam_shape', 'spot_size, spot_blend'),
    ('MITSUBA_MATERIAL_PT_context', 'material slots'),
    ('MITSUBA_MATERIAL_PT_surface', 'material Surface socket'),
    ('MITSUBA_WORLD_PT_surface', 'world Surface socket'),
)


@pytest.mark.parametrize('name,reads', REQUIRED_PANELS)
def test_every_exporter_read_property_has_a_panel(engine, name, reads):
    engine('MITSUBA')
    panel = getattr(bpy.types, name, None)
    assert panel is not None, f'{name} is not registered, so {reads} is unreachable'
    assert visible_under_misuka(panel), name


def order_of(panel):
    '''Blender defaults an unset bl_order to 0.'''
    return getattr(panel, 'bl_order', 0)


def test_the_material_selector_stays_above_the_acoustic_panels():
    '''
    io.register() runs before engine.register(), so on a tie at bl_order 0 the
    acoustic panels would sit above the material selector and bury the New
    button. Only positive orders help: the RNA clamps a negative one to 0.
    '''
    assert order_of(panels.MITSUBA_MATERIAL_PT_context) < \
        order_of(io_module.ACOUSTIC_PT_material)
    assert order_of(io_module.ACOUSTIC_PT_material) < \
        order_of(panels.MITSUBA_MATERIAL_PT_surface)

    # and all of them stay above Blender's, which sit at 10 and higher
    assert order_of(panels.MITSUBA_MATERIAL_PT_surface) < \
        order_of(bpy.types.MATERIAL_PT_viewport)
