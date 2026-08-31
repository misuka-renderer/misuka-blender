import bpy

from mathutils import Matrix

def test_prespective_sensor():
    import importlib
    sensors = importlib.import_module("misuka-blender.io.importer.sensors")
    assert sensors
    common = importlib.import_module("misuka-blender.io.importer.common")
    assert common

    from misuka import Properties
    mi_sensor_props = Properties('perspective')
    mi_context = common.MitsubaSceneImportContext(bpy.context, bpy.context.scene, bpy.context.scene.collection, '', mi_sensor_props, Matrix())

    bl_camera, world_matrix = sensors.mi_perspective_to_bl_camera(mi_context, mi_sensor_props)
    assert bl_camera.type == 'PERSP'


def _addon():
    # The add-on package directory is hyphenated, so it can only be imported by name.
    import importlib
    return importlib.import_module("misuka-blender")

def test_pip_install_args():
    addon = _addon()
    assert addon.pip_install_args('misuka==0.1.0', force_reinstall=True) == \
        ['install', '--force-reinstall', 'misuka==0.1.0']
    assert addon.pip_install_args('misuka==0.1.0', upgrade=True) == \
        ['install', '--upgrade', 'misuka==0.1.0']

def test_pip_install_args_testpypi_fallback():
    addon = _addon()
    args = addon.pip_install_args(
        'misuka==0.1.0', index_url=addon.TESTPYPI_INDEX_URL, no_deps=True, force_reinstall=True)
    assert args == ['install', '--force-reinstall', '--no-deps',
                    '--index-url', 'https://test.pypi.org/simple/', 'misuka==0.1.0']

def test_runtime_requirements_drops_extras():
    addon = _addon()
    requirements = ['drjit>=1.0', 'numpy', 'pytest; extra == "test"', 'sphinx; extra=="docs"']
    assert addon.runtime_requirements(requirements) == ['drjit>=1.0', 'numpy']

def test_log_lines_keeps_the_tail():
    addon = _addon()
    assert addon.log_lines('first\n\nsecond\nthird\n', max_lines=2) == ['second', 'third']
    assert addon.last_log_line('') == 'no output'

def test_log_lines_drops_pip_upgrade_notice():
    addon = _addon()
    output = ('ERROR: No matching distribution found for misuka==0.0.1\n'
              '\n'
              '[notice] A new release of pip is available: 23.2.1 -> 26.2.1\n'
              '[notice] To update, run: python -m pip install --upgrade pip\n')
    assert addon.last_log_line(output) == 'ERROR: No matching distribution found for misuka==0.0.1'

def test_release_version_ignores_dev_suffix():
    addon = _addon()
    assert addon.release_version('0.1.0.dev1+gabc') == (0, 1, 0)
    assert addon.release_version('0.1.0') == addon.release_version('0.1.0.dev1+gabc')
