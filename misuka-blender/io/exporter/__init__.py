import os
import xml.etree.ElementTree as ET

if "bpy" in locals():
    import importlib
    if "export_context" in locals():
        importlib.reload(export_context)
    if "materials" in locals():
        importlib.reload(materials)
    if "geometry" in locals():
        importlib.reload(geometry)
    if "lights" in locals():
        importlib.reload(lights)
    if "camera" in locals():
        importlib.reload(camera)

import bpy

from . import export_context
from . import materials
from . import geometry
from . import lights
from . import camera
from ... import docs

class SceneConverter:
    '''
    Converts a blender scene to a Mitsuba-compatible dict.
    Either save it as an XML or load it as a scene.
    '''
    def __init__(self, render=False):
        self.export_ctx = export_context.ExportContext()
        self.use_selection = False # Only export selection
        self.ignore_background = True
        self.allow_multiple_emitters = False
        self.render = render

    def set_path(self, name):
        self.export_path = name
        # Give the path to the export context, for saving meshes and files
        self.export_ctx.directory, _ = os.path.split(name)

    def scene_to_dict(self, depsgraph, window_manager):
        # Switch to object mode before exporting stuff, so everything is defined properly
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        # Store dependency graph
        self.export_ctx.deg = depsgraph

        b_scene = depsgraph.scene  # TODO: what if there are multiple scenes?
        acoustic_mode = self.export_ctx.acoustic_mode

        # Every setting an export writes lives on the misuka engine. Under
        # another one the exporter would substitute that engine's own settings,
        # so the scene would not match the panels the user set up. Say so rather
        # than writing a scene from values the user cannot see.
        if b_scene.render.engine != 'MITSUBA':
            raise RuntimeError(
                "A misuka export needs the misuka render engine. Set "
                "Render Properties > Render Engine to misuka."
            )

        # --- Integrator setup ---
        # Each mode has its own dropdown, and neither offers the other's
        # integrators, so the panel a mode reads cannot name a plugin it
        # would reject.
        if acoustic_mode:
            integrator = getattr(
                b_scene.mitsuba.available_integrators,
                b_scene.mitsuba.acoustic_integrator
            ).to_dict()

            # Required for acoustic integrator
            integrator['max_time'] = self.export_ctx.acoustic_max_time

        else:
            integrator = getattr(
                b_scene.mitsuba.available_integrators,
                b_scene.mitsuba.visual_integrator
            ).to_dict()

        # Named in both modes. Left unnamed it fell through to the counter and
        # reached the file as 'elm__0'.
        self.export_ctx.data_add(integrator, name="integrator")

        # A background emits from every direction at once, so as a sound source
        # it is a room with no walls rather than anything you would measure.
        # An acoustic export leaves it out whatever the world is set to, which
        # is why Ignore Default Background is inert in that mode.
        if acoustic_mode:
            if materials.world_emits(b_scene.world):
                self.export_ctx.log(
                    "An acoustic export skips the world background.", 'INFO')
        else:
            materials.export_world(self.export_ctx, b_scene.world,
                                   self.ignore_background)


        # Establish list of particle objects
        particles = []
        for particle_sys in bpy.data.particles:
            if particle_sys.render_type == 'OBJECT':
                particles.append(particle_sys.instance_object.name)
            elif particle_sys.render_type == 'COLLECTION':
                for obj in particle_sys.instance_collection.objects:
                    particles.append(obj.name)

        progress_counter = 0
        # Main export loop
        for object_instance in depsgraph.object_instances:
            window_manager.progress_update(progress_counter)
            progress_counter += 1

            if self.use_selection:
                #skip if it's not selected or if it's an instance and the parent object is not selected
                if not object_instance.is_instance and not object_instance.object.original.select_get():
                    continue
                if (object_instance.is_instance and object_instance.object.parent
                    and not object_instance.object.parent.original.select_get()):
                    continue

            evaluated_obj = object_instance.object
            object_type = evaluated_obj.type
            #type: enum in [‘MESH’, ‘CURVE’, ‘SURFACE’, ‘META’, ‘FONT’, ‘ARMATURE’, ‘LATTICE’, ‘EMPTY’, ‘GPENCIL’, ‘CAMERA’, ‘LIGHT’, ‘SPEAKER’, ‘LIGHT_PROBE’], default ‘EMPTY’, (readonly)
            if evaluated_obj.hide_render or (object_instance.is_instance
                and evaluated_obj.parent and evaluated_obj.parent.original.hide_render):
                self.export_ctx.log("Object: {} is hidden for render. Ignoring it.".format(evaluated_obj.name), 'INFO')
                continue#ignore it since we don't want it rendered (TODO: hide_viewport)
            if object_type in {'MESH', 'FONT', 'SURFACE', 'META'}:
                geometry.export_object(object_instance, self.export_ctx, evaluated_obj.name in particles)
            elif object_type == 'CAMERA':
                # When rendering inside blender, export only the active camera
                if (self.render and evaluated_obj.name_full == b_scene.camera.name_full) or not self.render:
                    camera.export_camera(object_instance, b_scene, self.export_ctx)
            elif object_type == 'LIGHT':
                lights.export_light(object_instance, self.export_ctx)
            else:
                self.export_ctx.log("Object: %s of type '%s' is not supported!" % (evaluated_obj.name_full, object_type), 'WARN')

        if acoustic_mode:
            emitters = self.export_ctx.emitter_names()

            if not emitters:
                raise RuntimeError(
                    "This acoustic scene has no emitter. Add a point light, "
                    "or give a mesh an Emission material, and export again."
                )

            # Several sources sum into one energy-time curve, which is rarely
            # what a room measurement wants. The user can say they mean it,
            # and then switch between sources at render time instead.
            if len(emitters) > 1 and not self.allow_multiple_emitters:
                raise RuntimeError(
                    "This acoustic scene has %d emitters (%s). Their energy "
                    "sums into one energy-time curve. Tick Allow Multiple "
                    "Emitters to export anyway, or hide all but one source. "
                    "See %s"
                    % (len(emitters), ', '.join(sorted(emitters)),
                       docs.url('guide/exporting.html#multiple-emitters'))
                )

    def dict_to_xml(self):
        from misuka import parser, variant
        config = parser.ParserConfig(variant())
        state = parser.parse_dict(config, self.export_ctx.scene_data)
        parser.write_file(state, self.export_path)
        name_scene_plugins(self.export_path)

    def dict_to_scene(self):
        from misuka import load_dict
        return load_dict(self.export_ctx.scene_data)


def name_scene_plugins(path):
    """
    Give every plugin in the scene an `id` matching the name it was exported
    under.

    misuka's writer only emits an `id` for a plugin something else references,
    and writes the export name as a `name` attribute otherwise. Nothing reads
    that back: `mi.traverse()` keys such a plugin by its memory address, and
    the importer falls back to `_unnamed_<n>`. Copying the name across is what
    lets a script address a shape, a sensor or an emitter by the name it has in
    Blender.

    Only the direct children of `<scene>` are plugins in their own right. A
    nested element's `name` is the parameter it fills, such as the `bsdf` of a
    shape, so it is left alone.
    """
    # Scene children that declare something rather than instantiate a plugin.
    # `<default name="spp">` names a variable, not an object to address.
    not_plugins = {'default', 'alias', 'include', 'path', 'ref'}

    tree = ET.parse(path)
    root = tree.getroot()

    for element in root:
        if element.tag in not_plugins:
            continue
        name = element.get('name')
        if name is not None and element.get('id') is None:
            element.set('id', name)

    tree.write(path, encoding='utf-8', xml_declaration=False)
