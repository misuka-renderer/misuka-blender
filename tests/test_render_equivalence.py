'''
Render the same scene in Cycles and in misuka, and compare the two images.

The rest of the suite reads the exported XML, which says whether a number was
written but not whether it means the same thing on the other side. misuka's
`principled` squares the roughness itself, for one, so the exporter squaring it
too made every highlight far sharper than Blender's, and no amount of reading
the XML would have shown it.

Two lighting setups, each blind to what the other sees:

- A furnace. Lighting is a uniform white environment, so every visible point
  returns the albedo the BSDF decides and nothing else. That pins down color
  and energy, and says nothing about the shape of the lobe.
- A point lamp. The highlight's size is then the whole story, which is what
  catches a roughness that means something different on the two sides.
'''
import os

import bpy
import numpy as np
import pytest

from fixtures import skip_on_windows


RESOLUTION = 64
SAMPLES = 32

# Every test here renders the exported scene, which means instantiating it.
pytestmark = skip_on_windows


@pytest.fixture
def scene():
    '''
    A scene of its own, so the comparison neither sees nor leaves any state.

    `read_factory_settings()` would be the obvious way to get a clean file, but
    it resets the preferences too and would switch the add-on off for the rest
    of the session.
    '''
    previous = bpy.context.window.scene
    sc = bpy.data.scenes.new('equivalence')
    bpy.context.window.scene = sc

    sc.render.engine = 'CYCLES'
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = False
    sc.render.resolution_x = RESOLUTION
    sc.render.resolution_y = RESOLUTION
    sc.render.film_transparent = True  # the alpha channel is our object mask
    sc.render.image_settings.file_format = 'OPEN_EXR'
    sc.render.image_settings.color_depth = '32'
    sc.render.image_settings.color_mode = 'RGBA'
    sc.view_settings.view_transform = 'Standard'
    sc.mitsuba.active_integrator = 'path'

    mesh = bpy.ops.mesh.primitive_uv_sphere_add
    with bpy.context.temp_override(scene=sc):
        mesh(radius=1.0, segments=48, ring_count=24)
        bpy.ops.object.shade_smooth()

    camera = bpy.data.objects.new('camera', bpy.data.cameras.new('camera'))
    camera.location = (0, -5, 0)
    camera.rotation_euler = (np.pi / 2, 0, 0)
    sc.collection.objects.link(camera)
    sc.camera = camera

    yield sc

    bpy.context.window.scene = previous
    bpy.data.scenes.remove(sc)


def sphere(scene):
    return next(obj for obj in scene.objects if obj.type == 'MESH')


def furnace(scene):
    '''Uniform white lighting from every direction.'''
    world = bpy.data.worlds.new('furnace')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (1, 1, 1, 1)
    scene.world = world


def point_lamp(scene):
    light = bpy.data.lights.new('lamp', type='POINT')
    light.energy = 1000.0
    light.shadow_soft_size = 0.0
    scene.collection.objects.link(bpy.data.objects.new('lamp', light))
    scene.collection.objects['lamp'].location = (3, -3, 4)


def shader(scene, node_type, **inputs):
    '''Give the sphere a material whose surface is `node_type`.'''
    mat = bpy.data.materials.new('equivalence')
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    for node in list(nodes):
        if node.type != 'OUTPUT_MATERIAL':
            nodes.remove(node)

    node = nodes.new(node_type)
    for name, value in inputs.items():
        node.inputs[name].default_value = value
    mat.node_tree.links.new(node.outputs[0], nodes['Material Output'].inputs['Surface'])

    sphere(scene).data.materials.append(mat)
    return mat


def render_cycles(scene, tmp_path):
    '''Render with Cycles, and return linear pixels plus the object mask.'''
    scene.render.filepath = os.path.join(str(tmp_path), 'cycles')
    with bpy.context.temp_override(scene=scene):
        bpy.ops.render.render(write_still=True)

    image = bpy.data.images.load(os.path.join(str(tmp_path), 'cycles.exr'))
    # Blender hands over its pixels bottom row first.
    pixels = np.array(image.pixels[:]).reshape(RESOLUTION, RESOLUTION, 4)[::-1]
    bpy.data.images.remove(image)

    return pixels[:, :, :3], pixels[:, :, 3] > 0.999


def render_misuka(scene, tmp_path):
    import misuka as mi

    path = os.path.join(str(tmp_path), 'scene.xml')
    with bpy.context.temp_override(scene=scene):
        assert bpy.ops.export_scene.mitsuba(
            filepath=path, export_mode='VISUAL') == {'FINISHED'}

    return np.array(mi.render(mi.load_file(path), spp=SAMPLES))[:, :, :3]


def both(scene, tmp_path):
    cycles, mask = render_cycles(scene, tmp_path)
    misuka = render_misuka(scene, tmp_path)
    assert mask.sum() > 200, 'the sphere covers too little of the frame to compare'
    return cycles[mask], misuka[mask], mask


def lit_share(pixels, level):
    '''What fraction of the object is brighter than `level`.'''
    return (pixels.max(axis=1) > level).mean()


def test_a_diffuse_sphere_returns_its_albedo(scene, tmp_path):
    '''The plainest case there is, and the one that pins down color.'''
    furnace(scene)
    shader(scene, 'ShaderNodeBsdfDiffuse', Color=(0.2, 0.5, 0.8, 1.0))

    cycles, misuka, _ = both(scene, tmp_path)

    assert misuka.mean(axis=0) == pytest.approx(cycles.mean(axis=0), abs=0.01)
    assert misuka.mean(axis=0) == pytest.approx([0.2, 0.5, 0.8], abs=0.01)


def test_a_mirror_returns_its_color(scene, tmp_path):
    furnace(scene)
    shader(scene, 'ShaderNodeBsdfGlossy',
           Color=(0.9, 0.6, 0.3, 1.0), Roughness=0.0)

    cycles, misuka, _ = both(scene, tmp_path)

    assert misuka.mean(axis=0) == pytest.approx(cycles.mean(axis=0), abs=0.02)


def test_an_emitter_ships_its_radiance(scene, tmp_path):
    furnace(scene)
    shader(scene, 'ShaderNodeEmission', Color=(1.0, 0.5, 0.2, 1.0), Strength=2.0)

    cycles, misuka, _ = both(scene, tmp_path)

    assert misuka.mean(axis=0) == pytest.approx(cycles.mean(axis=0), abs=0.02)
    assert misuka.mean(axis=0) == pytest.approx([2.0, 1.0, 0.4], abs=0.02)


@pytest.mark.parametrize('node_type, inputs', [
    ('ShaderNodeBsdfGlossy', {'Roughness': 0.3}),
    ('ShaderNodeBsdfPrincipled', {'Roughness': 0.3, 'Metallic': 1.0}),
])
def test_a_highlight_is_the_size_blender_draws_it(scene, tmp_path, node_type, inputs):
    '''
    A furnace conserves energy whatever the lobe looks like, so only a lamp can
    tell whether the roughness meant the same thing on both sides.

    misuka's principled squares the roughness itself, so the exporter squaring
    it as well made this highlight about four times sharper than Blender's.
    '''
    point_lamp(scene)
    shader(scene, node_type, **inputs)

    cycles, misuka, _ = both(scene, tmp_path)

    for level in (1.0, 4.0):
        assert lit_share(misuka, level) == pytest.approx(
            lit_share(cycles, level), rel=0.35, abs=0.004), \
            f'the highlight above {level} is a different size'
