'''
The misuka engine exists so the panels have something to poll, and for nothing
else.

The add-on is an exporter. Rendering happens in misuka, outside Blender. That
is not only a scoping decision: instantiating a misuka scene inside Blender
faults on Windows under 3.6, 4.2 and 4.5, because misuka needs a newer C++
runtime than those ship in `blender.crt`. Since nothing in the add-on builds a
scene object, that failure is unreachable, and these tests are what keeps it
that way.
'''
import importlib

import bpy
import pytest


engine_module = importlib.import_module('misuka-blender.engine.final')
exporter_module = importlib.import_module('misuka-blender.io.exporter')


def test_the_engine_is_registered_and_selectable():
    '''Selecting it is what puts the acoustic settings in front of the user.'''
    # An add-on engine is not in the enum's static items, so assigning it is
    # the check: an unregistered identifier raises here.
    bpy.context.scene.render.engine = 'MITSUBA'
    assert bpy.context.scene.render.engine == 'MITSUBA'


def test_the_panels_poll_under_the_engine():
    '''
    Every misuka panel gates on `context.engine`, so a panel that stopped
    polling would take the whole acoustic UI with it.
    '''
    properties = importlib.import_module('misuka-blender.engine.properties')
    panel = properties.MITSUBA_RENDER_PT_acoustic

    bpy.context.scene.render.engine = 'MITSUBA'
    assert 'MITSUBA' in panel.COMPAT_ENGINES
    assert panel.poll(bpy.context)

    bpy.context.scene.render.engine = 'CYCLES'
    assert not panel.poll(bpy.context)


def test_the_engine_claims_no_previews():
    '''
    Blender asks an engine that claims previews to render material and world
    thumbnails, which would be a scene load per thumbnail.
    '''
    assert engine_module.MitsubaRenderEngine.bl_use_preview is False


def test_the_engine_reports_instead_of_rendering():
    '''
    F12 has to say what to do instead. Returning quietly leaves a blank render
    window, which reads as a broken add-on rather than a deliberate limit.
    '''
    reported = []

    class Stub:
        '''Stands in for the engine instance Blender would pass as self.'''

        def report(self, level, message):
            reported.append((level, message))

    engine_module.MitsubaRenderEngine.render(Stub(), depsgraph=None)

    assert reported, 'rendering said nothing at all'
    level, message = reported[0]
    assert 'ERROR' in level
    assert 'does not render inside Blender' in message
    assert 'Export' in message


def test_nothing_in_the_add_on_can_instantiate_a_scene():
    '''
    The regression guard. `dict_to_scene` was the only call that built a misuka
    scene object, and it existed for the renderer that no longer exists.

    Mesh conversion still calls `load_dict` to build misuka's `blender` mesh
    plugin, which is a single plugin rather than a scene and is not affected.
    '''
    assert not hasattr(exporter_module.SceneConverter, 'dict_to_scene')

    # The flag that told the exporter to write only the active camera existed
    # for the renderer too. Without it every camera is exported, which is what
    # a room measured at several receiver positions needs.
    converter = exporter_module.SceneConverter()
    assert not hasattr(converter, 'render')
