import sys
import os

import bpy
import pytest

class SetupPlugin:
    def __init__(self):
        mi_addon_root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        self.mi_addon_dir = os.path.join(mi_addon_root_dir, 'misuka-blender')
        self.bl_addon_dir  = bpy.utils.user_resource('SCRIPTS', path='addons', create=True)
        bpy.utils.refresh_script_paths()
        self.bl_mi_addon_dir = os.path.join(self.bl_addon_dir, 'misuka-blender')

    def pytest_configure(self, config):
        if os.path.exists(self.bl_mi_addon_dir):
            os.remove(self.bl_mi_addon_dir)
        
        # Create a symlink from the addon to the Blender script folder
        if sys.platform == 'win32':
            import _winapi
            _winapi.CreateJunction(str(self.mi_addon_dir), str(self.bl_mi_addon_dir))
        else:
            os.symlink(self.mi_addon_dir, self.bl_mi_addon_dir, target_is_directory=True)
        
        if bpy.ops.preferences.addon_enable(module='misuka-blender') != {'FINISHED'}:
            raise RuntimeError('Cannot enable misuka-blender addon')

        if not bpy.context.preferences.addons['misuka-blender'].preferences.is_mitsuba_initialized:
            raise RuntimeError('Failed to initialize misuka library')

    def pytest_unconfigure(self):
        print('[teardown] disabling addon', flush=True)
        bpy.ops.preferences.addon_disable(module='misuka-blender')
        print('[teardown] addon disabled', flush=True)
        # Remove the symlink
        os.remove(self.bl_mi_addon_dir)
        print('[teardown] symlink removed', flush=True)

    def pytest_runtest_setup(self, item):
        bpy.ops.wm.read_homefile(use_empty=True)
        if 'misuka-blender' not in bpy.context.preferences.addons:
            raise RuntimeError("Plugin was disabled by test reset")

if __name__ == '__main__':
    pytest_args = ["tests"]

    try:
        pytest_args += sys.argv[sys.argv.index('--')+1:]
    except ValueError:
        pass

    try:
        exit_code = pytest.main(pytest_args, plugins=[SetupPlugin()])
    except Exception as e:
        print(e)
        exit_code = 1

    print(f'[teardown] pytest returned {exit_code}', flush=True)

    # NOTE: Blender faults on Windows while tearing misuka down, after every test
    #       has already run (issue #4). The test result is fully determined by
    #       now, so leave immediately rather than unwind through native
    #       finalization. A crash *during* the tests never reaches this line and
    #       still fails the job.
    sys.stdout.flush()
    sys.stderr.flush()
    # int(): pytest.main returns an ExitCode enum rather than a plain int.
    os._exit(int(exit_code))
