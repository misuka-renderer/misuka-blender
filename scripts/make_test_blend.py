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
    if not prefs.is_misuka_initialized:
        raise RuntimeError(
            'misuka did not initialize. Install it into this Blender\'s Python.')

    return link


def build_scene():
    """
    Blender's default startup scene, turned into a room with an object in it.

    The default cube stays where it is and becomes the blue object. A second
    cube scaled around it becomes the red room, which is what
    docs/tutorials/shoebox-room teaches.

    Two emitters and two receivers, because one of anything cannot catch an
    exporter that writes only the first, and two emitters at equal Power are
    what make the merge trap reachable. All four sit inside the room and clear
    of the cube, and both cameras look at the cube so the blue object and the
    red room behind it are both in frame.
    """
    from mathutils import Vector

    from shoebox import (
        ACOUSTIC_MAX_TIME, CAMERA_TARGET, CUBE_BANDS, CUBE_COLOR,
        DEFAULT_CUBE_SIZE, EMITTER_POWER, EMITTER_RADIUS, RECEIVER_POSITIONS,
        RESOLUTION, ROOM_BANDS, ROOM_COLOR, ROOM_SCALE, SAMPLING_RATE,
        SOURCE_POSITIONS, set_bands, set_base_color)

    scene = bpy.context.scene
    scene.render.engine = 'MISUKA'
    scene.render.resolution_x, scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = 100

    scene.misuka.acoustic_band_resolution = 'OCTAVE'
    scene.misuka.acoustic_max_time = ACOUSTIC_MAX_TIME
    scene.misuka.acoustic_sampling_rate = SAMPLING_RATE

    # The object. Blender's default cube, at the origin, in blue.
    bpy.ops.mesh.primitive_cube_add(size=DEFAULT_CUBE_SIZE)
    cube = bpy.context.active_object
    cube.name = 'Cube'
    cube_material = bpy.data.materials.new('CubeSurface')
    cube_material.use_nodes = True
    set_base_color(cube_material, CUBE_COLOR)
    set_bands(cube_material, CUBE_BANDS)
    cube.data.materials.append(cube_material)

    # The room. The same cube scaled by 10, so it encloses everything else.
    # Its normals point outwards, which does not matter: an acousticbsdf is
    # two-sided and the visual render sees the inside faces.
    bpy.ops.mesh.primitive_cube_add(size=DEFAULT_CUBE_SIZE)
    room = bpy.context.active_object
    room.name = 'Room'
    room.scale = (ROOM_SCALE,) * 3
    room_material = bpy.data.materials.new('RoomSurface')
    room_material.use_nodes = True
    set_base_color(room_material, ROOM_COLOR)
    set_bands(room_material, ROOM_BANDS)
    room.data.materials.append(room_material)

    for index, position in enumerate(SOURCE_POSITIONS):
        bpy.ops.object.light_add(type='POINT', location=position)
        light = bpy.context.active_object
        light.name = 'Light' if index == 0 else f'Light_{index}'
        light.data.energy = EMITTER_POWER
        light.data.shadow_soft_size = EMITTER_RADIUS

    for index, position in enumerate(RECEIVER_POSITIONS):
        # A camera looks along its own -Z, so aim that at the cube.
        direction = Vector(CAMERA_TARGET) - Vector(position)
        rotation = direction.to_track_quat('-Z', 'Y').to_euler()
        bpy.ops.object.camera_add(location=position, rotation=rotation)
        receiver = bpy.context.active_object
        receiver.name = 'Camera' if index == 0 else f'Camera_{index}'
        # A fixed seed is what makes a render repeatable, and a repeatable
        # render is what makes a stored reference mean anything.
        settings = receiver.data.misuka
        getattr(settings.acoustic_samplers, settings.acoustic_sampler).seed = 0
        getattr(settings.visual_samplers, settings.visual_sampler).seed = 0

    # Sensor 0, so the reference image is the default startup view.
    scene.camera = bpy.data.objects['Camera']

    return scene


def write_references(scene):
    import numpy as np

    from shoebox import (
        ACOUSTIC_SPP, VISUAL_SPP, export, render_acoustic, render_visual,
        run_worker)

    os.makedirs(REFERENCE_DIR, exist_ok=True)

    visual_xml = export(scene, RES_DIR, 'VISUAL')
    acoustic_xml = export(scene, RES_DIR, 'ACOUSTIC')

    # Rendering and writing the .exr both need misuka, which runs outside
    # Blender for the same reason the tests do. See tests/misuka_worker.py.
    image = render_visual(visual_xml, VISUAL_SPP, REFERENCE_DIR)
    run_worker('write_exr', npy_path=os.path.join(REFERENCE_DIR, 'visual.npy'),
               out_path=os.path.join(REFERENCE_DIR, 'visual.exr'))
    os.unlink(os.path.join(REFERENCE_DIR, 'visual.npy'))

    tape = render_acoustic(acoustic_xml, ACOUSTIC_SPP, REFERENCE_DIR)
    np.save(os.path.join(REFERENCE_DIR, 'acoustic.npy'), tape)
    os.unlink(os.path.join(REFERENCE_DIR, 'acoustic-0-None.npy'))

    print(f'rendered {image.shape} image and {tape.shape} tape')

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
