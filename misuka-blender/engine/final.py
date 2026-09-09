import bpy


class MisukaRenderEngine(bpy.types.RenderEngine):
    '''
    The misuka engine, which exists so the panels have something to poll.

    The add-on is an exporter. Rendering happens in misuka, outside Blender,
    against the XML that File > Export writes.

    The engine is still registered, because every misuka panel polls
    `context.engine in {'MISUKA'}` and would not draw otherwise. Selecting it
    is what puts the acoustic settings in front of the user; it is not a
    statement that Blender can render the scene.

    It deliberately loads nothing. misuka's Windows build needs a newer C++
    runtime than Blender 3.6, 4.2 and 4.5 ship in `blender.crt`, so
    instantiating a scene inside Blender dies there with an access violation.
    Since no part of exporting needs a scene object, the add-on never builds
    one, and that whole class of failure is out of reach.

    See https://github.com/misuka-renderer/misuka-blender/issues/4.
    '''

    bl_idname = "MISUKA"
    bl_label = "misuka"
    # Blender asks an engine that claims previews to render material and world
    # thumbnails. This one renders nothing, so it claims nothing.
    bl_use_preview = False

    def render(self, depsgraph):
        '''
        Say what to do instead, and render nothing.

        Returning quietly would leave the blank render window that this used to
        produce, which reads as a broken add-on rather than a deliberate limit.
        '''
        self.report(
            {'ERROR'},
            "misuka does not render inside Blender. Export the scene with "
            "File > Export > misuka (.xml), then render it with misuka.")
