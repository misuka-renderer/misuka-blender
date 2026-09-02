bl_info = {
    'name': 'misuka',
    'author': 'Tobias Jüterbock, Julius Schwarz',
    'version': (0, 2, 0),
    'blender': (2, 93, 0),
    'category': 'Render',
    'location': 'File menu, render engine menu',
    'description': 'misuka integration for Blender',
    # Blender's Documentation button. Kept as a literal because Blender
    # parses bl_info instead of importing it; DOCS_URL in docs.py is the
    # same URL for everything that can import.
    'wiki_url': 'https://misuka-blender.readthedocs.io/latest/',
    'tracker_url': 'https://github.com/misuka-renderer/misuka-blender/issues/new/choose',
    #'warning': 'alpha',
}

import bpy
from bpy.props import StringProperty, BoolProperty
from bpy.types import Operator, AddonPreferences
from bpy.utils import register_class, unregister_class

import os
import sys
import subprocess

from . import io, engine
from .io import draw_paragraphs
from .docs import draw_help_button

DEPS_MITSUBA_VERSION = '0.1.0'

# Fallback index for the releases that land here before they reach PyPI.
TESTPYPI_INDEX_URL = 'https://test.pypi.org/simple/'

def get_addon_preferences(context):
    return context.preferences.addons[__name__].preferences

def init_mitsuba(context):
    # Make sure we can load mitsuba from blender
    try:
        os.environ['DRJIT_NO_RTLD_DEEPBIND'] = 'True'
        should_reload_mitsuba = 'misuka' in sys.modules
        import misuka as mitsuba
        # If mitsuba was already loaded and we change the path, we need to reload it, since the import above will be ignored
        if should_reload_mitsuba:
            import importlib
            importlib.reload(mitsuba)
        mitsuba.set_variant('scalar_rgb')
        return True
    except ModuleNotFoundError:
        return False

def try_register_mitsuba(context):
    prefs = get_addon_preferences(context)
    prefs.mitsuba_dependencies_status_message = ''

    could_init_mitsuba = False
    if prefs.using_mitsuba_custom_path:
        update_additional_custom_paths(prefs, context)
        could_init_mitsuba = init_mitsuba(context)
        if could_init_mitsuba:
            import misuka as mitsuba
            prefs.mitsuba_custom_version = mitsuba.__version__
            if prefs.has_valid_mitsuba_custom_version:
                prefs.mitsuba_dependencies_status_message = f'Found custom misuka v{prefs.mitsuba_custom_version}.'
            else:
                prefs.mitsuba_dependencies_status_message = f'Found custom misuka v{prefs.mitsuba_custom_version}. Supported version is v{DEPS_MITSUBA_VERSION}.'
        else:
            prefs.mitsuba_dependencies_status_message = 'Failed to load custom misuka. Please verify the path to the build directory.'
    elif prefs.has_pip_dependencies:
        if prefs.has_valid_dependencies_version:
            could_init_mitsuba = init_mitsuba(context)
            if could_init_mitsuba:
                import misuka as mitsuba
                prefs.mitsuba_dependencies_status_message = f'Found pip misuka v{mitsuba.__version__}.'
            else:
                prefs.mitsuba_dependencies_status_message = 'Failed to load misuka package.'
        else:
            prefs.mitsuba_dependencies_status_message = f'Found pip misuka v{prefs.installed_dependencies_version}. Supported version is v{DEPS_MITSUBA_VERSION}.'
    else:
        prefs.mitsuba_dependencies_status_message = 'misuka dependencies not installed.'

    prefs.is_mitsuba_initialized = could_init_mitsuba

    if could_init_mitsuba:
        io.register()
        engine.register()

    return could_init_mitsuba

def try_unregister_mitsuba():
    '''
    Try unregistering Addon classes.
    This may fail if Mitsuba wasn't found, hence the try catch guard
    '''
    try:
        io.unregister()
        engine.unregister()
        return True
    except RuntimeError:
        return False

def try_reload_mitsuba(context):
    try_unregister_mitsuba()
    if try_register_mitsuba(context):
        # Save user preferences
        bpy.ops.wm.save_userpref()

def ensure_pip():
    result = subprocess.run([sys.executable, '-m', 'ensurepip'], capture_output=True)
    return result.returncode == 0

def run_pip(args):
    '''Run pip in Blender's interpreter, returning (return code, combined output).

    The output is captured so that a failure can be shown in a dialog, and echoed
    to the console so that it still ends up where it always did.
    '''
    result = subprocess.run([sys.executable, '-m', 'pip', *args], capture_output=True)
    parts = [part for part in (result.stdout, result.stderr) if part]
    output = b'\n'.join(parts).decode('utf-8', errors='replace')
    if output:
        print(output)
    return result.returncode, output

def pip_install_args(requirement, index_url=None, no_deps=False, upgrade=False, force_reinstall=False):
    '''The pip arguments for one install, without running anything.'''
    args = ['install']
    if upgrade:
        args.append('--upgrade')
    if force_reinstall:
        args.append('--force-reinstall')
    if no_deps:
        args.append('--no-deps')
    if index_url is not None:
        args += ['--index-url', index_url]
    args.append(requirement)
    return args

def runtime_requirements(requirements):
    '''Requirements without the ones gated behind an optional extra.

    Package metadata lists every extra's dependencies alongside the mandatory
    ones, marked with an `extra == "..."` environment marker. Installing those
    would pull in test and documentation dependencies nobody asked for.
    '''
    return [req for req in requirements if 'extra ==' not in req and 'extra==' not in req]

def installed_requires(package):
    '''The requirements of an installed distribution, read in a fresh interpreter.

    The running interpreter caches package metadata, so a distribution installed
    moments ago has to be inspected from a subprocess to be seen at all.
    '''
    script = f"import importlib.metadata as md; print('\\n'.join(md.requires({package!r}) or []))"
    result = subprocess.run([sys.executable, '-c', script], capture_output=True)
    if result.returncode != 0:
        return []
    output = result.stdout.decode('utf-8', errors='replace')
    return [line.strip() for line in output.splitlines() if line.strip()]

def install_dependencies_from_testpypi():
    '''Install misuka from TestPyPI, with its dependencies still coming from PyPI.

    Take *only* misuka from TestPyPI. Its /simple/ pages for other projects are
    unreliable (drjit's returns 503), so letting the resolver reach it for
    dependencies makes every install hostage to that. This mirrors the fallback
    in .github/workflows/test-suite.yml.
    '''
    returncode, output = run_pip(pip_install_args(
        f'misuka=={DEPS_MITSUBA_VERSION}',
        index_url=TESTPYPI_INDEX_URL,
        no_deps=True,
        force_reinstall=True))
    if returncode != 0:
        return False, output

    requirements = runtime_requirements(installed_requires('misuka'))
    if requirements:
        returncode, deps_output = run_pip(['install', *requirements])
        if returncode != 0:
            return False, deps_output

    return True, output

def log_lines(text, max_lines=12):
    '''The last few meaningful lines of a command's output.

    pip signs off with its own `[notice]` block advertising a pip upgrade, which
    would otherwise be the tail we show and bury the actual error.
    '''
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    lines = [line for line in lines if not line.startswith('[notice]')]
    return lines[-max_lines:]

def draw_log_lines(layout, text):
    box = layout.box()
    for line in log_lines(text):
        box.label(text=line)

def last_log_line(text):
    lines = log_lines(text, max_lines=1)
    return lines[0] if lines else 'no output'

def offer_testpypi_fallback(operator, returncode, output):
    '''Report a failed PyPI install and open the TestPyPI retry dialog.'''
    operator.report({'ERROR'}, f'Failed to install misuka with return code {returncode}.')
    bpy.ops.mitsuba.pip_install_from_testpypi('INVOKE_DEFAULT', error_log=output)
    return {'CANCELLED'}

def check_pip_dependencies(context):
    prefs = get_addon_preferences(context)
    result = subprocess.run([sys.executable, '-m', 'pip', 'list'], capture_output=True)

    prefs.has_pip_dependencies = False
    prefs.has_valid_dependencies_version = False

    if result.returncode == 0:
        output_str = result.stdout.decode('utf-8')
        lines = output_str.splitlines(keepends=False)
        for line in lines:
            parts = line.split()
            if len(parts) >= 2 and parts[0] == 'misuka':
                prefs.has_pip_dependencies = True
                prefs.installed_dependencies_version = parts[1]
                break

    if not prefs.has_pip_dependencies:
        # Clear any version left over from a previous check, so a stale string
        # can't leak into the status message.
        prefs.installed_dependencies_version = ''
        prefs.has_valid_dependencies_version = False

def clean_additional_custom_paths(self, context):
    # Remove old values from system PATH and sys.path
    if self.additional_python_path in sys.path:
        sys.path.remove(self.additional_python_path)
    if self.additional_path and self.additional_path in os.environ['PATH']:
        items = os.environ['PATH'].split(os.pathsep)
        items.remove(self.additional_path)
        os.environ['PATH'] = os.pathsep.join(items)

def update_additional_custom_paths(self, context):
    build_path = bpy.path.abspath(self.mitsuba_custom_path)
    if len(build_path) > 0:
        clean_additional_custom_paths(self, context)

        # Add path to the binaries to the system PATH
        self.additional_path = build_path
        if self.additional_path not in os.environ['PATH']:
            os.environ['PATH'] += os.pathsep + self.additional_path

        # Add path to python libs to sys.path
        self.additional_python_path = os.path.join(build_path, 'python')
        if self.additional_python_path not in sys.path:
            # NOTE: We insert in the first position here, so that the custom path
            #       supersede the pip version
            sys.path.insert(0, self.additional_python_path)

class MITSUBA_OT_install_pip_dependencies(Operator):
    bl_idname = 'mitsuba.install_pip_dependencies'
    bl_label = 'Install misuka pip dependencies'
    bl_description = 'Use pip to install the add-on\'s required dependencies'

    @classmethod
    def poll(cls, context):
        prefs = get_addon_preferences(context)
        return not prefs.has_pip_dependencies or not prefs.has_valid_dependencies_version

    def execute(self, context):
        returncode, output = run_pip(pip_install_args(f'misuka=={DEPS_MITSUBA_VERSION}', force_reinstall=True))
        if returncode != 0:
            return offer_testpypi_fallback(self, returncode, output)

        check_pip_dependencies(context)

        try_reload_mitsuba(context)

        return {'FINISHED'}

class MITSUBA_OT_upgrade_pip_dependencies(Operator):
    bl_idname = 'mitsuba.upgrade_pip_dependencies'
    bl_label = 'Upgrade misuka pip dependencies'
    bl_description = 'Use pip to upgrade misuka to the version supported by this add-on'

    @classmethod
    def poll(cls, context):
        prefs = get_addon_preferences(context)
        return prefs.has_pip_dependencies

    def execute(self, context):
        returncode, output = run_pip(pip_install_args(f'misuka=={DEPS_MITSUBA_VERSION}', upgrade=True))
        if returncode != 0:
            return offer_testpypi_fallback(self, returncode, output)

        check_pip_dependencies(context)

        try_reload_mitsuba(context)

        return {'FINISHED'}

class MITSUBA_OT_uninstall_pip_dependencies(Operator):
    bl_idname = 'mitsuba.uninstall_pip_dependencies'
    bl_label = 'Uninstall misuka pip dependencies'
    bl_description = 'Use pip to uninstall the misuka package'

    @classmethod
    def poll(cls, context):
        prefs = get_addon_preferences(context)
        return prefs.has_pip_dependencies

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        prefs = get_addon_preferences(context)

        returncode, output = run_pip(['uninstall', '-y', 'misuka'])
        if returncode != 0:
            self.report({'ERROR'}, f'Failed to uninstall misuka with return code {returncode}. '
                                   f'Restarting Blender may be required first: {last_log_line(output)}')
            return {'CANCELLED'}

        try_unregister_mitsuba()

        check_pip_dependencies(context)

        # The extension module stays loaded in this interpreter, so the add-on
        # cannot honestly claim a clean state until Blender restarts.
        prefs.is_mitsuba_initialized = False
        prefs.require_restart = True
        bpy.ops.wm.save_userpref()

        return {'FINISHED'}

class MITSUBA_OT_pip_install_from_testpypi(Operator):
    bl_idname = 'mitsuba.pip_install_from_testpypi'
    bl_label = 'Retry the misuka install from TestPyPI'
    bl_description = 'Retry the failed install, taking misuka from TestPyPI'

    error_log : StringProperty(
        name = 'pip output of the failed install',
        default = '',
        options = {'SKIP_SAVE'},
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=600)

    def draw(self, context):
        layout = self.layout
        layout.label(text='Installing misuka from PyPI failed.', icon='ERROR')
        draw_log_lines(layout, self.error_log)
        layout.label(text=f'Retry with misuka taken from {TESTPYPI_INDEX_URL} instead?')

    def execute(self, context):
        succeeded, output = install_dependencies_from_testpypi()
        if not succeeded:
            self.report({'ERROR'}, f'Failed to install misuka from TestPyPI: {last_log_line(output)}')
            return {'CANCELLED'}

        check_pip_dependencies(context)

        try_reload_mitsuba(context)

        return {'FINISHED'}

def update_using_mitsuba_custom_path(self, context):
    self.require_restart = True
    if self.using_mitsuba_custom_path:
        update_mitsuba_custom_path(self, context)
    else:
        clean_additional_custom_paths(self, context)

def update_mitsuba_custom_path(self, context):
    if self.is_mitsuba_initialized:
        self.require_restart = True
    if self.using_mitsuba_custom_path and len(self.mitsuba_custom_path) > 0:
        update_additional_custom_paths(self, context)
        if not self.is_mitsuba_initialized:
            try_reload_mitsuba(context)

def release_version(version_string):
    '''Leading numeric components of a version, e.g. '0.1.0.dev1+gabc' -> (0, 1, 0).

    Custom builds carry a dev/commit suffix that never compares equal to a plain
    release string, so both checks compare on the release components only.
    '''
    components = []
    for part in version_string.split('+')[0].split('.'):
        if not part.isdigit():
            break
        components.append(int(part))
    return tuple(components)

def update_installed_dependencies_version(self, context):
    self.has_valid_dependencies_version = \
        release_version(self.installed_dependencies_version) == release_version(DEPS_MITSUBA_VERSION)

def update_mitsuba_custom_version(self, context):
    self.has_valid_mitsuba_custom_version = \
        release_version(self.mitsuba_custom_version) == release_version(DEPS_MITSUBA_VERSION)

# misuka is licensed separately from this add-on, and its license restricts
# use rather than only redistribution. The notice sits beside the install
# buttons because pressing one is the moment a user takes misuka on.
MISUKA_LICENSE_URL = 'https://polyformproject.org/licenses/noncommercial/1.0.0'
MISUKA_LICENSE_NOTICE = (
    'misuka is licensed under PolyForm Noncommercial 1.0.0. Because this '
    'add-on imports misuka, it is effectively restricted to noncommercial '
    'use as well. Commercial use needs an agreement with the misuka '
    'maintainers.'
)


class MitsubaPreferences(AddonPreferences):
    bl_idname = __name__

    acousticindex_api_key: StringProperty(
        name="acousticindex.com API Key",
        subtype='PASSWORD'
    )

    is_mitsuba_initialized : BoolProperty(
        name = 'Is misuka initialized',
    )

    has_pip_dependencies : BoolProperty(
        name = 'Has pip dependencies installed',
    )

    installed_dependencies_version : StringProperty(
        name = 'Installed misuka dependencies version string',
        default = '',
        update = update_installed_dependencies_version,
    )

    has_valid_dependencies_version : BoolProperty(
        name = 'Has the correct version of dependencies'
    )

    mitsuba_dependencies_status_message : StringProperty(
        name = 'misuka dependencies status message',
        default = '',
    )

    require_restart : BoolProperty(
        name = 'Require a Blender restart',
    )

    # Advanced settings

    using_mitsuba_custom_path : BoolProperty(
        name = 'Using custom misuka path',
        update = update_using_mitsuba_custom_path,
    )

    mitsuba_custom_path : StringProperty(
        name = 'Custom misuka path',
        description = 'Path to the custom misuka build directory',
        default = '',
        subtype = 'DIR_PATH',
        update = update_mitsuba_custom_path,
    )

    mitsuba_custom_version : StringProperty(
        name = 'Custom misuka build version',
        default = '',
        update = update_mitsuba_custom_version,
    )

    has_valid_mitsuba_custom_version : BoolProperty(
        name = 'Has the correct version of custom misuka build'
    )

    additional_path : StringProperty(
        name = 'Addition to PATH',
        default = '',
        subtype = 'DIR_PATH',
    )

    additional_python_path : StringProperty(
        name = 'Addition to sys.path',
        default = '',
        subtype = 'DIR_PATH',
    )

    def draw(self, context):
        layout = self.layout

        draw_help_button(layout, "installation.html")

        row = layout.row()
        icon = 'ERROR'
        row.alert = True
        if self.require_restart:
            self.mitsuba_dependencies_status_message = 'A restart is required to apply the changes.'
        elif self.is_mitsuba_initialized and (not self.using_mitsuba_custom_path or (self.using_mitsuba_custom_path and self.has_valid_mitsuba_custom_version)):
            icon = 'CHECKMARK'
            row.alert = False
        row.label(text=self.mitsuba_dependencies_status_message, icon=icon)

        operator_text = 'Install dependencies'
        if self.has_pip_dependencies and not self.has_valid_dependencies_version:
            operator_text = 'Update dependencies'
        row = layout.row(align=True)
        row.operator(MITSUBA_OT_install_pip_dependencies.bl_idname, text=operator_text)
        row.operator(MITSUBA_OT_upgrade_pip_dependencies.bl_idname, text='Upgrade dependencies')
        row.operator(MITSUBA_OT_uninstall_pip_dependencies.bl_idname, text='Uninstall dependencies')

        box = layout.box()
        box.label(text='misuka License', icon='INFO')
        draw_paragraphs(box, context, MISUKA_LICENSE_NOTICE)
        box.operator(
            'wm.url_open', text='Read the license', icon='URL',
        ).url = MISUKA_LICENSE_URL

        box = layout.box()
        box.label(text='Advanced Settings')
        box.prop(self, 'using_mitsuba_custom_path', text=f'Use custom misuka path') #(Supported version is v{DEPS_MITSUBA_VERSION})
        if self.using_mitsuba_custom_path:
            box.prop(self, 'mitsuba_custom_path')

        # --- AcousticIndex API ---
        box = layout.box()
        box.label(text="Acoustic Index Database")
        box.prop(self, "acousticindex_api_key")

classes = (
    MITSUBA_OT_install_pip_dependencies,
    MITSUBA_OT_upgrade_pip_dependencies,
    MITSUBA_OT_uninstall_pip_dependencies,
    MITSUBA_OT_pip_install_from_testpypi,
    MitsubaPreferences,
)

def register():
    for cls in classes:
        register_class(cls)

    context = bpy.context
    prefs = get_addon_preferences(context)
    prefs.require_restart = False

    if not ensure_pip():
        raise RuntimeError('Cannot activate misuka-blender add-on. Python pip module cannot be initialized.')

    check_pip_dependencies(context)
    if try_register_mitsuba(context):
        import misuka as mitsuba
        print(f'misuka-blender v{".".join(str(e) for e in bl_info["version"])}{bl_info["warning"] if "warning" in bl_info else ""} registered (with misuka v{mitsuba.__version__})')

def unregister():
    for cls in classes:
        unregister_class(cls)
    try_unregister_mitsuba()
