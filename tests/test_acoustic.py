'''
Tests for the acoustic material operators.

These run inside Blender with the addon enabled (see scripts/run_tests.py), so
they can register properties and drive the operators for real.
'''
import importlib
import os
import xml.etree.ElementTree as ET

import bpy
import pytest


bands = importlib.import_module('misuka-blender.io.acoustic_bands')

OCTAVES = bands.OCTAVES
ABS_PROPS = bands.ABS_PROPS
SCAT_PROPS = bands.SCAT_PROPS


@pytest.fixture
def mat():
    material = bpy.data.materials.new('acoustic_test')
    material.use_nodes = True
    return material


def run(operator, material):
    '''
    Call an acoustic operator against `material`.

    The panel supplies `context.material` from the properties editor; a headless
    test has no active material, so it has to be overridden explicitly.
    '''
    with bpy.context.temp_override(material=material):
        return operator()


def load_variant(mat, variant):
    '''Prime the material as if the database operator had just fetched this.'''
    mat['_acoustic_variants_cache'] = [variant]
    mat.acoustic_variant_enum = 'NONE'


def test_octave_lookup_reads_json_string_keys():
    '''
    Measurement data arrives as JSON, so its keys are strings. The scattering
    copy of this lookup compared raw ints against them, matched nothing, and
    then raised KeyError indexing with an int.
    '''
    data = {'250': 0.2, '1000': 0.6}

    values = bands.octave_lookup(data, OCTAVES, 0.25)

    assert values[OCTAVES.index(250)] == 0.2
    assert values[OCTAVES.index(1000)] == 0.6
    # clamped to the nearest measurement outside the measured range
    assert values[OCTAVES.index(63)] == 0.2
    assert values[OCTAVES.index(16000)] == 0.6
    # and the fallback inside a gap
    assert values[OCTAVES.index(500)] == 0.25


def test_apply_variant_reads_scattering_octave_data(mat):
    '''A scattering variant without third-octave data used to raise KeyError.'''
    load_variant(mat, {
        '_type': 'scattering',
        'scatter_octave': {'500': 0.3, '2000': 0.7},
    })

    assert run(bpy.ops.acoustic.apply_variant, mat) == {'FINISHED'}

    assert mat.acoustic_scat_500 == pytest.approx(0.3)
    assert mat.acoustic_scat_2000 == pytest.approx(0.7)


def test_apply_variant_reads_absorption_octave_data(mat):
    '''The absorption twin was already correct; keep it that way.'''
    load_variant(mat, {
        '_type': 'absorption',
        'alpha_s_octave': {'500': 0.3, '2000': 0.7},
    })

    assert run(bpy.ops.acoustic.apply_variant, mat) == {'FINISHED'}

    assert mat.acoustic_abs_500 == pytest.approx(0.3)
    assert mat.acoustic_abs_2000 == pytest.approx(0.7)


def test_operators_are_unavailable_without_a_material():
    '''
    Every operator dereferences context.material, so poll has to guard it.
    Without that, invoking one from the F3 search menu raises AttributeError.
    '''
    assert getattr(bpy.context, 'material', None) is None

    for operator in (
        bpy.ops.acoustic.reset_abs,
        bpy.ops.acoustic.reset_scat,
        bpy.ops.acoustic.reset_specular_lobe_width,
        bpy.ops.acoustic.interpolate_abs,
        bpy.ops.acoustic.interpolate_scat,
        bpy.ops.acoustic.apply_variant,
        bpy.ops.acoustic.load_from_api,
    ):
        assert not operator.poll(), operator


def test_operators_are_available_with_a_material(mat):
    with bpy.context.temp_override(material=mat):
        assert bpy.ops.acoustic.reset_abs.poll()
        assert bpy.ops.acoustic.interpolate_abs.poll()


def export_scene(mat, tmp_path):
    '''Export a single cube carrying `mat` and return the parsed scene root.'''
    bpy.ops.mesh.primitive_cube_add()
    bpy.context.active_object.data.materials.append(mat)
    bpy.ops.object.camera_add()

    path = os.path.join(str(tmp_path), 'scene.xml')

    assert bpy.ops.export_scene.mitsuba(
        filepath=path, acoustic_mode=True) == {'FINISHED'}

    return ET.parse(path).getroot()


def film_setting(root, kind, name):
    film = root.find(".//film[@type='tape']")
    assert film is not None, 'no tape film in the exported scene'
    return film.find(f"{kind}[@name='{name}']").get('value')


@pytest.mark.parametrize('resolution, expected', [
    ('OCTAVE', bands.OCTAVES),
    ('THIRD_OCTAVE', bands.THIRD_OCTAVES),
])
def test_film_frequencies_follow_the_band_resolution(mat, tmp_path, resolution, expected):
    '''
    The tape film was pinned to a single 500 Hz band, so eight of the nine
    per-material coefficients never reached the simulation.
    '''
    bpy.context.scene.mitsuba.acoustic_band_resolution = resolution

    written = film_setting(export_scene(mat, tmp_path), 'string', 'frequencies')

    assert [int(f) for f in written.split(',')] == list(expected)


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
        filepath=path, acoustic_mode=False) == {'FINISHED'}

    root = ET.parse(path).getroot()

    assert root.find(".//integrator[@type='acoustic_path']") is None
    assert root.find(".//integrator[@type='path']") is not None
    assert root.find(".//film[@type='hdrfilm']") is not None
