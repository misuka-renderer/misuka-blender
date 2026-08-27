import os

import bpy

import pytest

from fixtures import *

@pytest.mark.parametrize("xml_scene", ["scenes/test1.xml"])
def test_round_trip_visual(xml_scene, resource_resolver, mitsuba_scene_ztest):
    '''Import a visual scene, export it in visual mode, and compare renders.'''
    resolution = (1280, 720)
    sample_budget = int(2e6)
    pixel_count = resolution[0] * resolution[1]
    spp = sample_budget // pixel_count

    ref_scene_file = resource_resolver.get_absolute_resource_path(xml_scene)
    ref_scene_name, _ = os.path.splitext(os.path.basename(ref_scene_file))
    test_output_dir = resource_resolver.ensure_resource_dir(f'out/{ref_scene_name}')
    output_scene_file = os.path.join(test_output_dir, f'{ref_scene_name}_out.xml')

    assert bpy.ops.import_scene.mitsuba(filepath=ref_scene_file) == {'FINISHED'}

    # NOTE: The reference scene's `moment` integrator wraps `path` to give the
    #       z-test its variance image. The importer has no Blender equivalent for
    #       `moment`, so the scene keeps the property default (`acoustic_path`);
    #       select the visual integrator explicitly before exporting.
    bpy.context.scene.mitsuba.active_integrator = 'path'

    assert bpy.ops.export_scene.mitsuba(
        filepath=output_scene_file, ignore_background=True, acoustic_mode=False) == {'FINISHED'}

    assert mitsuba_scene_ztest.compare_scenes(ref_scene_file, output_scene_file, spp, resolution, test_output_dir)

@pytest.mark.parametrize("xml_scene", ["scenes/test1.xml"])
def test_round_trip_acoustic(xml_scene, resource_resolver):
    '''Export in acoustic mode and check misuka can load the result.

    Acoustic renders produce an impulse response rather than an image, so there is
    no reference to z-test against yet; this asserts the exported scene parses and
    carries the acoustic plugin set.
    '''
    from misuka import load_file

    ref_scene_file = resource_resolver.get_absolute_resource_path(xml_scene)
    ref_scene_name, _ = os.path.splitext(os.path.basename(ref_scene_file))
    test_output_dir = resource_resolver.ensure_resource_dir(f'out/{ref_scene_name}')
    output_scene_file = os.path.join(test_output_dir, f'{ref_scene_name}_acoustic_out.xml')

    assert bpy.ops.import_scene.mitsuba(filepath=ref_scene_file) == {'FINISHED'}
    assert bpy.ops.export_scene.mitsuba(
        filepath=output_scene_file, ignore_background=True, acoustic_mode=True) == {'FINISHED'}

    scene = load_file(output_scene_file)

    assert str(scene.integrator()).startswith('AcousticPathIntegrator'), \
        f'Expected an acoustic integrator, got {scene.integrator()}'
    assert scene.sensors(), 'Acoustic export produced no sensor'
    assert str(scene.sensors()[0]).startswith('Microphone'), \
        f'Expected a microphone sensor, got {scene.sensors()[0]}'
    assert str(scene.sensors()[0].film()).startswith('Tape'), \
        f'Expected a tape film, got {scene.sensors()[0].film()}'
