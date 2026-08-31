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


def set_interpolation(axis):
    '''So is the interpolation axis.'''
    bpy.context.scene.mitsuba.acoustic_interpolation = axis


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
    assert bpy.context.scene.mitsuba.acoustic_interpolation == 'LOG'
    assert not hasattr(mat, 'acoustic_interpolation'), \
        'the axis is a scene setting, not a per-material one'


def test_linear_interpolation_uses_the_hertz_axis(mat):
    '''
    500 Hz and 2 kHz are one octave either side of 1 kHz, so the logarithmic
    axis puts 1 kHz halfway between the anchors while the linear one puts it a
    third of the way.
    '''
    set_interpolation('LINEAR')
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
    set_interpolation('LINEAR')
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
        (float(f), float(v))
        for f, v in (pair.split(':') for pair in node.get('value').split(','))
    ]


def export_scene(mat, tmp_path, **kwargs):
    '''Export a single cube carrying `mat` and return the parsed scene root.'''
    bpy.ops.mesh.primitive_cube_add()
    bpy.context.active_object.data.materials.append(mat)
    bpy.ops.object.camera_add()

    path = os.path.join(str(tmp_path), 'scene.xml')

    assert bpy.ops.export_scene.mitsuba(
        filepath=path, export_mode='ACOUSTIC', **kwargs
    ) == {'FINISHED'}

    return ET.parse(path).getroot()


def film_setting(root, kind, name):
    film = root.find(".//film[@type='tape']")
    assert film is not None, 'no tape film in the exported scene'
    return film.find(f"{kind}[@name='{name}']").get('value')


def test_export_writes_the_panel_values_verbatim(mat, tmp_path):
    '''
    Whatever the panel shows is what ships. The exporter used to re-run the
    interpolation itself, which could rewrite values it decided were unset.
    '''
    # one value per octave band, including two at the default, which the
    # exporter used to treat as unset
    expected = [0.1, 0.2, 0.3, 0.5, 0.5, 0.6, 0.7, 0.8, 0.9, 0.4]
    assert len(expected) == len(OCTAVES)

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

    assert [float(f) for f in written.split(',')] == list(expected)


def test_the_band_table_covers_31_5_hz():
    '''
    Room acoustics is judged below 63 Hz, so the table reaches down an octave
    further than the nine bands it started with.
    '''
    assert len(bands.OCTAVES) == 10
    assert len(bands.THIRD_OCTAVES) == 30

    assert bands.THIRD_OCTAVES[:3] == (25, 31.5, 40)

    # spelled out rather than sliced, since OCTAVES is derived from the
    # third-octave table and a slice would only compare it against itself
    assert bands.OCTAVES == (
        31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)


def test_the_31_5_hz_band_names_a_property_that_can_be_addressed(mat):
    '''A dot cannot appear in an RNA path, so the property is acoustic_abs_31_5.'''
    prop = bands.ABS_PROPS[bands.THIRD_OCTAVES.index(31.5)]

    assert prop == 'acoustic_abs_31_5'
    assert 'acoustic_scat_31_5' in bands.SCAT_PROPS

    mat.path_resolve(prop)


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

    def operator(self, idname, text='', **kwargs):
        self.drawn.append(('operator', idname, text))
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

    assert 'acoustic_specular_lobe_width' in props

    # the interpolation axis is a single scene setting, drawn once, in Output
    # properties; the material panel only points at it
    assert 'acoustic_interpolation' not in props

    # every band row carries its anchor checkbox
    for flag in ('acoustic_abs_band_set', 'acoustic_scat_band_set'):
        indices = sorted(e[2] for e in drawn if e[0] == 'prop' and e[1] == flag)
        assert indices == list(range(len(THIRD_OCTAVES)))

    # every family is headed by its name and a "Keep" column for the ticks
    labels = [entry[1] for entry in drawn if entry[0] == 'label']
    assert labels.count('Keep') == 2
    assert 'Absorption' in labels and 'Scattering' in labels

    operators = [entry[1] for entry in drawn if entry[0] == 'operator']
    for idname in (
        'acoustic.interpolate_abs', 'acoustic.reset_abs',
        'acoustic.interpolate_scat', 'acoustic.reset_scat',
        'acoustic.load_from_api', 'acoustic.apply_variant',
        'acoustic.reset_specular_lobe_width',
    ):
        assert idname in operators, f'{idname} is missing from the panel'


def test_panel_quotes_the_shared_default_rather_than_hardcoding_it(mat):
    drawn = draw_panel(mat)
    text = ' '.join(entry[-1] for entry in drawn if entry[0] in ('label', 'operator'))

    # the Reset buttons name the default, built from the constant
    assert str(DEFAULT) in text
    assert '0.25' not in text, 'scattering no longer has a default of its own'


def test_panel_help_text_is_wrapped_to_the_panel(mat):
    '''Blender labels do not wrap, so the help text is broken up by hand.'''
    labels = [entry[1] for entry in draw_panel(mat) if entry[0] == 'label']

    help_lines = [line for line in labels if line.startswith('Values are exported')]
    assert help_lines, 'the manual input help should be drawn'

    # wrapped, not one long line, and no line long enough to be clipped
    assert all(len(line) <= 80 for line in labels), max(labels, key=len)


def load_variant(mat, variant):
    '''Prime the material as if the database operator had just fetched this.'''
    mat['_acoustic_variants_cache'] = [variant]
    mat.acoustic_variant_enum = 'NONE'


def test_apply_variant_keeps_third_octave_data_at_full_resolution(mat):
    '''Third-octave measurements used to be averaged down to ten octave values.'''
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
    set_interpolation('LINEAR')
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


def test_time_bins_come_from_the_length_and_sampling_rate(mat, tmp_path):
    '''
    The film takes a bin count, but a response is described by how long it is
    and how finely it is sampled. time_bins was hardcoded to 2000 with no UI.
    '''
    scene = bpy.context.scene
    scene.mitsuba.acoustic_max_time = 3.0
    scene.mitsuba.acoustic_sampling_rate = 4000.0

    root = export_scene(mat, tmp_path)

    assert film_setting(root, 'integer', 'time_bins') == '12000'


def test_max_time_reaches_the_integrator(mat, tmp_path):
    '''max_time was hardcoded to 2.0 in the exporter.'''
    bpy.context.scene.mitsuba.acoustic_max_time = 5.0

    root = export_scene(mat, tmp_path)
    integrator = root.find(".//integrator[@type='acoustic_path']")

    assert integrator is not None
    assert float(integrator.find("float[@name='max_time']").get('value')) == 5.0


def test_film_settings_default_to_the_previous_export(mat, tmp_path):
    '''
    2 s at 1 kHz is the 2000 bins the film used to hardcode, so a scene that
    touches none of this exports exactly as it did before.
    '''
    scene = bpy.context.scene

    assert scene.mitsuba.acoustic_band_resolution == 'OCTAVE'
    assert scene.mitsuba.acoustic_max_time == 2.0
    assert scene.mitsuba.acoustic_sampling_rate == 1000.0

    root = export_scene(mat, tmp_path)
    assert film_setting(root, 'integer', 'time_bins') == '2000'


def test_film_settings_are_stored_on_the_scene(mat):
    '''
    They belong to the film, so they are saved in the .blend and shared by every
    material rather than set per export.
    '''
    operator_props = bpy.ops.export_scene.mitsuba.get_rna_type().properties

    # the per-material resolution toggle is gone
    assert not hasattr(bpy.data.materials[0], 'acoustic_third_octave')

    for name in ('acoustic_band_resolution', 'acoustic_max_time',
                 'acoustic_sampling_rate'):
        assert hasattr(bpy.context.scene.mitsuba, name), name
        assert name not in operator_props, name


def integrator_setting(root, kind, name):
    integrator = root.find(".//integrator[@type='acoustic_path']")
    assert integrator is not None, 'no acoustic integrator in the exported scene'
    node = integrator.find(f"{kind}[@name='{name}']")
    return node.get('value') if node is not None else None


def test_max_energy_loss_is_exported(mat, tmp_path):
    '''
    It was never written at all, so misuka fell back to its own default. The
    fallback path builds the integrator by hand and has to carry it too.
    '''
    root = export_scene(mat, tmp_path)

    assert float(integrator_setting(root, 'float', 'max_energy_loss')) == 300.0


def test_russian_roulette_is_not_offered_for_the_acoustic_integrator(mat, tmp_path):
    '''
    misuka's acoustic_path has no Russian Roulette and rejects rr_depth, so the
    panel used to show a field that was stripped again on the way out.
    '''
    settings = bpy.context.scene.mitsuba.available_integrators.acoustic_path

    assert not hasattr(settings, 'rr_depth')
    assert 'rr_depth' not in settings.to_dict()
    assert integrator_setting(export_scene(mat, tmp_path), 'integer', 'rr_depth') is None

    # the visual tracers still have it
    assert hasattr(bpy.context.scene.mitsuba.available_integrators.path, 'rr_depth')


def test_max_energy_loss_is_declared_for_the_integrator_panel():
    '''
    Declaring it in integrators.json is what generates the property, its row in
    the Integrator panel and its entry in to_dict().
    '''
    import json
    import os

    addon = os.path.dirname(bands.__file__)
    path = os.path.join(os.path.dirname(addon), 'engine', 'integrators.json')

    with open(path) as handle:
        declared = json.load(handle)['acoustic_path']['parameters']

    assert declared['max_energy_loss']['type'] == 'float'
    assert declared['max_energy_loss']['default'] == 300.0

    settings = bpy.context.scene.mitsuba.available_integrators.acoustic_path
    assert settings.max_energy_loss == 300.0
    assert settings.to_dict()['max_energy_loss'] == 300.0


def test_the_engine_defaults_to_the_acoustic_integrator():
    '''
    So its settings are in the Integrator panel the moment the engine is
    picked, rather than behind a dropdown change.
    '''
    assert bpy.context.scene.mitsuba.active_integrator == 'acoustic_path'


def test_visual_export_substitutes_a_visual_integrator(mat, tmp_path):
    '''
    The acoustic integrator cannot produce an image, so a visual export must
    not write it just because it is now the engine default.
    '''
    scene = bpy.context.scene
    scene.render.engine = 'MITSUBA'
    assert scene.mitsuba.active_integrator == 'acoustic_path'

    bpy.ops.mesh.primitive_cube_add()
    bpy.context.active_object.data.materials.append(mat)
    bpy.ops.object.camera_add()

    path = os.path.join(str(tmp_path), 'visual.xml')
    assert bpy.ops.export_scene.mitsuba(
        filepath=path, export_mode='VISUAL') == {'FINISHED'}

    root = ET.parse(path).getroot()

    assert root.find(".//integrator[@type='acoustic_path']") is None
    assert root.find(".//integrator[@type='path']") is not None
    assert root.find(".//film[@type='hdrfilm']") is not None


def test_export_mode_is_a_choice_of_two_scenes():
    '''
    The two modes swap out the integrator, sensor, film and materials, so the
    dialog names them rather than offering a checkbox to modify one.
    '''
    props = bpy.ops.export_scene.mitsuba.get_rna_type().properties

    assert 'acoustic_mode' not in props
    assert props['export_mode'].type == 'ENUM'
    assert [item.identifier for item in props['export_mode'].enum_items] == \
        ['ACOUSTIC', 'VISUAL']
    assert props['export_mode'].default == 'ACOUSTIC'

def test_wrap_text_fills_each_line(mat):
    '''
    Greedy wrapping against a measured width, so lines reach the panel edge
    instead of breaking at a guessed character count.
    '''
    # one unit per character, so the expected breaks are easy to read off
    measure = len

    assert io_module.wrap_text('aaa bbb ccc ddd', 7, measure) == ['aaa bbb', 'ccc ddd']
    assert io_module.wrap_text('aaa bbb ccc', 100, measure) == ['aaa bbb ccc']
    assert io_module.wrap_text('', 10, measure) == []

    # a word longer than the line still gets its own line rather than vanishing
    assert io_module.wrap_text('short enormouslylongword', 6, measure) == [
        'short', 'enormouslylongword'
    ]


def test_wrap_text_never_overflows_the_width(mat):
    '''
    Blender truncates a label that does not fit, with an ellipsis over the last
    word, so overflowing is worse than breaking a line early.
    '''
    text = ('Values are exported exactly as shown. Greyed bands are not '
            'exported; Band Resolution in Output properties picks which.')

    for width in (40, 55, 80, 120, 300):
        for line in io_module.wrap_text(text, width, len):
            # a single word wider than the line is the one unavoidable case
            assert len(line) <= width or ' ' not in line, (width, line)


def test_wrap_text_uses_the_full_width_available(mat):
    text = 'Values are exported exactly as shown. Greyed bands are not exported.'

    narrow = io_module.wrap_text(text, 30, len)
    wide = io_module.wrap_text(text, 60, len)

    assert len(wide) < len(narrow)
    # every line but the last is within one word of the limit
    for lines, width in ((narrow, 30), (wide, 60)):
        for line, following in zip(lines, lines[1:]):
            assert len(line) + 1 + len(following.split()[0]) > width, line


def test_every_acoustic_property_carries_a_description():
    '''
    Descriptions are the tooltips, and they are where the per-value guidance
    belongs rather than in the panel's help boxes.
    '''
    material_props = bpy.types.Material.bl_rna.properties
    scene_props = bpy.types.Scene.bl_rna.properties['mitsuba'].fixed_type.properties

    checked = 0

    for props, names in (
        (material_props, ABS_PROPS + SCAT_PROPS + (
            'acoustic_abs_band_set', 'acoustic_scat_band_set',
            'acoustic_specular_lobe_width')),
        (scene_props, (
            'acoustic_band_resolution', 'acoustic_interpolation',
            'acoustic_max_time', 'acoustic_sampling_rate')),
    ):
        for name in names:
            assert name in props, name
            assert props[name].description.strip(), f'{name} has no tooltip'
            checked += 1

    assert checked == 2 * len(bands.THIRD_OCTAVES) + 7


def test_the_manual_input_help_points_at_the_scene_settings(mat):
    '''
    Band Resolution and Interpolation are single scene settings, so the panel
    says where they are rather than drawing a second copy of them.
    '''
    text = ' '.join(entry[1] for entry in draw_panel(mat) if entry[0] == 'label')

    assert 'Band Resolution in Output properties' in text
    assert 'Interpolation in Output properties' in text


def test_the_database_instructions_are_wrapped(mat):
    '''They were five hand-broken numbered lines that clipped when narrowed.'''
    labels = [entry[1] for entry in draw_panel(mat) if entry[0] == 'label']

    assert any(line.startswith('Set an AcousticIndex API key') for line in labels)
    assert all(len(line) <= 80 for line in labels), max(labels, key=len)
