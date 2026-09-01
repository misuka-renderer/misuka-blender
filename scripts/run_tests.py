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
        # pytest_unconfigure() still runs when pytest_configure() raises.
        self.remove_link = False

    def _create_link(self):
        if sys.platform == 'win32':
            import _winapi
            _winapi.CreateJunction(str(self.mi_addon_dir), str(self.bl_mi_addon_dir))
        else:
            os.symlink(self.mi_addon_dir, self.bl_mi_addon_dir, target_is_directory=True)

    def _remove_link(self):
        # A junction is a directory: rmdir removes it, os.remove does not.
        if sys.platform == 'win32':
            os.rmdir(self.bl_mi_addon_dir)
        else:
            os.unlink(self.bl_mi_addon_dir)

    def pytest_configure(self, config):
        # os.path.exists() follows a link, so one whose target has moved reads
        # as absent and os.symlink() then fails with FileExistsError.
        # os.readlink() reads Windows directory junctions too, since 3.8.
        try:
            target = os.path.realpath(os.readlink(self.bl_mi_addon_dir))
        except OSError:
            target = None

        if target == os.path.realpath(self.mi_addon_dir):
            # Already linked at this checkout, most likely by a developer who
            # works against it. Reuse it and leave it in teardown, so running
            # the tests does not uninstall the add-on from their Blender.
            self.remove_link = False
        elif target is None and os.path.lexists(self.bl_mi_addon_dir):
            # A real add-on install. Deleting it is not ours to do.
            raise RuntimeError(
                f'{self.bl_mi_addon_dir} exists and is not a link. '
                'Move or delete the installed add-on, then run the tests again.'
            )
        else:
            # Nothing there, or some other link, possibly stale from a run that
            # crashed before teardown. A link is safe to replace.
            if target is not None:
                self._remove_link()
            self._create_link()
            self.remove_link = True

        if bpy.ops.preferences.addon_enable(module='misuka-blender') != {'FINISHED'}:
            raise RuntimeError('Cannot enable misuka-blender addon')

        if not bpy.context.preferences.addons['misuka-blender'].preferences.is_mitsuba_initialized:
            raise RuntimeError('Failed to initialize misuka library')

    def pytest_unconfigure(self):
        print('[teardown] disabling addon', flush=True)
        bpy.ops.preferences.addon_disable(module='misuka-blender')
        print('[teardown] addon disabled', flush=True)

        if not self.remove_link:
            print('[teardown] symlink was already there, left in place', flush=True)
            return

        # An exception here propagates out of pytest.main(), is caught below
        # and turns a fully passing run red, so report it and carry on.
        try:
            self._remove_link()
        except OSError as e:
            print(f'[teardown] could not remove symlink: {e}', flush=True)
        else:
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
