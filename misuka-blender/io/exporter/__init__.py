import os

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

class SceneConverter:
    '''
    Converts a blender scene to a Mitsuba-compatible dict.
    Either save it as an XML or load it as a scene.
    '''
    def __init__(self, render=False):
        self.export_ctx = export_context.ExportContext()
        self.use_selection = False # Only export selection
        self.ignore_background = True
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

        # Enable useful IDs for acoustic scenes
        if acoustic_mode:
            self.export_ctx.export_ids = True

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

        #issue request: useful naming
        if acoustic_mode:
            self.export_ctx.data_add(integrator, name="integrator")
        else:
            self.export_ctx.data_add(integrator)

        # --- Rest of original exporter ---
        materials.export_world(self.export_ctx, b_scene.world, self.ignore_background)


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

            # An impulse response runs from one source to one receiver. Several
            # emitters would sum into a single response without saying so, so
            # the choice is left to the user rather than made for them.
            if len(emitters) > 1:
                raise RuntimeError(
                    "This acoustic scene has %d emitters (%s), and an impulse "
                    "response runs from one source. Leave one of them, and "
                    "hide or remove the rest."
                    % (len(emitters), ', '.join(sorted(emitters)))
                )

    def dict_to_xml(self):
        from misuka import parser, variant
        config = parser.ParserConfig(variant())
        state = parser.parse_dict(config, self.export_ctx.scene_data)
        parser.write_file(state, self.export_path)

    def dict_to_scene(self):
        from misuka import load_dict
        return load_dict(self.export_ctx.scene_data)
