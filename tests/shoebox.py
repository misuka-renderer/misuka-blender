'''
The shoebox fixture: what is in it, and how it is rendered and measured.

`scripts/make_test_blend.py` builds the scene from this and records the
references; `tests/test_pipeline.py` opens the saved file and checks its renders
against them. Both go through the code here, so a reference and the test that
reads it can never disagree about how a number was computed.

This module deliberately sits outside the `fixtures` package, so it can be
imported without pulling in pytest. The generator runs inside Blender, where
pytest need not be installed.
'''
import os

# Both variants are pinned to the scalar backend rather than following the
# `cuda_ad_*, metal_ad_*, llvm_ad_*` order the tutorial uses. Which backend a
# machine happens to offer would otherwise decide what a render produces, and a
# reference recorded on one backend says nothing on another.
VISUAL_VARIANT = 'scalar_rgb'
ACOUSTIC_VARIANT = 'scalar_acoustic'

######################
##   The scene      ##
######################

ROOM_SIZE = 8.0

# Two emitters at the *same* Power, on purpose. Two emitters at one level export
# identical radiance, and misuka merges identical plugins unless `load_file` is
# given `optimize=False`; they then share a parameter, so zeroing one silences
# both. Equal Power is what puts that trap in front of the tests. The two stay
# distinguishable through where they are rather than how loud they are, which is
# the harder thing for a broken selection to fake.
EMITTER_POWER = 100.0
EMITTER_RADIUS = 0.3
SOURCE_POSITIONS = ((-2.5, -2.5, 0.0), (2.5, 2.5, 0.0))

RECEIVER_POSITIONS = ((-1.0, 2.0, -1.0), (2.0, -1.0, 1.0))

# Absorption and scattering per octave band, 31.5 Hz to 16 kHz. The two
# surfaces differ so the export has two distinct bsdfs to keep apart, and
# neither is the 0.5 default, so a material that failed to survive the save
# reads as obviously wrong rather than plausibly right.
WALL_COLOR = (0.55, 0.60, 0.72)
FLOOR_COLOR = (0.45, 0.32, 0.20)

WALL_BANDS = {
    'absorption': (0.10, 0.12, 0.14, 0.18, 0.22, 0.28, 0.34, 0.40, 0.46, 0.52),
    'scattering': (0.05, 0.08, 0.11, 0.15, 0.20, 0.26, 0.33, 0.41, 0.50, 0.60),
}
FLOOR_BANDS = {
    'absorption': (0.02, 0.03, 0.04, 0.06, 0.08, 0.11, 0.15, 0.20, 0.26, 0.33),
    'scattering': (0.30, 0.32, 0.35, 0.39, 0.44, 0.50, 0.57, 0.65, 0.74, 0.84),
}

ACOUSTIC_MAX_TIME = 0.5
SAMPLING_RATE = 1000.0
RESOLUTION = (64, 48)

######################
##  Render budget   ##
######################

# Sample counts and tolerance are one decision, not two: the tolerance is what
# the sample count can hold, and the sample count is what the runtime allows.
# See scripts/make_test_blend.py for how to re-derive them.
VISUAL_SPP = 64
ACOUSTIC_SPP = 4096

# Relative agreement required between a render and its reference.
#
# The references are recorded on one machine and compared on every other, and
# the scalar backend is not bit-identical across platforms even at a fixed
# seed: the same seed consumes the sample sequence slightly differently. What
# that costs was measured rather than guessed, against a macOS reference:
#
#     Windows, Blender 5.2          1.15%  (energy)
#     Linux, Blender 3.6/4.2/4.5    1.20%  (energy)
#     Linux, Blender 5.2            1.20%  (energy)
#
# Only per-band energy drifts that far; arrival and centroid held inside 1%
# everywhere. 2% clears the worst of it with room to spare, and is still far
# below what an actual regression moves - a wrong level, band or material
# changes these by tens of percent.
#
# Rerun scripts/audit_test_faults.py on a platform to re-measure.
TOLERANCE = 0.02

# Arrival is quantized to time bins, so a relative tolerance on it is really a
# tolerance of a fraction of a bin, and a single bin of drift would fail. One
# bin is the smallest difference that means anything.
ABSOLUTE_TOLERANCES = {'arrival': 1.0 / SAMPLING_RATE}


def set_base_color(material, color):
    '''Set a material's Principled base color, which is what a visual export writes.'''
    principled = material.node_tree.nodes['Principled BSDF']
    principled.inputs['Base Color'].default_value = (*color, 1.0)


def set_bands(material, bands):
    '''Write one octave-band table onto a material's acoustic panel.'''
    import importlib

    acoustic_bands = importlib.import_module('misuka-blender.io.acoustic_bands')

    for quantity, props in (('absorption', acoustic_bands.ABS_PROPS),
                            ('scattering', acoustic_bands.SCAT_PROPS)):
        values = bands[quantity]
        assert len(values) == len(acoustic_bands.OCTAVE_INDICES)
        for index, value in zip(acoustic_bands.OCTAVE_INDICES, values):
            setattr(material, props[index], value)


def read_band_table(material):
    '''Read back what set_bands wrote, in the same shape.'''
    import importlib

    acoustic_bands = importlib.import_module('misuka-blender.io.acoustic_bands')
    indices = acoustic_bands.OCTAVE_INDICES

    return {
        'absorption': tuple(
            acoustic_bands.read_bands(material, acoustic_bands.ABS_PROPS, indices)),
        'scattering': tuple(
            acoustic_bands.read_bands(material, acoustic_bands.SCAT_PROPS, indices)),
    }


######################
##  Export & render ##
######################

def export(scene, out_dir, export_mode):
    '''Export `scene` and return the path written.'''
    import bpy

    path = os.path.join(str(out_dir), f'shoebox_{export_mode.lower()}.xml')

    with bpy.context.temp_override(scene=scene):
        result = bpy.ops.export_scene.mitsuba(
            filepath=path, export_mode=export_mode, ignore_background=True,
            allow_multiple_emitters=True)

    assert result == {'FINISHED'}, f'{export_mode} export failed: {result}'
    return path


def render_visual(xml_path, spp):
    '''Render the visual scene and return its pixels.'''
    import misuka as mi
    import numpy as np

    scene = mi.load_file(xml_path)
    return np.array(mi.render(scene, spp=spp, seed=0))[:, :, :3]


def render_acoustic(xml_path, spp, sensor=0, scene=None):
    '''
    Render one receiver's energy-time curve, shaped (bands, time bins).

    `scene` renders an already-loaded scene, which is what the emitter
    selection test needs after it has silenced the other emitters.
    '''
    import misuka as mi
    import numpy as np

    if scene is None:
        scene = mi.load_file(xml_path)

    tape = mi.render(scene, spp=spp, seed=0, sensor=sensor)
    return np.array(tape)[..., 0].T


######################
##   Aggregates     ##
######################

# The tests do not compare renders element by element. misuka is free to
# distribute samples differently without being wrong, and the sample sequence
# is not identical across platforms even at a fixed seed. These are quantities
# that average over many samples, so they survive that, and each one fails for
# a different reason.

def acoustic_aggregates(tape, sampling_rate=SAMPLING_RATE):
    '''
    Per-band energy, first arrival and decay centroid.

    Energy catches a wrong emitter level or wrong absorption. First arrival
    catches an emitter or receiver that moved, or geometry at the wrong scale.
    The centroid catches absorption and room size, which shift the decay
    without necessarily shifting its total.
    '''
    import numpy as np

    tape = np.asarray(tape, dtype=np.float64)
    times = np.arange(tape.shape[1]) / sampling_rate

    energy = tape.sum(axis=1)

    # First arrival: the first bin holding a hundredth of the band's peak.
    # A fixed absolute threshold would depend on the emitter's level.
    peaks = tape.max(axis=1)
    arrival = np.full(tape.shape[0], np.nan)
    for band in range(tape.shape[0]):
        if peaks[band] <= 0.0:
            continue
        above = np.flatnonzero(tape[band] >= 0.01 * peaks[band])
        if above.size:
            arrival[band] = times[above[0]]

    with np.errstate(invalid='ignore', divide='ignore'):
        centroid = (tape * times).sum(axis=1) / energy

    return {'energy': energy, 'arrival': arrival, 'centroid': centroid}


def visual_aggregates(image, blocks=(6, 8)):
    '''
    Per-channel mean, plus a coarse block average.

    The channel means catch a wrong emitter level, material color or exposure.
    The block average catches a camera or geometry error that moves the image
    around without changing how bright it is overall.
    '''
    import numpy as np

    image = np.asarray(image, dtype=np.float64)
    rows, columns = blocks
    height, width = image.shape[:2]
    assert height % rows == 0 and width % columns == 0, \
        f'{height}x{width} does not divide into {rows}x{columns} blocks'

    reshaped = image.reshape(rows, height // rows, columns, width // columns, 3)

    return {
        'channel_mean': image.mean(axis=(0, 1)),
        'blocks': reshaped.mean(axis=(1, 3)),
    }


def assert_close(actual, expected, tolerance=TOLERANCE, label=''):
    '''
    Compare two aggregate tables within a relative tolerance.

    Scaled by the expected values' own magnitude rather than element by
    element, so a band that is near zero in both does not fail on its own noise.

    Every metric is checked before anything is raised. Stopping at the first
    one hides how close the others came, and that margin is what says whether
    the tolerance is right.
    '''
    import numpy as np

    problems = []

    for key in expected:
        got = np.asarray(actual[key], dtype=np.float64)
        want = np.asarray(expected[key], dtype=np.float64)

        assert got.shape == want.shape, \
            f'{label}{key}: shape {got.shape}, reference {want.shape}'

        finite = np.isfinite(want)
        assert np.array_equal(finite, np.isfinite(got)), \
            f'{label}{key}: differs from the reference in which values exist'

        scale = np.abs(want[finite]).max()
        if scale == 0.0:
            continue

        allowed = ABSOLUTE_TOLERANCES.get(key, 0.0) + tolerance * scale
        worst = np.abs(got[finite] - want[finite]).max()
        if worst > allowed:
            problems.append(
                f'{label}{key}: worst difference {worst:.6g} exceeds '
                f'{allowed:.6g} ({worst / scale:.2%} of {scale:.6g}, '
                f'tolerance {tolerance:.0%})')

    assert not problems, '; '.join(problems)
