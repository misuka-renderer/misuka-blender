'''
Tests for the acoustic material coefficients.

These run inside Blender with the addon enabled (see scripts/run_tests.py), so
they can register properties, drive the operators and export a real scene.
'''
import importlib
import json
import os
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

import bpy
import numpy as np
import pytest


io_module = importlib.import_module('misuka-blender.io')
bands = importlib.import_module('misuka-blender.io.acoustic_bands')
engine_props = importlib.import_module('misuka-blender.engine.properties')
docs_module = importlib.import_module('misuka-blender.docs')

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


def test_defaults_are_shared_and_nothing_is_kept(mat):
    '''Both quantities start at the same neutral value with no band claimed.'''
    for props in (ABS_PROPS, SCAT_PROPS):
        assert all(getattr(mat, p) == DEFAULT for p in props)

    assert not any(mat.acoustic_abs_keep)
    assert not any(mat.acoustic_scat_keep)
    assert bpy.context.scene.mitsuba.acoustic_band_resolution == 'OCTAVE'


def test_editing_a_value_keeps_only_that_band(mat):
    setattr(mat, abs_prop(4000), 0.9)

    kept = [i for i, on in enumerate(mat.acoustic_abs_keep) if on]
    assert kept == [THIRD_OCTAVES.index(4000)]
    assert not any(mat.acoustic_scat_keep)


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


def test_interpolate_leaves_the_other_quantity_alone(mat):
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


def test_reset_restores_defaults_and_clears_keeps(mat):
    set_resolution('THIRD_OCTAVE')
    setattr(mat, abs_prop(1000), 0.9)
    setattr(mat, abs_prop(50), 0.1)

    assert run(bpy.ops.acoustic.reset_abs, mat) == {'FINISHED'}

    assert all(getattr(mat, p) == DEFAULT for p in ABS_PROPS)
    assert not any(mat.acoustic_abs_keep)
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


def add_point_light(power, radius):
    bpy.ops.object.light_add(type='POINT')
    light = bpy.context.active_object
    light.data.energy = power
    light.data.shadow_soft_size = radius
    return light


def export_scene(mat, tmp_path, export_mode='ACOUSTIC', **kwargs):
    '''
    Export a single cube carrying `mat` and return the parsed scene root.

    Either export mode needs the misuka engine, since that is where the
    settings it writes live, and an Acoustic one needs something to emit.
    Select the engine and add a point light unless the test set them up itself.
    '''
    if bpy.context.scene.render.engine != 'MITSUBA':
        bpy.context.scene.render.engine = 'MITSUBA'

    bpy.ops.mesh.primitive_cube_add()
    bpy.context.active_object.data.materials.append(mat)
    bpy.ops.object.camera_add()

    has_light = any(ob.type == 'LIGHT' for ob in bpy.data.objects)
    if export_mode == 'ACOUSTIC' and not has_light:
        add_point_light(100.0, 0.5)

    path = os.path.join(str(tmp_path), 'scene.xml')

    assert bpy.ops.export_scene.mitsuba(
        filepath=path, export_mode=export_mode, **kwargs
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


def scene_spp(root):
    '''
    Samples the sensor's sampler ends up with, one per frequency band. The
    XML writer hoists the sensor sample count into a `spp` default, so the
    sampler itself can carry a `$spp` reference instead of a number.
    '''
    sampler = root.find(".//sensor/sampler")
    assert sampler is not None, 'no sampler in the exported scene'

    value = sampler.find("integer[@name='sample_count']").get('value')
    if value.startswith('$'):
        value = root.find(f"default[@name='{value[1:]}']").get('value')

    return int(value)


def test_acoustic_export_defaults_to_262144_samples(mat, tmp_path):
    '''
    An acoustic run needs far more samples than an image, and the render
    engine's sample count used to leak into the acoustic scene.
    '''
    root = export_scene(mat, tmp_path)

    assert scene_spp(root) == 2 ** 18


def test_the_sample_count_setting_reaches_the_exported_scene(mat, tmp_path):
    bpy.context.scene.mitsuba.acoustic_sample_count = 64

    root = export_scene(mat, tmp_path)

    assert scene_spp(root) == 64


def source_sphere(root):
    shape = root.find(".//shape[@type='sphere']")
    assert shape is not None, 'no source sphere in the exported scene'

    radius = float(shape.find("float[@name='radius']").get('value'))
    emitter = shape.find("emitter[@type='area']")
    texture = emitter.find("texture[@name='radiance']")
    assert texture is not None, f'no radiance on {ET.tostring(emitter)}'
    radiance = float(texture.find("float[@name='value']").get('value'))

    return radius, radiance


@pytest.mark.parametrize('radius', [0.25, 0.5, 1.0])
def test_the_source_emits_the_lights_power_whatever_the_radius(
        mat, tmp_path, radius):
    '''
    Blender keeps a point light's Power fixed when you change its Radius. The
    acoustic source used to write the point intensity as a radiance, so its
    power grew with the radius squared.
    '''
    power = 100.0
    add_point_light(power, radius)

    exported_radius, radiance = source_sphere(export_scene(mat, tmp_path))

    assert exported_radius == pytest.approx(radius)

    # an area emitter on a sphere emits pi * area * radiance
    total = np.pi * 4 * np.pi * exported_radius ** 2 * radiance
    assert total == pytest.approx(power)


def test_a_zero_radius_source_falls_back_to_ten_centimeters(mat, tmp_path):
    add_point_light(100.0, 0.0)

    radius, radiance = source_sphere(export_scene(mat, tmp_path))

    assert radius == pytest.approx(0.1)
    assert np.pi * 4 * np.pi * radius ** 2 * radiance == pytest.approx(100.0)


def test_the_band_table_covers_31_5_hz(mat):
    '''
    Room acoustics is judged below 63 Hz, so the table reaches down an octave
    further than the nine bands it started with. A dot cannot appear in an RNA
    path, so 31.5 Hz becomes acoustic_abs_31_5.
    '''
    assert len(bands.OCTAVES) == 10
    assert len(bands.THIRD_OCTAVES) == 30

    assert bands.THIRD_OCTAVES[:3] == (25, 31.5, 40)

    # spelled out rather than sliced, since OCTAVES is derived from the
    # third-octave table and a slice would only compare it against itself
    assert bands.OCTAVES == (
        31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)

    prop = bands.ABS_PROPS[bands.THIRD_OCTAVES.index(31.5)]

    assert prop == 'acoustic_abs_31_5'
    assert 'acoustic_scat_31_5' in bands.SCAT_PROPS

    mat.path_resolve(prop)


class StubOperatorProps:
    '''
    Stand-in for what `UILayout.operator()` returns.

    Blender hands back the operator's properties so the caller can set them,
    which is how the HELP buttons carry their URL. Recording the assignment is
    what lets a test read that URL back.
    '''

    def __init__(self, drawn, idname):
        object.__setattr__(self, '_drawn', drawn)
        object.__setattr__(self, '_idname', idname)

    def __setattr__(self, name, value):
        self._drawn.append(('operator_prop', self._idname, name, value))


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

    # split(factor=...) is another way of asking for a nested layout, and a
    # stub layout has no widths to divide up.
    row = box = split = column

    def separator(self, **kwargs):
        pass

    def label(self, text='', icon='NONE', **kwargs):
        self.drawn.append(('label', text, icon))

    def operator(self, idname, text='', **kwargs):
        self.drawn.append(('operator', idname, text))
        return StubOperatorProps(self.drawn, idname)

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


ACOUSTIC_PANELS = (
    'ACOUSTIC_PT_material',
    'ACOUSTIC_PT_database',
    'ACOUSTIC_PT_coefficients',
    'ACOUSTIC_PT_specular',
)


def draw_panel(mat, only=None):
    '''
    Render the acoustic panels against the stub.

    Blender draws each subpanel separately and hides a collapsed one, so the
    stub does the same: it walks the panel classes and calls each draw.
    '''
    drawn = []

    for name in (only,) if only else ACOUSTIC_PANELS:
        panel = getattr(io_module, name)
        context = StubContext(mat)

        # The HELP buttons live in the header, so it has to be drawn too.
        # Blender right-aligns `draw_header_preset`, which is where they sit.
        if hasattr(panel, 'draw_header_preset'):
            header = type('Stub', (), {'draw_header_preset': panel.draw_header_preset})()
            header.layout = StubLayout(drawn)
            header.draw_header_preset(context)

        stub = type('Stub', (), {'draw': panel.draw})()
        stub.layout = StubLayout(drawn)
        stub.draw(context)

    return drawn


def test_the_sections_are_real_subpanels(mat):
    '''
    Blender nests panels itself, with fold state, drag handles and the right
    triangles, so none of that is hand-rolled here.
    '''
    parents = {name: getattr(io_module, name).bl_parent_id
               for name in ACOUSTIC_PANELS
               if hasattr(getattr(io_module, name), 'bl_parent_id')}

    assert parents == {
        'ACOUSTIC_PT_database': 'ACOUSTIC_PT_material',
        'ACOUSTIC_PT_coefficients': 'ACOUSTIC_PT_material',
        'ACOUSTIC_PT_specular': 'ACOUSTIC_PT_material',
    }


def test_the_sections_start_open(mat):
    '''
    Every section carries settings the user came for, so none of them is
    collapsed by default.
    '''
    for name in ACOUSTIC_PANELS:
        options = getattr(getattr(io_module, name), 'bl_options', set())
        assert 'DEFAULT_CLOSED' not in options, name


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
    for flag in ('acoustic_abs_keep', 'acoustic_scat_keep'):
        indices = sorted(e[2] for e in drawn if e[0] == 'prop' and e[1] == flag)
        assert indices == list(range(len(THIRD_OCTAVES)))

    # every quantity is headed by its name and a "Keep" column for the ticks
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
    # A label records ('label', text, icon) and an operator ('operator', idname,
    # text), so the text sits at a different index in each.
    text = ' '.join(entry[1] if entry[0] == 'label' else entry[2]
                    for entry in drawn if entry[0] in ('label', 'operator'))

    # the Reset buttons name the default, built from the constant
    assert str(DEFAULT) in text


def load_variant(mat, *variants, select=0):
    '''
    Prime the material as if the database operator had just fetched these.

    The dropdown builds its entries from `context.material`, so assigning to it
    needs the same override the operators do.
    '''
    mat['_acoustic_variants_cache'] = list(variants)

    with bpy.context.temp_override(material=mat):
        mat.acoustic_variant_enum = str(select)


def test_apply_variant_keeps_third_octave_data_at_full_resolution(mat):
    '''Third-octave measurements used to be averaged down to ten octave values.'''
    measured = {str(f): 0.1 + 0.01 * i for i, f in enumerate(THIRD_OCTAVES)}
    load_variant(mat, {'_type': 'absorption', 'alpha_s_third_octave': measured})

    assert run(bpy.ops.acoustic.apply_variant, mat) == {'FINISHED'}

    assert all(mat.acoustic_abs_keep), 'every measured band should be kept'

    for index, freq in enumerate(THIRD_OCTAVES):
        assert getattr(mat, ABS_PROPS[index]) == pytest.approx(measured[str(freq)])


def test_apply_variant_keeps_only_the_measured_bands(mat):
    '''Sparse data is filled in, but only the real measurements are kept.'''
    load_variant(mat, {
        '_type': 'absorption',
        'alpha_s_octave': {'250': 0.2, '1000': 0.6, '4000': 0.9},
    })

    assert run(bpy.ops.acoustic.apply_variant, mat) == {'FINISHED'}

    kept = {THIRD_OCTAVES[i] for i, on in enumerate(mat.acoustic_abs_keep) if on}
    assert kept == {250, 1000, 4000}

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

    kept = {THIRD_OCTAVES[i] for i, on in enumerate(mat.acoustic_abs_keep) if on}
    assert kept == {3150, 6300}


def test_apply_variant_uses_the_variant_the_dropdown_names(mat):
    '''
    The dropdown used to offer an "Auto Selection" that picked the most
    absorbent variant, so the applied numbers need not be the listed ones.
    '''
    load_variant(
        mat,
        {'_type': 'absorption', 'alpha_s_octave': {'1000': 0.9}},
        {'_type': 'absorption', 'alpha_s_octave': {'1000': 0.3}},
        select=1,
    )

    assert run(bpy.ops.acoustic.apply_variant, mat) == {'FINISHED'}

    values = dict(zip(OCTAVES, octave_values(mat, ABS_PROPS)))
    assert values[1000] == pytest.approx(0.3)


def test_variant_dropdown_offers_the_variants_and_nothing_picked(mat):
    '''
    Blender does not expose a dynamic enum's items to Python, so the entries
    are probed by what the property accepts.
    '''
    def accepts(value):
        try:
            with bpy.context.temp_override(material=mat):
                mat.acoustic_variant_enum = value
        except TypeError:
            return False
        return True

    load_variant(
        mat,
        {'_type': 'absorption', 'label': 'A'},
        {'_type': 'scattering', 'label': 'B'},
    )

    assert accepts('0') and accepts('1')
    assert not accepts('2')

    # the leading entry is "nothing picked", where the "Auto Selection" that
    # applied a variant of its own used to sit
    assert accepts(io_module.NO_VARIANT)
    assert io_module.select_variant(mat) is None


def test_apply_variant_needs_a_variant_to_be_picked(mat):
    '''A fresh database lookup leaves the dropdown on the "nothing picked" entry.'''
    load_variant(
        mat,
        {'_type': 'absorption', 'alpha_s_octave': {'1000': 0.9}},
        select=io_module.NO_VARIANT,
    )

    # reporting ERROR surfaces as a RuntimeError through the Python API
    with pytest.raises(RuntimeError, match='Select a variant'):
        run(bpy.ops.acoustic.apply_variant, mat)

    assert all(getattr(mat, p) == DEFAULT for p in ABS_PROPS)
    assert not any(mat.acoustic_abs_keep)


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

    for name in ('acoustic_band_resolution', 'acoustic_max_time',
                 'acoustic_sampling_rate', 'acoustic_sample_count'):
        assert hasattr(bpy.context.scene.mitsuba, name), name
        assert name not in operator_props, name


def draw_integrator_panel():
    '''Names of the properties the Integrator panel draws, in order.'''
    drawn = []
    panel = engine_props.MITSUBA_RENDER_PT_integrator
    stub = type('Stub', (), {'draw': panel.draw})()
    stub.layout = StubLayout(drawn)
    stub.draw(StubContext(None))

    return [name for kind, name, _ in drawn if kind == 'prop']


def test_the_sample_count_shows_only_for_the_acoustic_integrator():
    '''
    It is a sampler setting in Mitsuba, so it cannot come from
    integrators.json without being written into the integrator element. The
    panel draws it beside the settings it trades off against instead.
    '''
    settings = bpy.context.scene.mitsuba

    try:
        settings.active_integrator = 'acoustic_path'
        assert 'acoustic_sample_count' in draw_integrator_panel()

        settings.active_integrator = 'path'
        assert 'acoustic_sample_count' not in draw_integrator_panel()
    finally:
        settings.active_integrator = 'acoustic_path'


def test_a_sample_count_cannot_go_below_one():
    '''
    Mitsuba needs at least one ray. The JSON `min` used to reach Blender as a
    `soft_min`, which only stops the slider, so a typed or scripted zero got
    through.
    '''
    bpy.ops.object.camera_add()
    sampler = bpy.context.active_object.data.mitsuba.samplers.independent

    sampler.sample_count = 0

    assert sampler.sample_count == 1


def integrator_setting(root, kind, name):
    integrator = root.find(".//integrator[@type='acoustic_path']")
    assert integrator is not None, 'no acoustic integrator in the exported scene'
    node = integrator.find(f"{kind}[@name='{name}']")
    return node.get('value') if node is not None else None


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


def test_max_energy_loss_is_declared_and_exported(mat, tmp_path):
    '''
    Declaring it in integrators.json is what generates the property, its row in
    the Integrator panel and its entry in to_dict(). It was never written into
    the scene at all, so misuka fell back to its own default; the fallback path
    builds the integrator by hand and has to carry it too.
    '''
    addon = os.path.dirname(bands.__file__)
    path = os.path.join(os.path.dirname(addon), 'engine', 'integrators.json')

    with open(path) as handle:
        declared = json.load(handle)['acoustic_path']['parameters']

    assert declared['max_energy_loss']['type'] == 'float'
    assert declared['max_energy_loss']['default'] == 90.0

    settings = bpy.context.scene.mitsuba.available_integrators.acoustic_path
    assert settings.max_energy_loss == 90.0
    assert settings.to_dict()['max_energy_loss'] == 90.0

    root = export_scene(mat, tmp_path)

    assert float(integrator_setting(root, 'float', 'max_energy_loss')) == 90.0


def test_the_engine_defaults_to_the_acoustic_integrator():
    '''
    So its settings are in the Integrator panel the moment the engine is
    picked, rather than behind a dropdown change.
    '''
    assert bpy.context.scene.mitsuba.active_integrator == 'acoustic_path'


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

def test_wrap_text_fills_lines_without_overflowing(mat):
    """
    Greedy wrapping against a measured width, so lines reach the panel edge
    instead of breaking at a guessed character count. Blender truncates a label
    that does not fit, with an ellipsis over the last word, so overflowing is
    worse than breaking a line early.
    """
    # one unit per character, so the expected breaks are easy to read off
    measure = len

    assert io_module.wrap_text('aaa bbb ccc ddd', 7, measure) == ['aaa bbb', 'ccc ddd']
    assert io_module.wrap_text('aaa bbb ccc', 100, measure) == ['aaa bbb ccc']
    assert io_module.wrap_text('', 10, measure) == []

    # a word longer than the line still gets its own line rather than vanishing
    assert io_module.wrap_text('short enormouslylongword', 6, measure) == [
        'short', 'enormouslylongword'
    ]

    text = ('Values are exported exactly as shown. Greyed bands are not '
            'exported; Band Resolution in Output properties picks which.')

    for width in (30, 40, 55, 80, 120, 300):
        lines = io_module.wrap_text(text, width, measure)

        for line in lines:
            # a single word wider than the line is the one unavoidable case
            assert len(line) <= width or ' ' not in line, (width, line)

        # every line but the last is within one word of the limit
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
            'acoustic_abs_keep', 'acoustic_scat_keep',
            'acoustic_specular_lobe_width')),
        (scene_props, (
            'acoustic_band_resolution', 'acoustic_interpolation',
            'acoustic_max_time', 'acoustic_sampling_rate',
            'acoustic_sample_count')),
    ):
        for name in names:
            assert name in props, name
            assert props[name].description.strip(), f'{name} has no tooltip'
            checked += 1

    assert checked == 2 * len(bands.THIRD_OCTAVES) + 8


def test_every_section_links_to_its_documentation(mat):
    '''
    Each section explains itself through a HELP button rather than a block of
    panel-local prose, so the explanation can be longer than a panel fits.
    '''
    drawn = draw_panel(mat)

    urls = {value for kind, idname, name, value in
            (entry for entry in drawn if entry[0] == 'operator_prop')
            if idname == 'wm.url_open' and name == 'url'}

    assert urls == {
        docs_module.DOCS_URL + 'guide/acousticindex.html',
        docs_module.DOCS_URL + 'guide/acoustic-materials.html',
        docs_module.DOCS_URL + 'guide/acoustic-materials.html#specular-reflection',
    }

    # every link is absolute, so it resolves from Blender's own browser call
    assert all(url.startswith('https://') for url in urls)


@pytest.mark.parametrize('engine, export_mode, integrator, film', [
    ('MITSUBA', 'ACOUSTIC', 'acoustic_path', 'tape'),
    ('MITSUBA', 'VISUAL', 'path', 'hdrfilm'),
])
def test_the_export_mode_picks_the_integrator(
        mat, tmp_path, engine, export_mode, integrator, film):
    '''
    An acoustic export gets the acoustic integrator and an optical one gets a
    visual tracer, whatever the Integrator panel happens to be showing.
    '''
    bpy.context.scene.render.engine = engine

    root = export_scene(mat, tmp_path, export_mode=export_mode)

    assert root.find(f".//integrator[@type='{integrator}']") is not None
    assert root.find(f".//film[@type='{film}']") is not None

    unwanted = 'path' if integrator == 'acoustic_path' else 'acoustic_path'
    assert root.find(f".//integrator[@type='{unwanted}']") is None


def test_an_optical_export_still_honours_a_chosen_integrator(mat, tmp_path):
    '''
    Only acoustic_path is overridden. Picking a different visual integrator has
    to keep working, or the dropdown would be pointless.
    '''
    scene = bpy.context.scene
    scene.render.engine = 'MITSUBA'
    scene.mitsuba.active_integrator = 'direct'

    root = export_scene(mat, tmp_path, export_mode='VISUAL')

    assert root.find(".//integrator[@type='direct']") is not None


ACOUSTIC_OPERATORS = (
    'load_from_api',
    'apply_variant',
    'interpolate_abs',
    'interpolate_scat',
    'reset_abs',
    'reset_scat',
    'reset_specular_lobe_width',
)


def test_every_operator_has_a_tooltip():
    '''
    Blender reads bl_description, falling back to the class docstring. Python
    does not inherit __doc__, so documenting a base class left every subclass
    showing "(undocumented operator)".
    '''
    for name in ACOUSTIC_OPERATORS:
        description = getattr(bpy.ops.acoustic, name).get_rna_type().description

        assert description, name
        assert 'undocumented' not in description.lower(), (name, description)


def test_the_reset_tooltips_quote_the_shared_default():
    '''So they cannot drift from the value the buttons actually write.'''
    for name in ('reset_abs', 'reset_scat'):
        description = getattr(bpy.ops.acoustic, name).get_rna_type().description
        assert str(DEFAULT) in description, (name, description)


class FakeAPI:
    '''
    Stand in for AcousticIndex, recording what was asked for.

    The lookup is the interesting part and it is pure request plumbing, so the
    requests are what the tests assert on.
    '''

    def __init__(self, ids=(), search=None):
        self.ids = dict(ids)
        self.search = search
        self.urls = []

    def __call__(self, request, *args, **kwargs):
        url = request.full_url
        self.urls.append(url)

        if '/materials/search' in url:
            payload = {'items': [{'id': self.search}]} if self.search else {'items': []}
        else:
            key = url.rsplit('/', 1)[-1]
            if key not in self.ids:
                raise urllib.error.HTTPError(url, 404, 'Not Found', {}, None)
            payload = self.ids[key]

        return FakeResponse(payload)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fake_api(monkeypatch):
    def install(api):
        monkeypatch.setattr(io_module.urllib.request, 'urlopen', api)
        return api
    return install


def test_a_name_that_is_an_id_is_fetched_directly(fake_api):
    api = fake_api(FakeAPI(ids={'abc-123': {'label': 'Carpet'}}))

    assert io_module.fetch_material('key', 'abc-123') == {'label': 'Carpet'}
    # one request, and no search
    assert len(api.urls) == 1
    assert '/materials/abc-123' in api.urls[0]


def test_a_name_that_is_not_an_id_falls_back_to_the_search(fake_api):
    api = fake_api(FakeAPI(ids={'found-id': {'label': 'Carpet'}}, search='found-id'))

    assert io_module.fetch_material('key', 'Heavy Carpet') == {'label': 'Carpet'}

    assert len(api.urls) == 3
    assert '/materials/Heavy%20Carpet' in api.urls[0]
    assert '/materials/search?q=Heavy%20Carpet' in api.urls[1]
    assert '/materials/found-id' in api.urls[2]


def test_a_long_hyphenated_product_name_is_still_found(fake_api):
    '''
    The old heuristic called anything hyphenated and over 30 characters an id,
    so a name like this was fetched as one and the lookup failed outright.
    '''
    name = 'Acoustic Panel Type A - Perforated 16mm'
    assert len(name) > 30 and '-' in name

    api = fake_api(FakeAPI(ids={'real-id': {'label': 'Panel'}}, search='real-id'))

    assert io_module.fetch_material('key', name) == {'label': 'Panel'}
    assert any('/materials/search' in url for url in api.urls)


def test_an_unknown_name_reports_rather_than_guessing(fake_api):
    fake_api(FakeAPI())

    with pytest.raises(io_module.AcousticIndexError, match='No Acoustic Index material'):
        io_module.fetch_material('key', 'nothing like this')


def test_a_bad_key_is_not_reported_as_a_missing_material(fake_api):
    '''The search uses the same key, so falling through would mislead.'''
    class Unauthorised(FakeAPI):
        def __call__(self, request, *args, **kwargs):
            self.urls.append(request.full_url)
            raise urllib.error.HTTPError(request.full_url, 401, 'Unauthorized', {}, None)

    api = fake_api(Unauthorised())

    with pytest.raises(io_module.AcousticIndexError, match='Not authorised'):
        io_module.fetch_material('bad key', 'Carpet')

    assert len(api.urls) == 1, 'should not have tried the search'


def database_heading(material):
    '''
    The heading of the matched-entry box, as (text, icon).

    It is the first label the database panel draws: the Load button is an
    operator, and everything after the heading is the entry itself.
    '''
    labels = [(entry[1], entry[2])
              for entry in draw_panel(material, 'ACOUSTIC_PT_database')
              if entry[0] == 'label']

    return labels[0]


@pytest.mark.parametrize('query, failed, rename, expected', [
    (None, True, None, ('Last lookup failed', 'ERROR')),
    ('Heavy Carpet', False, 'Ceiling Tile',
     ('Loaded for "Heavy Carpet"', 'INFO')),
    (None, False, None, ('Matched Database Entry', 'CHECKMARK')),
    # a failed lookup outranks a rename
    ('Heavy Carpet', True, 'Ceiling Tile', ('Last lookup failed', 'ERROR')),
])
def test_the_panel_says_what_the_entry_below_is(mat, query, failed, rename,
                                                expected):
    """
    An entry stays valid for the name it was looked up under, not for the
    material's current name.
    """
    mat['_acoustic_loaded_label'] = 'Carpet'
    mat['_acoustic_loaded_query'] = query or mat.name
    mat['_acoustic_lookup_failed'] = failed

    if rename:
        mat.name = rename

    assert database_heading(mat) == expected


def test_an_entry_saved_before_the_query_was_recorded_reads_as_matched(mat):
    """Such a .blend carries neither key and must not be flagged."""
    mat['_acoustic_loaded_label'] = 'Carpet'

    assert database_heading(mat) == ('Matched Database Entry', 'CHECKMARK')


@pytest.fixture
def api_key():
    '''The operator reads the key from addon preferences, not the environment.'''
    prefs = bpy.context.preferences.addons['misuka-blender'].preferences
    previous = prefs.acousticindex_api_key
    prefs.acousticindex_api_key = 'test-key'
    yield
    prefs.acousticindex_api_key = previous


MEASURED = {
    'label': 'Carpet',
    'manufacturer': 'Acme',
    'measurements': {'absorption_iso_354': [{'alpha_s_octave': {'250': 0.2}}]},
}


def test_a_successful_lookup_records_the_query_it_matched(mat, fake_api, api_key):
    fake_api(FakeAPI(ids={'found-id': MEASURED}, search='found-id'))
    mat.name = 'Heavy Carpet'

    assert run(bpy.ops.acoustic.load_from_api, mat) == {'FINISHED'}

    assert mat['_acoustic_loaded_query'] == 'Heavy Carpet'
    assert not mat['_acoustic_lookup_failed']


def test_a_failed_lookup_leaves_the_previous_entry_in_place(mat, fake_api, api_key):
    '''
    The cached variants stay applicable, so they are kept. Only the panel's
    claim about them changes, which is what the flag is for.
    '''
    fake_api(FakeAPI(ids={'found-id': MEASURED}, search='found-id'))
    mat.name = 'Heavy Carpet'
    assert run(bpy.ops.acoustic.load_from_api, mat) == {'FINISHED'}

    # nothing matches the new name
    fake_api(FakeAPI())
    mat.name = 'Ceiling Tile'

    # reporting ERROR surfaces as a RuntimeError through the Python API
    with pytest.raises(RuntimeError, match='No Acoustic Index material'):
        run(bpy.ops.acoustic.load_from_api, mat)

    assert mat['_acoustic_lookup_failed']
    assert mat['_acoustic_loaded_label'] == 'Carpet'
    assert mat['_acoustic_loaded_query'] == 'Heavy Carpet'
    assert len(mat['_acoustic_variants_cache']) == 1


@pytest.mark.parametrize('light_type', ['SUN', 'SPOT', 'AREA'])
def test_an_acoustic_export_skips_non_point_lights(mat, tmp_path, light_type):
    '''
    Only convert_point_light() builds the sphere an acoustic source needs. The
    others wrote radiance tinted by the light color, which means nothing here.
    '''
    add_point_light(100.0, 0.5)
    bpy.ops.object.light_add(type=light_type)

    root = export_scene(mat, tmp_path)

    assert root.find(".//emitter[@type='directional']") is None
    assert root.find(".//emitter[@type='spot']") is None
    assert root.find(".//shape[@type='rectangle']") is None
    # the point light is still there
    assert root.find(".//shape[@type='sphere']") is not None


@pytest.mark.parametrize('light_type', ['SUN', 'SPOT', 'AREA'])
def test_a_visual_export_still_writes_every_light_type(mat, tmp_path, light_type):
    bpy.ops.object.light_add(type=light_type)

    root = export_scene(mat, tmp_path, export_mode='VISUAL')

    expected = {
        'SUN': ".//emitter[@type='directional']",
        'SPOT': ".//emitter[@type='spot']",
        'AREA': ".//shape[@type='rectangle']",
    }[light_type]
    assert root.find(expected) is not None


def test_an_acoustic_export_without_a_source_is_refused(mat, tmp_path):
    '''A scene with nothing to emit used to export silently.'''
    bpy.context.scene.render.engine = 'MITSUBA'
    bpy.ops.mesh.primitive_cube_add()
    bpy.context.active_object.data.materials.append(mat)
    bpy.ops.object.camera_add()

    path = os.path.join(str(tmp_path), 'scene.xml')

    with pytest.raises(RuntimeError, match='no emitter'):
        bpy.ops.export_scene.mitsuba(filepath=path, export_mode='ACOUSTIC')


def test_an_emission_mesh_counts_as_a_source(mat, tmp_path):
    '''
    The Emitter panel points at this as the way to get an emitter that behaves
    the same in both modes, so it has to satisfy the source check.
    '''
    bpy.context.scene.render.engine = 'MITSUBA'
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5)
    emissive = bpy.data.materials.new('Emitter')
    emissive.use_nodes = True
    tree = emissive.node_tree
    for node in list(tree.nodes):
        if node.type != 'OUTPUT_MATERIAL':
            tree.nodes.remove(node)
    emission = tree.nodes.new('ShaderNodeEmission')
    tree.links.new(emission.outputs[0],
                   tree.get_output_node('ALL').inputs['Surface'])
    bpy.context.active_object.data.materials.append(emissive)

    bpy.ops.object.camera_add()
    path = os.path.join(str(tmp_path), 'scene.xml')

    assert bpy.ops.export_scene.mitsuba(
        filepath=path, export_mode='ACOUSTIC') == {'FINISHED'}

    root = ET.parse(path).getroot()
    assert root.find(".//emitter[@type='area']") is not None


def test_an_acoustic_export_refuses_more_than_one_emitter(mat, tmp_path):
    '''
    An impulse response runs from one source to one receiver. Several emitters
    would sum into a single response without saying so.
    '''
    add_point_light(100.0, 0.5)
    add_point_light(100.0, 0.5)

    bpy.context.scene.render.engine = 'MITSUBA'
    bpy.ops.mesh.primitive_cube_add()
    bpy.context.active_object.data.materials.append(mat)
    bpy.ops.object.camera_add()

    path = os.path.join(str(tmp_path), 'scene.xml')

    with pytest.raises(RuntimeError, match='2 emitters'):
        bpy.ops.export_scene.mitsuba(filepath=path, export_mode='ACOUSTIC')


@pytest.mark.parametrize('export_mode', ['ACOUSTIC', 'VISUAL'])
def test_a_dot_in_a_name_is_replaced(mat, tmp_path, export_mode):
    '''
    misuka reserves '.' as a path delimiter and rejects a key holding one, but
    Blender names every duplicate Light.001. The export used to fail outright.
    '''
    mat.name = 'Wall.001'
    bpy.context.scene.render.engine = 'MITSUBA'

    bpy.ops.mesh.primitive_cube_add()
    bpy.context.active_object.data.materials.append(mat)
    bpy.ops.mesh.primitive_cube_add(location=(3, 0, 0))
    bpy.context.active_object.data.materials.append(mat)
    bpy.ops.object.camera_add()
    add_point_light(100.0, 0.5)

    path = os.path.join(str(tmp_path), 'scene.xml')
    assert bpy.ops.export_scene.mitsuba(
        filepath=path, export_mode=export_mode, export_ids=True) == {'FINISHED'}

    root = ET.parse(path).getroot()

    bsdf = root.find(".//bsdf[@id='mat-Wall_001']")
    assert bsdf is not None, 'the material id still carries a dot'

    # every reference has to point at the name it was stored under
    refs = {ref.get('id') for ref in root.iter('ref')}
    assert 'mat-Wall_001' in refs
    assert not any('.' in ref for ref in refs)


@pytest.mark.parametrize('export_mode', ['ACOUSTIC', 'VISUAL'])
def test_an_export_needs_the_misuka_engine(mat, tmp_path, export_mode):
    '''
    Both modes are gated on the misuka engine, so exporting from another one
    would write a scene from values the user cannot see. Acoustic used to fall
    back to hardcoded defaults, and Visual to Cycles' own sampler and filter.
    '''
    bpy.context.scene.render.engine = 'CYCLES'
    bpy.ops.mesh.primitive_cube_add()
    bpy.context.active_object.data.materials.append(mat)
    bpy.ops.object.camera_add()

    path = os.path.join(str(tmp_path), 'scene.xml')

    with pytest.raises(RuntimeError, match='A misuka export needs'):
        bpy.ops.export_scene.mitsuba(filepath=path, export_mode=export_mode)
