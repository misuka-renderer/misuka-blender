'''
Build the shoebox fixture the pipeline tests run on, and the references they
compare their renders against.

Run it inside Blender, with `misuka` installed in Blender's own Python (see
docs/contributing.md for how):

    blender -b -noaudio --factory-startup --python scripts/make_test_blend.py

Use the **oldest** Blender the CI matrix covers, currently 3.6. Blender opens
files written by older versions but not by newer ones, so a fixture saved by
5.2 would fail every other cell of the matrix.

It writes, all under `tests/res`:

    shoebox.blend            the scene
    references/visual.exr    the reference image
    references/acoustic.npy  the reference energy-time curve

The tests do not compare those files pixel for pixel. They compare aggregates
computed from them, because misuka is free to change how it distributes samples
without being wrong. The full renders are stored anyway so a failure can be
looked at rather than just reported.

Rerun this after changing the scene, or after any change to what the exporter
writes, and read what moved before committing it. A reference that moved for a
reason you cannot explain is the point of having them.
'''
import os
import sys

import bpy

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
RES_DIR = os.path.join(REPO_ROOT, 'tests', 'res')
REFERENCE_DIR = os.path.join(RES_DIR, 'references')
BLEND_PATH = os.path.join(RES_DIR, 'shoebox.blend')

# `tests/shoebox.py` holds the scene and the aggregate helpers, so a reference
# and the test that reads it are computed by the same code.
sys.path.insert(0, os.path.join(REPO_ROOT, 'tests'))


def enable_addon():
    '''
    Link this checkout into Blender's add-on directory and switch it on.

    The same dance as `scripts/run_tests.py`, minus the care that one takes not
    to disturb a developer's real install: this is a one-off tool.
    '''
    addon_source = os.path.join(REPO_ROOT, 'misuka-blender')
    addon_dir = bpy.utils.user_resource('SCRIPTS', path='addons', create=True)
    bpy.utils.refresh_script_paths()

    link = os.path.join(addon_dir, 'misuka-blender')
    if os.path.islink(link):
        os.unlink(link)
    elif os.path.exists(link):
        raise RuntimeError(
            f'{link} exists and is not a link. Move the installed add-on aside.')

    os.symlink(addon_source, link, target_is_directory=True)
    bpy.utils.refresh_script_paths()

    if bpy.ops.preferences.addon_enable(module='misuka-blender') != {'FINISHED'}:
        raise RuntimeError('Cannot enable misuka-blender')

    prefs = bpy.context.preferences.addons['misuka-blender'].preferences
    if not prefs.is_mitsuba_initialized:
        raise RuntimeError(
            'misuka did not initialize. Install it into this Blender\'s Python.')

    return link


def build_scene():
    '''
    A shoebox room with two surfaces, two emitters and two receivers.

    Deliberately more than one of everything, because one of anything cannot
    catch an exporter that writes only the first.
    '''
    from shoebox import (
        ACOUSTIC_MAX_TIME, EMITTER_POWER, EMITTER_RADIUS, FLOOR_BANDS,
        FLOOR_COLOR, RECEIVER_POSITIONS, RESOLUTION, ROOM_SIZE,
        SAMPLING_RATE, SOURCE_POSITIONS, WALL_BANDS, WALL_COLOR, set_bands,
        set_base_color)

    scene = bpy.context.scene
    scene.render.engine = 'MITSUBA'
    scene.render.resolution_x, scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = 100

    scene.mitsuba.acoustic_band_resolution = 'OCTAVE'
    scene.mitsuba.acoustic_max_time = ACOUSTIC_MAX_TIME
    scene.mitsuba.acoustic_sampling_rate = SAMPLING_RATE

    # The enclosure. Its normals point outwards, which does not matter: an
    # acousticbsdf is two-sided, and the visual render sees the inside faces.
    bpy.ops.mesh.primitive_cube_add(size=ROOM_SIZE)
    walls = bpy.context.active_object
    walls.name = 'Walls'
    wall_material = bpy.data.materials.new('WallSurface')
    wall_material.use_nodes = True
    set_base_color(wall_material, WALL_COLOR)
    set_bands(wall_material, WALL_BANDS)
    walls.data.materials.append(wall_material)

    # A separate object rather than a second material slot on the cube, so the
    # export writes two shapes referring to two different bsdfs.
    bpy.ops.mesh.primitive_plane_add(
        size=ROOM_SIZE, location=(0.0, 0.0, -ROOM_SIZE / 2 + 0.01))
    floor = bpy.context.active_object
    floor.name = 'Floor'
    floor_material = bpy.data.materials.new('FloorSurface')
    floor_material.use_nodes = True
    set_base_color(floor_material, FLOOR_COLOR)
    set_bands(floor_material, FLOOR_BANDS)
    floor.data.materials.append(floor_material)

    # Equal Power on purpose. Two emitters at the same level export identical
    # radiance, which misuka merges into one parameter unless `load_file` is
    # given `optimize=False`, and zeroing that one then silences both. Equal
    # Power is what makes the tests able to catch that.
    for index, position in enumerate(SOURCE_POSITIONS):
        bpy.ops.object.light_add(type='POINT', location=position)
        light = bpy.context.active_object
        light.name = f'Source_{index}'
        light.data.energy = EMITTER_POWER
        light.data.shadow_soft_size = EMITTER_RADIUS

    for index, position in enumerate(RECEIVER_POSITIONS):
        bpy.ops.object.camera_add(location=position, rotation=(1.5708, 0.0, 0.0))
        receiver = bpy.context.active_object
        receiver.name = f'Receiver_{index}'
        # A fixed seed is what makes a render repeatable, and a repeatable
        # render is what makes a stored reference mean anything.
        settings = receiver.data.mitsuba
        getattr(settings.acoustic_samplers, settings.acoustic_sampler).seed = 0
        getattr(settings.visual_samplers, settings.visual_sampler).seed = 0

    scene.camera = bpy.data.objects['Receiver_0']

    return scene


def write_references(scene):
    import numpy as np

    from shoebox import (
        ACOUSTIC_SPP, ACOUSTIC_VARIANT, VISUAL_SPP, VISUAL_VARIANT, export,
        render_acoustic, render_visual)

    import misuka as mi

    os.makedirs(REFERENCE_DIR, exist_ok=True)

    visual_xml = export(scene, RES_DIR, 'VISUAL')
    acoustic_xml = export(scene, RES_DIR, 'ACOUSTIC')

    mi.set_variant(VISUAL_VARIANT)
    image = render_visual(visual_xml, VISUAL_SPP)
    mi.Bitmap(image).write(os.path.join(REFERENCE_DIR, 'visual.exr'))

    mi.set_variant(ACOUSTIC_VARIANT)
    tape = render_acoustic(acoustic_xml, ACOUSTIC_SPP)
    np.save(os.path.join(REFERENCE_DIR, 'acoustic.npy'), tape)

    mi.set_variant(VISUAL_VARIANT)

    # The exports themselves are a build product, not a fixture: the tests
    # write their own into a temporary directory.
    import shutil

    for path in (visual_xml, acoustic_xml):
        os.unlink(path)
    shutil.rmtree(os.path.join(RES_DIR, 'meshes'), ignore_errors=True)

    print(f'Wrote references to {REFERENCE_DIR}')


def main():
    link = enable_addon()
    try:
        bpy.ops.wm.read_homefile(use_empty=True)
        scene = build_scene()

        os.makedirs(RES_DIR, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH, compress=False)
        print(f'Wrote {BLEND_PATH}')

        # Blender keeps the previous save as a .blend1 beside it, which is a
        # backup of a fixture rather than anything to commit.
        backup = BLEND_PATH + '1'
        if os.path.exists(backup):
            os.unlink(backup)

        write_references(scene)
    finally:
        os.unlink(link)


if __name__ == '__main__':
    main()
