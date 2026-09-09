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
import glob
import json
import os
import subprocess
import sys

# Both variants are pinned to the scalar backend rather than following the
# `cuda_ad_*, metal_ad_*, llvm_ad_*` order the tutorial uses. Which backend a
# machine happens to offer would otherwise decide what a render produces, and a
# reference recorded on one backend says nothing on another.
VISUAL_VARIANT = 'scalar_rgb'
ACOUSTIC_VARIANT = 'scalar_acoustic'

######################
##   The scene      ##
######################

# Blender's default startup scene, scaled into a room the way
# docs/tutorials/shoebox-room teaches: the default 2 m cube stays where it is
# and a second cube is scaled around it. That is a scene both renders say
# something about, a blue box seen against red walls, and a hard room with a
# soft object in it.
#
# The tutorial scales by 10, for a 20 m room. This one scales by 5, which is
# a compromise between two limits. Bigger, and a point receiver collects too
# few paths at a sample count the suite can afford, so the per-band aggregates
# come out as noise rather than as a measurement. Smaller, and there is nowhere
# to put a camera far enough from the cube to frame it and the room together.
ROOM_SCALE = 5.0
DEFAULT_CUBE_SIZE = 2.0
ROOM_SIZE = DEFAULT_CUBE_SIZE * ROOM_SCALE

# Two emitters at the *same* Power, on purpose. Two emitters at one level export
# identical radiance, and misuka merges identical plugins unless `load_file` is
# given `optimize=False`; they then share a parameter, so zeroing one silences
# both. Equal Power is what puts that trap in front of the tests. The two stay
# distinguishable through where they are rather than how loud they are, which is
# the harder thing for a broken selection to fake.
# Blender's startup light is at (4.08, 1.01, 5.90), which is outside an 8 m
# room, so the emitters sit inside it instead. Both are at the same Power on
# purpose: two emitters at one level export identical radiance, which is what
# makes the merge trap reachable.
# Blender's startup light is 1000 W, which blows out an enclosed room: the
# walls bounce light that the default scene lets escape.
EMITTER_POWER = 200.0
# Wider than Blender's 0.1 m default. The radius is the emitter sphere's size,
# and a bigger sphere is a bigger target, so fewer samples are needed before
# the per-band numbers mean anything. Power is held fixed whatever the radius,
# so this changes the variance and not the level.
EMITTER_RADIUS = 0.5
SOURCE_POSITIONS = ((2.5, 2.5, 1.5), (-2.5, -2.0, -1.2))

# Receivers, likewise inside the room and clear of the cube at the origin.
# Sensor 0 is where the reference image comes from.
#
# Both sit about 5.5 m from the cube. At the default 39.6 degree field of view
# that frame is about 4 m across, and the cube presents roughly its 2.8 m
# diagonal, so it covers something near half the picture with the red room
# around it. Closer and the cube fills the frame; further and there is no room
# left to stand in.
RECEIVER_POSITIONS = ((3.7, -3.7, 1.9), (-3.6, 3.4, -2.0))

# Both cameras look at the cube, so the blue object and the red room behind it
# are in frame and the image says something about both surfaces.
CAMERA_TARGET = (0.0, 0.0, 0.0)

# Absorption and scattering per octave band, 31.5 Hz to 16 kHz. The two
# surfaces differ so the export has two distinct bsdfs to keep apart, and
# neither is the 0.5 default, so a material that failed to survive the save
# reads as obviously wrong rather than plausibly right.
ROOM_COLOR = (0.72, 0.10, 0.08)
CUBE_COLOR = (0.08, 0.22, 0.75)

# A hard room with a soft object in it, so the object measurably shortens the
# decay rather than being acoustically invisible. Colors are visual only; an
# acoustic export reads these tables instead.
ROOM_BANDS = {
    'absorption': (0.02, 0.03, 0.04, 0.06, 0.08, 0.11, 0.15, 0.20, 0.26, 0.33),
    'scattering': (0.05, 0.08, 0.11, 0.15, 0.20, 0.26, 0.33, 0.41, 0.50, 0.60),
}
CUBE_BANDS = {
    'absorption': (0.20, 0.28, 0.38, 0.50, 0.62, 0.72, 0.80, 0.86, 0.90, 0.92),
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
ACOUSTIC_SPP = 16384

# Relative agreement required between a render and its reference.
#
# Two things have to fit inside it. The first is Monte Carlo noise: the same
# scene at two different seeds does not give the same answer, and how far apart
# they land is what the sample count buys. The second is that references are
# recorded on one machine and compared on every other, and the scalar backend
# is not bit-identical across platforms even at a fixed seed.
#
# Measured on this scene, seed 0 against seed 1:
#
#     spp   2048    energy 9.5%   centroid 6.4%   (0.09 s per render)
#     spp   4096    energy 5.0%   centroid 5.8%   (0.15 s)
#     spp  16384    energy 1.5%   centroid 2.2%   (0.60 s)
#
# 16384 is where the noise stops dominating, and four times that would cost
# more than the file's runtime budget is worth. 4% clears the noise at that
# sample count with room for the platform drift on top, and is still far below
# what an actual regression moves: a wrong level, band or material changes
# these by tens of percent.
#
# Rerun the seed comparison after changing the scene. A bigger room or a
# smaller emitter needs more samples for the same agreement.
TOLERANCE = 0.04

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
        result = bpy.ops.export_scene.misuka(
            filepath=path, export_mode=export_mode, ignore_background=True,
            allow_multiple_emitters=True)

    assert result == {'FINISHED'}, f'{export_mode} export failed: {result}'
    return path


def blender_python():
    '''
    The interpreter Blender ships, which is where the misuka work happens.

    Inside `blender.exe` on Windows, instantiating a misuka scene faults under
    Blender 3.6, 4.2 and 4.5. The bundled interpreter is a separate process and
    loads the system C++ runtime rather than the one in `blender.crt`, so it is
    unaffected on every version. `sys.prefix` points at it from inside Blender.
    '''
    pattern = os.path.join(sys.prefix, 'bin', 'python*')
    candidates = [p for p in sorted(glob.glob(pattern)) if os.path.isfile(p)]
    assert candidates, f'no interpreter under {pattern}'
    return candidates[0]


def run_worker(command, **payload):
    '''Run one `tests/misuka_worker.py` command and return what it reports.'''
    worker = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                          'misuka_worker.py')

    finished = subprocess.run(
        [blender_python(), worker, command, json.dumps(payload)],
        capture_output=True, text=True, errors='replace')

    marker = '__RESULT__'
    for line in finished.stdout.splitlines():
        if line.startswith(marker):
            return json.loads(line[len(marker):])

    raise AssertionError(
        f'misuka_worker {command} produced no result (exit {finished.returncode})\n'
        f'--- stdout ---\n{finished.stdout[-2000:]}\n'
        f'--- stderr ---\n{finished.stderr[-2000:]}')


def read_exr(path, out_dir):
    """Read a stored .exr reference, out of process."""
    import numpy as np

    out = os.path.join(str(out_dir), 'reference.npy')
    run_worker('read_exr', xml_path=path, variant=VISUAL_VARIANT, out_path=out)
    return np.load(out)


def inspect_scene(xml_path, variant, optimize=True):
    '''The scene's plugin names and counts, read out of process.'''
    return run_worker('inspect', xml_path=xml_path, variant=variant,
                      optimize=optimize)


def render_visual(xml_path, spp, out_dir):
    '''Render the visual scene out of process and return its pixels.'''
    import numpy as np

    out = os.path.join(str(out_dir), 'visual.npy')
    run_worker('render', xml_path=xml_path, variant=VISUAL_VARIANT,
               out_path=out, spp=spp)
    return np.load(out)


def render_acoustic(xml_path, spp, out_dir, sensor=0, isolate_emitter=None):
    '''
    Render one receiver's energy-time curve, shaped (bands, time bins).

    `isolate_emitter` silences every emitter but the one at that index, which
    has to happen in the same process as the render: a loaded scene cannot
    cross the boundary, so the worker does both.
    '''
    import numpy as np

    name = f'acoustic-{sensor}-{isolate_emitter}.npy'
    out = os.path.join(str(out_dir), name)
    run_worker('render', xml_path=xml_path, variant=ACOUSTIC_VARIANT,
               out_path=out, spp=spp, sensor=sensor,
               isolate_emitter=isolate_emitter, acoustic=True)
    return np.load(out)


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
