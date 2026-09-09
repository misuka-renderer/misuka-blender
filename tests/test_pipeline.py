'''
The whole path a user takes, from a saved file to a rendered result.

Everything else in this suite builds a scene in Python and reads the XML that
comes out. That says whether a number was written; it does not say whether the
file a user actually saved still carries the settings the add-on put on it, nor
whether misuka can render what we wrote.

So this opens `tests/res/shoebox.blend`, exports it both ways, loads both with
misuka and renders them, and compares the result against references recorded by
`scripts/make_test_blend.py`. The comparison is on aggregates rather than
pixels; `tests/shoebox.py` says why, and holds the scene's own constants.
'''
import os

import bpy
import numpy as np
import pytest

import shoebox


RES_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'res')
BLEND_PATH = os.path.join(RES_DIR, 'shoebox.blend')
REFERENCE_DIR = os.path.join(RES_DIR, 'references')


@pytest.fixture
def scene():
    '''The saved shoebox, opened the way a user would open it.'''
    bpy.ops.wm.open_mainfile(filepath=BLEND_PATH)
    return bpy.context.scene


def reference_tape():
    return np.load(os.path.join(REFERENCE_DIR, 'acoustic.npy'))


def reference_image(out_dir):
    '''The stored reference render. Reading an .exr needs misuka, so it goes
    through the worker like everything else that does.'''
    return shoebox.read_exr(os.path.join(REFERENCE_DIR, 'visual.exr'), out_dir)


#################################
##  What survives being saved  ##
#################################

def test_the_saved_scene_opens_with_its_misuka_settings(scene):
    '''
    The add-on's settings are custom properties, so they only come back if the
    add-on is registered when the file loads. A scene that opened without them
    would silently export as something else.
    '''
    assert scene.render.engine == 'MISUKA'
    assert (scene.render.resolution_x, scene.render.resolution_y) == shoebox.RESOLUTION

    assert scene.misuka.acoustic_band_resolution == 'OCTAVE'
    assert scene.misuka.acoustic_max_time == pytest.approx(shoebox.ACOUSTIC_MAX_TIME)
    assert scene.misuka.acoustic_sampling_rate == pytest.approx(shoebox.SAMPLING_RATE)


def test_both_surfaces_keep_their_own_coefficients(scene):
    '''
    Two materials with different tables, so a save that collapsed them onto one
    fails here rather than quietly halving the room's absorption. The room is
    the hard surface and the cube inside it is the absorbent one.
    '''
    for name, expected in (('RoomSurface', shoebox.ROOM_BANDS),
                           ('CubeSurface', shoebox.CUBE_BANDS)):
        table = shoebox.read_band_table(bpy.data.materials[name])
        for quantity, values in expected.items():
            assert table[quantity] == pytest.approx(values), f'{name} {quantity}'


def test_the_saved_scene_holds_two_emitters_and_two_receivers(scene):
    lights = [o for o in scene.objects if o.type == 'LIGHT']
    cameras = [o for o in scene.objects if o.type == 'CAMERA']

    assert len(lights) == 2
    assert len(cameras) == 2
    # Equal Power is what makes the merge trap below reachable.
    assert lights[0].data.energy == pytest.approx(lights[1].data.energy)


####################################
##  Exporting and loading it back ##
####################################

def test_exporting_several_emitters_keeps_them_separate(scene, tmp_path):
    '''
    Both emitters are at the same Power, so they export identical radiance and
    misuka merges them into a single parameter unless `load_file` is told not
    to. Zeroing that parameter to pick one emitter would then silence both.

    See docs/guide/exporting.md, "Exporting several emitters on purpose".
    '''
    path = shoebox.export(scene, tmp_path, 'ACOUSTIC')
    found = shoebox.inspect_scene(path, shoebox.ACOUSTIC_VARIANT, optimize=False)
    keys = found['radiance_keys']

    assert len(keys) == 2, (
        f'expected one radiance parameter per emitter, got {keys}. '
        'Two emitters at the same level merge without optimize=False.')


def test_a_saved_scene_renders_visually(scene, tmp_path):
    path = shoebox.export(scene, tmp_path, 'VISUAL')
    image = shoebox.render_visual(path, shoebox.VISUAL_SPP, tmp_path)

    assert np.isfinite(image).all()
    assert image.min() >= 0.0
    assert image.max() > 0.0, 'the visual render is black'

    shoebox.assert_close(
        shoebox.visual_aggregates(image),
        shoebox.visual_aggregates(reference_image(tmp_path)),
        label='visual ')


def test_a_saved_scene_renders_acoustically(scene, tmp_path):
    path = shoebox.export(scene, tmp_path, 'ACOUSTIC')
    found = shoebox.inspect_scene(path, shoebox.ACOUSTIC_VARIANT)

    assert found['integrator'].startswith('AcousticPathIntegrator')
    assert len(found['sensors']) == 2
    for sensor, film in zip(found['sensors'], found['films']):
        assert sensor.startswith('Microphone')
        assert film.startswith('Tape')

    tape = shoebox.render_acoustic(path, shoebox.ACOUSTIC_SPP, tmp_path)

    assert np.isfinite(tape).all()
    assert tape.min() >= 0.0
    assert tape.sum() > 0.0, 'the acoustic render carries no energy'

    shoebox.assert_close(
        shoebox.acoustic_aggregates(tape),
        shoebox.acoustic_aggregates(reference_tape()),
        label='acoustic ')


def test_the_render_repeats(scene, tmp_path):
    '''
    The seed is fixed in the saved file, so the same scene rendered twice has
    to give the same answer. Without that a stored reference means nothing.
    '''
    path = shoebox.export(scene, tmp_path, 'ACOUSTIC')

    first_dir = tmp_path / 'first'
    second_dir = tmp_path / 'second'
    first_dir.mkdir()
    second_dir.mkdir()

    first = shoebox.render_acoustic(path, shoebox.ACOUSTIC_SPP, first_dir)
    second = shoebox.render_acoustic(path, shoebox.ACOUSTIC_SPP, second_dir)

    assert np.array_equal(first, second)


#############################################
##  Picking one emitter, picking one receiver ##
#############################################

def test_each_emitter_can_be_rendered_on_its_own(scene, tmp_path):
    '''
    The workflow documented in docs/guide/exporting.md: export every emitter
    once, then silence all but one at render time.

    The two emitters sit at different corners of the room, so the curves differ
    in when energy arrives rather than in how much there is. That is the case a
    selection that quietly did nothing would otherwise pass.
    '''
    path = shoebox.export(scene, tmp_path, 'ACOUSTIC')

    assert len(shoebox.inspect_scene(
        path, shoebox.ACOUSTIC_VARIANT, optimize=False)['radiance_keys']) == 2

    # Silencing the others and rendering has to happen in one process: a loaded
    # scene cannot cross the boundary, so the worker does both.
    curves = [shoebox.render_acoustic(path, shoebox.ACOUSTIC_SPP, tmp_path,
                                      isolate_emitter=index)
              for index in (0, 1)]

    for index, curve in enumerate(curves):
        assert curve.sum() > 0.0, f'emitter {index} alone produced no energy'

    assert not np.array_equal(curves[0], curves[1]), \
        'both emitters gave the same curve, so the selection did nothing'


def test_each_receiver_can_be_rendered_on_its_own(scene, tmp_path):
    '''
    Receivers need no trick: a sensor index picks one.
    See docs/guide/exporting.md, "Multiple Receivers".
    '''
    path = shoebox.export(scene, tmp_path, 'ACOUSTIC')

    first = shoebox.render_acoustic(path, shoebox.ACOUSTIC_SPP, tmp_path, sensor=0)
    second = shoebox.render_acoustic(path, shoebox.ACOUSTIC_SPP, tmp_path, sensor=1)

    assert first.sum() > 0.0 and second.sum() > 0.0
    assert not np.array_equal(first, second), \
        'both receivers gave the same curve, so the sensor index did nothing'
