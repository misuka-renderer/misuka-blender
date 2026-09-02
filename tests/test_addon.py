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


def test_every_help_button_points_at_a_page_that_exists():
    '''
    A HELP button that 404s is worse than no button, and a page rename is easy
    to make without noticing the buttons. The literals are read straight out of
    the source, so a new button is covered the moment it is written.
    '''
    import ast
    import os
    import re

    addon_root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    addon_dir = os.path.join(addon_root, 'misuka-blender')
    docs_dir = os.path.join(addon_root, 'docs')

    pages = set()

    for dirpath, _, filenames in os.walk(addon_dir):
        for filename in filenames:
            if not filename.endswith('.py'):
                continue

            source = open(os.path.join(dirpath, filename), encoding='utf-8').read()

            for node in ast.walk(ast.parse(source)):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, 'id', None) or getattr(node.func, 'attr', None)
                if name != 'draw_help_button':
                    continue
                # draw_help_button(layout, page), so the page is the second arg.
                page = node.args[1]
                assert isinstance(page, ast.Constant), ast.dump(node)
                pages.add(page.value)

    assert pages, 'no HELP buttons found'

    for page in pages:
        # Strip the anchor: the page has to exist, the anchor is Sphinx's job.
        path = re.sub(r'#.*$', '', page)
        assert path.endswith('.html'), page
        source_file = os.path.join(docs_dir, path[:-len('.html')] + '.md')
        assert os.path.isfile(source_file), f'{page} has no {source_file}'


def test_the_documentation_url_matches_bl_info():
    '''
    Blender parses bl_info instead of importing it, so wiki_url cannot
    reference DOCS_URL and the two have to be kept in step by hand.
    '''
    import importlib

    addon = _addon()
    docs = importlib.import_module('misuka-blender.docs')

    assert addon.bl_info['wiki_url'] == docs.DOCS_URL
    assert docs.DOCS_URL.endswith('/')
    assert docs.url('installation.html').startswith('https://')
