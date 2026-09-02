'''
Tests for the material inputs of a visual export.

A node misuka has no texture for used to raise, and the exporter caught that by
replacing the whole material with the magenta dummy, so one unsupported texture
turned a whole object pink. See issue #23.

These run inside Blender with the addon enabled (see scripts/run_tests.py).
'''
import os
import xml.etree.ElementTree as ET

import bpy
import pytest


# What the exporter falls back to when it cannot read a material at all.
DUMMY_REFLECTANCE = [1.0, 0.0, 0.3]


@pytest.fixture
def mat():
    '''A material holding nothing but its output node.'''
    material = bpy.data.materials.new('visual_test')
    material.use_nodes = True
    for node in list(material.node_tree.nodes):
        if node.type != 'OUTPUT_MATERIAL':
            material.node_tree.nodes.remove(node)
    return material


def surface(mat, node_type):
    '''Add `node_type` as the surface shader of `mat`.'''
    nodes = mat.node_tree.nodes
    node = nodes.new(node_type)
    mat.node_tree.links.new(node.outputs[0], nodes['Material Output'].inputs['Surface'])
    return node


def feed(mat, node_type, socket, output='Color'):
    '''Add `node_type` and link its `output` into `socket`.'''
    node = mat.node_tree.nodes.new(node_type)
    mat.node_tree.links.new(node.outputs[output], socket)
    return node


def image(mat, socket, tmp_path, colorspace):
    '''Feed `socket` from an image texture saved in `colorspace`.'''
    img = bpy.data.images.new('visual_test', 4, 4)
    img.filepath_raw = os.path.join(str(tmp_path), 'visual_test.png')
    img.file_format = 'PNG'
    img.save()
    try:
        img.colorspace_settings.name = colorspace
    except TypeError:
        pytest.skip(f'this Blender has no {colorspace} colorspace')

    feed(mat, 'ShaderNodeTexImage', socket).image = img


def export_scene(mat, tmp_path):
    '''Export a single cube carrying `mat` and return the parsed scene root.'''
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    bpy.ops.mesh.primitive_cube_add()
    bpy.context.active_object.data.materials.append(mat)

    path = os.path.join(str(tmp_path), 'scene.xml')

    assert bpy.ops.export_scene.mitsuba(
        filepath=path, export_mode='VISUAL') == {'FINISHED'}

    return ET.parse(path).getroot()


def exported_bsdf(mat, tmp_path):
    '''Export `mat` and return its BSDF, unwrapped from its twosided shell.'''
    root = export_scene(mat, tmp_path)
    node = root.find(f".//bsdf[@id='mat-{mat.name}']")
    assert node is not None, f'no material {mat.name} in {ET.tostring(root)}'
    return node.find('bsdf') if node.get('type') == 'twosided' else node


def rgb(node, name):
    value = node.find(f"rgb[@name='{name}']")
    assert value is not None, f'no {name} color in {ET.tostring(node)}'
    return [float(v) for v in value.get('value').split()]


def number(node, name):
    value = node.find(f"float[@name='{name}']")
    assert value is not None, f'no {name} value in {ET.tostring(node)}'
    return float(value.get('value'))


def texture(node, name):
    value = node.find(f"texture[@name='{name}']")
    assert value is not None, f'no {name} texture in {ET.tostring(node)}'
    return value


def test_an_unsupported_color_node_costs_only_that_input(mat, tmp_path):
    '''The material used to be thrown away whole, dummy and all.'''
    diffuse = surface(mat, 'ShaderNodeBsdfDiffuse')
    diffuse.inputs['Color'].default_value = (0.2, 0.4, 0.6, 1.0)
    feed(mat, 'ShaderNodeTexBrick', diffuse.inputs['Color'])

    exported = exported_bsdf(mat, tmp_path)

    assert exported.get('type') == 'diffuse'
    assert rgb(exported, 'reflectance') == pytest.approx([0.2, 0.4, 0.6], abs=1e-6)


def test_an_unsupported_float_node_falls_back_to_the_socket(mat, tmp_path):
    glossy = surface(mat, 'ShaderNodeBsdfGlossy')
    glossy.inputs['Roughness'].default_value = 0.5
    feed(mat, 'ShaderNodeTexNoise', glossy.inputs['Roughness'], output='Fac')

    exported = exported_bsdf(mat, tmp_path)

    # Blender's roughness is remapped with a square root, as for an unlinked
    # socket, so 0.5 is 0.25 of misuka's alpha.
    assert number(exported, 'alpha') == pytest.approx(0.25, abs=1e-6)


def test_an_unsupported_shader_node_still_exports_the_dummy(mat, tmp_path):
    '''A material misuka has no BSDF for is a different matter: it stays pink.'''
    surface(mat, 'ShaderNodeBsdfTranslucent')

    exported = exported_bsdf(mat, tmp_path)

    assert rgb(exported, 'reflectance') == pytest.approx(DUMMY_REFLECTANCE, abs=1e-6)


def test_a_checker_texture_exports_as_a_checkerboard(mat, tmp_path):
    diffuse = surface(mat, 'ShaderNodeBsdfDiffuse')
    checker = feed(mat, 'ShaderNodeTexChecker', diffuse.inputs['Color'])
    checker.inputs['Color1'].default_value = (1.0, 0.0, 0.0, 1.0)
    checker.inputs['Color2'].default_value = (0.0, 0.0, 1.0, 1.0)
    checker.inputs['Scale'].default_value = 8.0

    exported = texture(exported_bsdf(mat, tmp_path), 'reflectance')

    assert exported.get('type') == 'checkerboard'
    assert rgb(exported, 'color0') == pytest.approx([1.0, 0.0, 0.0], abs=1e-6)
    assert rgb(exported, 'color1') == pytest.approx([0.0, 0.0, 1.0], abs=1e-6)

    # misuka checkers two squares per unit of UV, Blender `scale` of them, so
    # half the scale gives squares of the same size.
    scale = exported.find("transform[@name='to_uv']/scale")
    assert scale is not None, f'no to_uv transform in {ET.tostring(exported)}'
    assert float(scale.get('x')) == pytest.approx(4.0)
    assert float(scale.get('y')) == pytest.approx(4.0)


def test_a_checker_texture_without_a_scale_is_one_color(mat, tmp_path):
    '''Blender paints the whole surface in Color1 once the squares stop.'''
    diffuse = surface(mat, 'ShaderNodeBsdfDiffuse')
    checker = feed(mat, 'ShaderNodeTexChecker', diffuse.inputs['Color'])
    checker.inputs['Color1'].default_value = (1.0, 0.0, 0.0, 1.0)
    checker.inputs['Scale'].default_value = 0.0

    exported = exported_bsdf(mat, tmp_path)

    assert rgb(exported, 'reflectance') == pytest.approx([1.0, 0.0, 0.0], abs=1e-6)


def test_a_checker_texture_carries_a_nested_texture(mat, tmp_path):
    '''Both checker colors are inputs of their own.'''
    diffuse = surface(mat, 'ShaderNodeBsdfDiffuse')
    checker = feed(mat, 'ShaderNodeTexChecker', diffuse.inputs['Color'])
    image(mat, checker.inputs['Color1'], tmp_path, 'sRGB')

    exported = texture(exported_bsdf(mat, tmp_path), 'reflectance')

    assert texture(exported, 'color0').get('type') == 'bitmap'


@pytest.mark.parametrize('colorspace', ['Linear Rec.709', 'Non-Color'])
def test_a_linear_texture_is_not_decoded_as_srgb(mat, tmp_path, colorspace):
    '''
    'Linear' was renamed 'Linear Rec.709' in Blender 4.0. The old name was the
    only one the exporter knew, so a linear texture shipped without `raw` and
    misuka gamma decoded values that were already linear.
    '''
    diffuse = surface(mat, 'ShaderNodeBsdfDiffuse')
    image(mat, diffuse.inputs['Color'], tmp_path, colorspace)

    exported = texture(exported_bsdf(mat, tmp_path), 'reflectance')

    assert exported.get('type') == 'bitmap'
    assert exported.find("boolean[@name='raw']").get('value') == 'true'


def test_an_srgb_texture_is_still_decoded(mat, tmp_path):
    diffuse = surface(mat, 'ShaderNodeBsdfDiffuse')
    image(mat, diffuse.inputs['Color'], tmp_path, 'sRGB')

    exported = texture(exported_bsdf(mat, tmp_path), 'reflectance')

    assert exported.find("boolean[@name='raw']") is None
