import bpy

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
