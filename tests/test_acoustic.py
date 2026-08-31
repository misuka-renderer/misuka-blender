'''
Tests for the acoustic material coefficients.

These run inside Blender with the addon enabled (see scripts/run_tests.py), so
they can register properties, drive the operators and export a real scene.
'''
import importlib
import os
import xml.etree.ElementTree as ET

import bpy
import pytest


io_module = importlib.import_module('misuka-blender.io')
bands = importlib.import_module('misuka-blender.io.acoustic_bands')

ABS_PROPS = bands.ABS_PROPS
SCAT_PROPS = bands.SCAT_PROPS
OCTAVES = bands.OCTAVES
OCTAVE_INDICES = bands.OCTAVE_INDICES
THIRD_OCTAVES = bands.THIRD_OCTAVES
DEFAULT = bands.ACOUSTIC_DEFAULT


@pytest.fixture
def mat():
    material = bpy.data.materials.new('acoustic_test')
    material.use_nodes = True
    return material


def abs_prop(freq):
    return ABS_PROPS[THIRD_OCTAVES.index(freq)]


def octave_values(material, props):
    return [getattr(material, props[i]) for i in OCTAVE_INDICES]


def set_resolution(resolution):
    '''Band resolution is a scene-wide film setting, not a material one.'''
    bpy.context.scene.mitsuba.acoustic_band_resolution = resolution


def run(operator, material):
    '''
    Call an acoustic operator against `material`.

    The panel supplies `context.material` from the properties editor; a headless
    test has no active material, so it has to be overridden explicitly.
    '''
    with bpy.context.temp_override(material=material):
        return operator()


def test_defaults_are_shared_and_nothing_is_marked_set(mat):
    '''Both families start at the same neutral value with no band claimed.'''
    for props in (ABS_PROPS, SCAT_PROPS):
        assert all(getattr(mat, p) == DEFAULT for p in props)

    assert not any(mat.acoustic_abs_band_set)
    assert not any(mat.acoustic_scat_band_set)
    assert bpy.context.scene.mitsuba.acoustic_band_resolution == 'OCTAVE'


def test_editing_a_value_marks_only_that_band(mat):
    setattr(mat, abs_prop(4000), 0.9)

    marked = [i for i, on in enumerate(mat.acoustic_abs_band_set) if on]
    assert marked == [THIRD_OCTAVES.index(4000)]
    assert not any(mat.acoustic_scat_band_set)


def test_interpolate_fills_between_and_clamps_outside(mat):
    setattr(mat, abs_prop(500), 0.2)
    setattr(mat, abs_prop(2000), 0.8)

    assert run(bpy.ops.acoustic.interpolate_abs, mat) == {'FINISHED'}

    values = dict(zip(OCTAVES, octave_values(mat, ABS_PROPS)))

    assert values[500] == pytest.approx(0.2)
    assert values[2000] == pytest.approx(0.8)
    # centred on the log-frequency axis the octave centres sit on
    assert values[1000] == pytest.approx(0.5, abs=1e-5)
    # outside the anchors the nearest anchor's value is held
    assert values[63] == pytest.approx(0.2)
    assert values[16000] == pytest.approx(0.8)


def test_interpolation_defaults_to_logarithmic(mat):
    assert mat.acoustic_interpolation == 'LOG'


def test_linear_interpolation_uses_the_hertz_axis(mat):
    '''
    500 Hz and 2 kHz are one octave either side of 1 kHz, so the logarithmic
    axis puts 1 kHz halfway between the anchors while the linear one puts it a
    third of the way.
    '''
    mat.acoustic_interpolation = 'LINEAR'
    setattr(mat, abs_prop(500), 0.2)
    setattr(mat, abs_prop(2000), 0.8)

    assert run(bpy.ops.acoustic.interpolate_abs, mat) == {'FINISHED'}

    values = dict(zip(OCTAVES, octave_values(mat, ABS_PROPS)))

    assert values[1000] == pytest.approx(0.2 + (0.8 - 0.2) / 3, abs=1e-5)
    # the anchors themselves and the clamped ends do not depend on the axis
    assert values[500] == pytest.approx(0.2)
    assert values[2000] == pytest.approx(0.8)
    assert values[63] == pytest.approx(0.2)
    assert values[16000] == pytest.approx(0.8)


def test_the_two_axes_disagree_only_between_the_anchors(mat):
    setattr(mat, abs_prop(250), 0.1)
    setattr(mat, abs_prop(8000), 0.9)

    assert run(bpy.ops.acoustic.interpolate_abs, mat) == {'FINISHED'}
    logarithmic = octave_values(mat, ABS_PROPS)

    assert run(bpy.ops.acoustic.reset_abs, mat) == {'FINISHED'}
    mat.acoustic_interpolation = 'LINEAR'
    setattr(mat, abs_prop(250), 0.1)
    setattr(mat, abs_prop(8000), 0.9)

    assert run(bpy.ops.acoustic.interpolate_abs, mat) == {'FINISHED'}
    linear = octave_values(mat, ABS_PROPS)

    lo = OCTAVES.index(250)
    hi = OCTAVES.index(8000)

    # linear in Hz leans everything toward the low anchor
    assert all(a > b for a, b in zip(logarithmic[lo + 1:hi], linear[lo + 1:hi]))
    assert logarithmic[:lo + 1] == pytest.approx(linear[:lo + 1])
    assert logarithmic[hi:] == pytest.approx(linear[hi:])


def test_interpolate_honours_an_anchor_sitting_on_the_default(mat):
    '''
    The old rule inferred anchors by comparing against the default, so a band
    deliberately left at 0.5 was silently ignored.
    '''
    setattr(mat, abs_prop(500), 0.9)
    setattr(mat, abs_prop(500), DEFAULT)
    setattr(mat, abs_prop(4000), 0.9)

    assert run(bpy.ops.acoustic.interpolate_abs, mat) == {'FINISHED'}

    values = dict(zip(OCTAVES, octave_values(mat, ABS_PROPS)))

    assert values[500] == pytest.approx(DEFAULT)
    assert values[4000] == pytest.approx(0.9)
    assert DEFAULT < values[1000] < 0.9


def test_interpolate_without_anchors_is_cancelled(mat):
    assert run(bpy.ops.acoustic.interpolate_abs, mat) == {'CANCELLED'}
    assert all(getattr(mat, p) == DEFAULT for p in ABS_PROPS)


def test_interpolate_leaves_the_other_family_alone(mat):
    setattr(mat, abs_prop(1000), 0.8)

    assert run(bpy.ops.acoustic.interpolate_abs, mat) == {'FINISHED'}
    assert all(getattr(mat, p) == DEFAULT for p in SCAT_PROPS)


def test_interpolate_fills_the_greyed_bands_too(mat):
    '''
    Octave resolution greys the other 18 bands but still fills them, so raising
    the resolution later gives a coherent curve rather than a comb of defaults.
    '''
    assert bpy.context.scene.mitsuba.acoustic_band_resolution == 'OCTAVE'

    setattr(mat, abs_prop(250), 0.2)
    setattr(mat, abs_prop(4000), 0.8)
    assert run(bpy.ops.acoustic.interpolate_abs, mat) == {'FINISHED'}

    for index, freq in enumerate(THIRD_OCTAVES):
        if index not in OCTAVE_INDICES and 250 < freq < 4000:
            assert getattr(mat, ABS_PROPS[index]) != DEFAULT, f'{freq} Hz'


def test_third_octave_mode_interpolates_all_bands(mat):
    set_resolution('THIRD_OCTAVE')
    setattr(mat, abs_prop(100), 0.2)
    setattr(mat, abs_prop(10000), 0.8)

    assert run(bpy.ops.acoustic.interpolate_abs, mat) == {'FINISHED'}

    values = [getattr(mat, p) for p in ABS_PROPS]
    assert values[THIRD_OCTAVES.index(100)] == pytest.approx(0.2)
    assert values[THIRD_OCTAVES.index(10000)] == pytest.approx(0.8)
    # 1000 Hz is the log midpoint of the two anchors
    assert values[THIRD_OCTAVES.index(1000)] == pytest.approx(0.5, abs=1e-5)
    # strictly rising between the anchors means every band was filled, not
    # just the octave centres
    lo = THIRD_OCTAVES.index(100)
    hi = THIRD_OCTAVES.index(10000)
    ramp = values[lo:hi + 1]
    assert all(a < b for a, b in zip(ramp, ramp[1:])), ramp

    # outside the anchors the nearest anchor's value is held
    assert values[:lo] == pytest.approx([0.2] * lo)
    assert values[hi + 1:] == pytest.approx([0.8] * (len(THIRD_OCTAVES) - hi - 1))


def test_reset_restores_defaults_and_clears_marks(mat):
    set_resolution('THIRD_OCTAVE')
    setattr(mat, abs_prop(1000), 0.9)
    setattr(mat, abs_prop(50), 0.1)

    assert run(bpy.ops.acoustic.reset_abs, mat) == {'FINISHED'}

    assert all(getattr(mat, p) == DEFAULT for p in ABS_PROPS)
    assert not any(mat.acoustic_abs_band_set)
    # the scene's resolution is not a material setting for reset to undo
    assert bpy.context.scene.mitsuba.acoustic_band_resolution == 'THIRD_OCTAVE'


def test_operators_are_unavailable_without_a_material():
    '''Every operator dereferences context.material, so poll has to guard it.'''
    assert getattr(bpy.context, 'material', None) is None

    assert not bpy.ops.acoustic.reset_abs.poll()
    assert not bpy.ops.acoustic.reset_scat.poll()
    assert not bpy.ops.acoustic.interpolate_abs.poll()
    assert not bpy.ops.acoustic.interpolate_scat.poll()
    assert not bpy.ops.acoustic.apply_variant.poll()
    assert not bpy.ops.acoustic.load_from_api.poll()
    assert not bpy.ops.acoustic.reset_specular_lobe_width.poll()


def read_spectrum(bsdf, name):
    node = bsdf.find(f"spectrum[@name='{name}']")
    assert node is not None, f'no {name} spectrum in {ET.tostring(bsdf)}'
    return [
        (int(f), float(v))
        for f, v in (pair.split(':') for pair in node.get('value').split(','))
    ]


def export_scene(mat, tmp_path, **kwargs):
    '''Export a single cube carrying `mat` and return the parsed scene root.'''
    bpy.ops.mesh.primitive_cube_add()
    bpy.context.active_object.data.materials.append(mat)
    bpy.ops.object.camera_add()

    path = os.path.join(str(tmp_path), 'scene.xml')

    assert bpy.ops.export_scene.mitsuba(
        filepath=path, acoustic_mode=True, **kwargs
    ) == {'FINISHED'}

    return ET.parse(path).getroot()


def test_export_writes_the_panel_values_verbatim(mat, tmp_path):
    '''
    Whatever the panel shows is what ships. The exporter used to re-run the
    interpolation itself, which could rewrite values it decided were unset.
    '''
    expected = [0.1, 0.2, 0.3, 0.5, 0.5, 0.6, 0.7, 0.8, 0.9]

    for freq, value in zip(OCTAVES, expected):
        setattr(mat, abs_prop(freq), value)

    root = export_scene(mat, tmp_path)
    bsdf = root.find(".//bsdf[@type='acousticbsdf']")

    assert read_spectrum(bsdf, 'absorption') == list(zip(OCTAVES, expected))
    assert read_spectrum(bsdf, 'scattering') == [(f, DEFAULT) for f in OCTAVES]


def test_export_uses_the_third_octave_table_when_enabled(mat, tmp_path):
    set_resolution('THIRD_OCTAVE')

    root = export_scene(mat, tmp_path)
    bsdf = root.find(".//bsdf[@type='acousticbsdf']")

    assert [f for f, _ in read_spectrum(bsdf, 'absorption')] == list(THIRD_OCTAVES)


@pytest.mark.parametrize('resolution, expected', [
    ('OCTAVE', OCTAVES),
    ('THIRD_OCTAVE', THIRD_OCTAVES),
])
def test_film_frequencies_follow_the_band_resolution(mat, tmp_path, resolution, expected):
    '''The tape film used to be pinned to a single 500 Hz band.'''
    set_resolution(resolution)
    root = export_scene(mat, tmp_path)

    film = root.find(".//film[@type='tape']")
    written = film.find("string[@name='frequencies']").get('value')

    assert [int(f) for f in written.split(',')] == list(expected)


class StubLayout:
    '''
    Minimal stand-in for Blender's UILayout.

    Panels cannot be drawn in background mode, so the draw code is exercised
    against this instead. Every prop() resolves the property for real, which is
    what catches a mistyped name or an out-of-range band index.
    '''

    def __init__(self, drawn):
        self.drawn = drawn
        self.enabled = True
        self.alert = False
        self.scale_y = 1.0
        self.operator_context = 'EXEC_DEFAULT'

    def column(self, **kwargs):
        return StubLayout(self.drawn)

    row = box = column

    def separator(self, **kwargs):
        pass

    def label(self, text='', **kwargs):
        self.drawn.append(('label', text))

    def operator(self, idname, **kwargs):
        self.drawn.append(('operator', idname))
        return StubLayout(self.drawn)

    def prop(self, data, name, index=-1, **kwargs):
        value = getattr(data, name)
        if index >= 0:
            value = value[index]
        self.drawn.append(('prop', name, index))


class StubContext:
    '''Just enough context for the panel's draw().'''

    def __init__(self, material):
        self.material = material
        self.scene = bpy.context.scene


class PanelStub:
    '''
    Borrows the panel's draw methods without being a bpy_struct.

    Panel subclasses cannot be instantiated from Python, so the methods are
    lifted onto a plain class that supplies the one attribute they touch.
    '''

    draw = io_module.ACOUSTIC_PT_material.draw
    draw_bands = io_module.ACOUSTIC_PT_material.draw_bands

    def __init__(self, drawn):
        self.layout = StubLayout(drawn)


def draw_panel(mat):
    drawn = []
    PanelStub(drawn).draw(StubContext(mat))
    return drawn


@pytest.mark.parametrize('resolution', ['OCTAVE', 'THIRD_OCTAVE'])
def test_panel_draws_every_band(mat, resolution):
    set_resolution(resolution)

    drawn = draw_panel(mat)

    props = [entry[1] for entry in drawn if entry[0] == 'prop']

    for name in ABS_PROPS + SCAT_PROPS:
        assert name in props, f'{name} is missing from the panel'

    assert 'acoustic_interpolation' in props
    assert 'acoustic_specular_lobe_width' in props

    # every band row carries its anchor checkbox
    for flag in ('acoustic_abs_band_set', 'acoustic_scat_band_set'):
        indices = sorted(e[2] for e in drawn if e[0] == 'prop' and e[1] == flag)
        assert indices == list(range(len(THIRD_OCTAVES)))

    operators = [entry[1] for entry in drawn if entry[0] == 'operator']
    for idname in (
        'acoustic.interpolate_abs', 'acoustic.reset_abs',
        'acoustic.interpolate_scat', 'acoustic.reset_scat',
        'acoustic.load_from_api', 'acoustic.apply_variant',
        'acoustic.reset_specular_lobe_width',
    ):
        assert idname in operators, f'{idname} is missing from the panel'


def test_panel_labels_mention_the_shared_default(mat):
    text = ' '.join(entry[1] for entry in draw_panel(mat) if entry[0] == 'label')

    # the one number the help text has to explain, quoted from the constant
    assert str(DEFAULT) in text
    assert '0.25' not in text, 'scattering no longer has a default of its own'


def load_variant(mat, variant):
    '''Prime the material as if the database operator had just fetched this.'''
    mat['_acoustic_variants_cache'] = [variant]
    mat.acoustic_variant_enum = 'NONE'


def test_apply_variant_keeps_third_octave_data_at_full_resolution(mat):
    '''Third-octave measurements used to be averaged down to nine octave values.'''
    measured = {str(f): 0.1 + 0.01 * i for i, f in enumerate(THIRD_OCTAVES)}
    load_variant(mat, {'_type': 'absorption', 'alpha_s_third_octave': measured})

    assert run(bpy.ops.acoustic.apply_variant, mat) == {'FINISHED'}

    assert all(mat.acoustic_abs_band_set), 'every measured band should be marked'

    for index, freq in enumerate(THIRD_OCTAVES):
        assert getattr(mat, ABS_PROPS[index]) == pytest.approx(measured[str(freq)])


def test_apply_variant_marks_only_the_measured_bands(mat):
    '''Sparse data is filled in, but only the real measurements are marked.'''
    load_variant(mat, {
        '_type': 'absorption',
        'alpha_s_octave': {'250': 0.2, '1000': 0.6, '4000': 0.9},
    })

    assert run(bpy.ops.acoustic.apply_variant, mat) == {'FINISHED'}

    marked = {THIRD_OCTAVES[i] for i, on in enumerate(mat.acoustic_abs_band_set) if on}
    assert marked == {250, 1000, 4000}

    values = dict(zip(OCTAVES, octave_values(mat, ABS_PROPS)))
    assert values[250] == pytest.approx(0.2)
    assert values[4000] == pytest.approx(0.9)
    # the gaps are filled rather than left at the default
    assert 0.2 < values[500] < 0.6


def test_apply_variant_reads_scattering_octave_data(mat):
    '''
    This branch used to index a JSON dict with int keys and raise KeyError, so
    any scattering variant without third-octave data crashed.
    '''
    load_variant(mat, {
        '_type': 'scattering',
        'scatter_octave': {'500': 0.3, '2000': 0.7},
    })

    assert run(bpy.ops.acoustic.apply_variant, mat) == {'FINISHED'}

    values = dict(zip(OCTAVES, octave_values(mat, SCAT_PROPS)))
    assert values[500] == pytest.approx(0.3)
    assert values[2000] == pytest.approx(0.7)
    assert all(getattr(mat, p) == DEFAULT for p in ABS_PROPS)


def test_apply_variant_fills_gaps_on_the_chosen_axis(mat):
    '''Sparse database data is filled in the same way manual input is.'''
    mat.acoustic_interpolation = 'LINEAR'
    load_variant(mat, {
        '_type': 'absorption',
        'alpha_s_octave': {'500': 0.2, '2000': 0.8},
    })

    assert run(bpy.ops.acoustic.apply_variant, mat) == {'FINISHED'}

    values = dict(zip(OCTAVES, octave_values(mat, ABS_PROPS)))
    assert values[1000] == pytest.approx(0.2 + (0.8 - 0.2) / 3, abs=1e-5)


def test_apply_variant_snaps_off_nominal_frequencies(mat):
    '''Measured centres are not always the ISO 266 preferred ones.'''
    load_variant(mat, {
        '_type': 'absorption',
        'alpha_s_third_octave': {'3200': 0.4, '6250': 0.6},
    })

    assert run(bpy.ops.acoustic.apply_variant, mat) == {'FINISHED'}

    marked = {THIRD_OCTAVES[i] for i, on in enumerate(mat.acoustic_abs_band_set) if on}
    assert marked == {3150, 6300}


def test_apply_variant_without_usable_data_is_rejected(mat):
    load_variant(mat, {'_type': 'absorption'})

    # reporting ERROR surfaces as a RuntimeError through the Python API
    with pytest.raises(RuntimeError, match='No absorption data'):
        run(bpy.ops.acoustic.apply_variant, mat)

    assert all(getattr(mat, p) == DEFAULT for p in ABS_PROPS)


def test_time_bins_follow_the_scene_setting(mat, tmp_path):
    '''time_bins used to be a hardcoded 2000 with no UI.'''
    bpy.context.scene.mitsuba.acoustic_time_bins = 4096

    root = export_scene(mat, tmp_path)
    film = root.find(".//film[@type='tape']")

    assert film.find("integer[@name='time_bins']").get('value') == '4096'


def test_the_band_resolution_is_stored_on_the_scene(mat):
    '''
    It belongs to the film, so it is saved in the .blend and shared by every
    material rather than being set per material or per export.
    '''
    scene = bpy.context.scene

    assert scene.mitsuba.acoustic_band_resolution == 'OCTAVE'
    assert not hasattr(mat, 'acoustic_third_octave')
    assert 'acoustic_band_resolution' not in bpy.ops.export_scene.mitsuba.get_rna_type().properties
