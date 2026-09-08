import sys

import bpy
import pytest

####################################
##  Instantiating a misuka scene  ##
####################################

# misuka's Windows build needs a newer Microsoft C++ runtime than Blender 3.6,
# 4.2 and 4.5 ship in `blender.crt`, and Blender forces its own copy on
# everything running inside it. Instantiating a scene there dies with an access
# violation. Blender 5.2 ships a new enough runtime and is unaffected.
#
# `load_file` is enough to trigger it; rendering is not required. Exporting is
# not affected, so the tests that only write a scene run everywhere.
#
# This is a fault, not a failure. It kills the process, and pytest writes its
# JUnit report at the end of the run, so one unmarked test costs every other
# test's result rather than its own, so a test that instantiates a scene has to
# carry this whether or not anyone minds losing it.
# See https://github.com/misuka-renderer/misuka-blender/issues/4
skip_on_windows = pytest.mark.skipif(
    sys.platform == 'win32' and bpy.app.version < (5, 2, 0),
    reason='misuka faults when instantiating a scene under Blender < 5.2 on '
           'Windows. See '
           'https://github.com/misuka-renderer/misuka-blender/issues/4')

#############################
##  Building test scenes   ##
#############################

def add_point_light(power, radius, location=(0.0, 0.0, 0.0)):
    '''
    A point light, which an acoustic export writes as a sphere carrying an
    area emitter.
    '''
    bpy.ops.object.light_add(type='POINT', location=location)
    light = bpy.context.active_object
    light.data.energy = power
    light.data.shadow_soft_size = radius
    return light


def add_emission_mesh(name='Emitter', strength=1.0, location=(0.0, 0.0, 0.0)):
    '''A sphere carrying a material whose only shader is an Emission node.'''
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, location=location)
    mesh = bpy.context.active_object
    mesh.name = name

    emissive = bpy.data.materials.new(name)
    emissive.use_nodes = True
    tree = emissive.node_tree
    for node in list(tree.nodes):
        if node.type != 'OUTPUT_MATERIAL':
            tree.nodes.remove(node)
    emission = tree.nodes.new('ShaderNodeEmission')
    emission.inputs['Strength'].default_value = strength
    tree.links.new(emission.outputs[0],
                   tree.get_output_node('ALL').inputs['Surface'])
    mesh.data.materials.append(emissive)
    return mesh


def add_receiver(name=None, location=(0.0, 0.0, 0.0)):
    '''
    A camera, which an acoustic export writes as a microphone sensor. The
    add-on has no receiver object of its own.
    '''
    bpy.ops.object.camera_add(location=location)
    receiver = bpy.context.active_object
    if name is not None:
        receiver.name = name
    return receiver
