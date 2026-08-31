'''
Tests for the acoustic material operators.

These run inside Blender with the addon enabled (see scripts/run_tests.py), so
they can register properties and drive the operators for real.
'''
import importlib

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
