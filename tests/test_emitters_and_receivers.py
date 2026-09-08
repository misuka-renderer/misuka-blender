'''
Export coverage for scenes with several emitters and several receivers.

A room measurement runs from one emitter to one receiver, but the scene a user
builds rarely holds only one of each: several source positions, a grid of
receiver positions, and a source that is sometimes a loudspeaker mesh rather
than a point. These check that such a scene reaches the file whole, and that
misuka can load what was written.

The add-on has no receiver object of its own, so a receiver is a Blender
camera: an acoustic export writes it as a `microphone` sensor, a visual one as
a `perspective` sensor.
'''
import os
import xml.etree.ElementTree as ET

import bpy
import pytest

from fixtures import (
    ACOUSTIC_VARIANT,
    VISUAL_VARIANT,
    add_emission_mesh,
    add_point_light,
    add_receiver,
    misuka_variant,
    skip_on_windows,
)


@pytest.fixture
def scene():
    '''
    A scene of its own, so counting emitters and sensors sees only what the
    test put there.

    `read_factory_settings()` would be the obvious way to get a clean file, but
    it resets the preferences too and would switch the add-on off for the rest
    of the session.
    '''
    previous = bpy.context.window.scene
    sc = bpy.data.scenes.new('emitters_and_receivers')
    bpy.context.window.scene = sc
    sc.render.engine = 'MITSUBA'

    yield sc

    bpy.context.window.scene = previous
    bpy.data.scenes.remove(sc)


def add_room(name='Room'):
    '''A cube with a plain material, so the scene has something to reflect off.'''
    bpy.ops.mesh.primitive_cube_add(size=10)
    room = bpy.context.active_object
    room.name = name
    material = bpy.data.materials.new(f'{name}-surface')
    material.use_nodes = True
    room.data.materials.append(material)
    return room


def export(scene, tmp_path, export_mode, **kwargs):
    '''Export `scene` and return the parsed scene root.'''
    path = os.path.join(str(tmp_path), 'scene.xml')

    kwargs.setdefault('ignore_background', True)
    if export_mode == 'ACOUSTIC':
        kwargs.setdefault('allow_multiple_emitters', True)

    assert bpy.ops.export_scene.mitsuba(
        filepath=path, export_mode=export_mode, **kwargs) == {'FINISHED'}

    return path, ET.parse(path).getroot()


def ids(elements):
    return [element.get('id') for element in elements]


def radiance(emitter):
    '''The single value an acoustic area emitter radiates in every band.'''
    texture = emitter.find("texture[@name='radiance']")
    assert texture is not None, f'no radiance texture in {ET.tostring(emitter)}'
    return float(texture.find("float[@name='value']").get('value'))


def sample_count(root, sensor):
    '''
    What a sensor actually samples.

    misuka's writer hoists the first sensor's sample count into a `spp`
    default and leaves the rest literal, so the attribute alone is not the
    answer.
    '''
    value = sensor.find("sampler/integer[@name='sample_count']").get('value')
    if value.startswith('$'):
        return int(root.find(f"default[@name='{value[1:]}']").get('value'))
    return int(value)


#############################
##  Several emitters       ##
#############################

def test_each_point_emitter_gets_its_own_sphere(scene, tmp_path):
    '''
    A point light becomes a sphere carrying an area emitter, and two of them
    have to stay two, each at its own place and level.
    '''
    add_room()
    add_receiver()
    add_point_light(100.0, 0.5, location=(1.0, 0.0, 0.0)).name = 'Source_A'
    add_point_light(400.0, 0.5, location=(3.0, 0.0, 0.0)).name = 'Source_B'

    _, root = export(scene, tmp_path, 'ACOUSTIC')

    spheres = root.findall(".//shape[@type='sphere']")
    assert ids(spheres) == ['emit-Source_A', 'emit-Source_B']

    # Four times the power at the same radius is four times the radiance.
    levels = [radiance(sphere.find("emitter[@type='area']")) for sphere in spheres]
    assert levels[1] == pytest.approx(4.0 * levels[0])

    centers = [sphere.find("vector[@name='center']").get('x') for sphere in spheres]
    assert [float(x) for x in centers] == pytest.approx([1.0, 3.0])


def test_a_point_and_a_mesh_emitter_export_side_by_side(scene, tmp_path):
    '''
    A loudspeaker is a mesh and a source position is a point, and a scene may
    hold both. The two take different shapes in the file, so a scene mixing
    them is the case that catches an exporter handling only one.
    '''
    add_room()
    add_receiver()
    add_point_light(100.0, 0.5, location=(1.0, 0.0, 0.0)).name = 'Source'
    add_emission_mesh('Speaker', strength=3.0, location=(3.0, 0.0, 0.0))

    _, root = export(scene, tmp_path, 'ACOUSTIC')

    sphere = root.find(".//shape[@type='sphere'][@id='emit-Source']")
    assert sphere is not None, 'the point light did not export as a sphere'
    assert sphere.find("emitter[@type='area']") is not None

    speaker = root.find(".//shape[@type='ply'][@id='mesh-Speaker']")
    assert speaker is not None, 'the emission mesh did not export as a shape'
    assert radiance(speaker.find("emitter[@type='area']")) == pytest.approx(3.0)

    # The room reflects and does not emit, so it is the one shape without an
    # emitter on it.
    room = root.find(".//shape[@id='mesh-Room']")
    assert room.find("emitter") is None

    assert len(root.findall(".//shape/emitter[@type='area']")) == 2


def test_a_mesh_emitter_does_not_hide_a_point_light_in_a_visual_scene(scene, tmp_path):
    '''
    A visual export writes the two through different code paths: the point
    light becomes a top-level `point` emitter, the mesh keeps its area emitter.
    '''
    add_room()
    add_receiver()
    add_point_light(100.0, 0.5, location=(1.0, 0.0, 0.0)).name = 'Source'
    add_emission_mesh('Speaker', strength=3.0, location=(3.0, 0.0, 0.0))

    _, root = export(scene, tmp_path, 'VISUAL')

    assert ids(root.findall("emitter[@type='point']")) == ['emit-Source']
    assert root.find(".//shape[@id='mesh-Speaker']/emitter[@type='area']") is not None


def test_several_point_lights_stay_several_in_a_visual_scene(scene, tmp_path):
    add_room()
    add_receiver()
    add_point_light(100.0, 0.5, location=(1.0, 0.0, 0.0)).name = 'Source_A'
    add_point_light(100.0, 0.5, location=(3.0, 0.0, 0.0)).name = 'Source_B'

    _, root = export(scene, tmp_path, 'VISUAL')

    assert ids(root.findall("emitter[@type='point']")) == ['emit-Source_A', 'emit-Source_B']


#############################
##  Several receivers      ##
#############################

def test_each_receiver_becomes_its_own_microphone(scene, tmp_path):
    '''
    Measuring a room means recording it from several places at once. Every
    camera has to reach the file as a sensor of its own, under its own name.
    '''
    add_room()
    add_point_light(100.0, 0.5)
    add_receiver('Recv_A', location=(0.0, 1.0, 0.0))
    add_receiver('Recv_B', location=(0.0, 2.0, 0.0))
    add_receiver('Recv_C', location=(0.0, 3.0, 0.0))

    _, root = export(scene, tmp_path, 'ACOUSTIC')

    sensors = root.findall("sensor[@type='microphone']")
    assert ids(sensors) == ['Recv_A', 'Recv_B', 'Recv_C']

    origins = [
        sensor.find("transform/lookat").get('origin') for sensor in sensors
    ]
    assert len({origin for origin in origins}) == 3, \
        f'receivers share a position: {origins}'


def test_every_receiver_carries_a_tape_film(scene, tmp_path):
    '''
    An acoustic sensor records an energy-time curve, so a receiver without a
    tape film records nothing. Settings the second sensor loses are the easy
    thing to get wrong.
    '''
    add_room()
    add_point_light(100.0, 0.5)
    add_receiver('Recv_A', location=(0.0, 1.0, 0.0))
    add_receiver('Recv_B', location=(0.0, 2.0, 0.0))

    _, root = export(scene, tmp_path, 'ACOUSTIC')

    films = root.findall("sensor/film[@type='tape']")
    assert len(films) == 2

    bands = [film.find("string[@name='frequencies']").get('value') for film in films]
    assert bands[0] == bands[1], 'receivers disagree about the bands to simulate'

    bins = [int(film.find("integer[@name='time_bins']").get('value')) for film in films]
    assert bins[0] == bins[1]


def test_a_receiver_keeps_its_own_sampler_and_filter(scene, tmp_path):
    '''
    Sampler and reconstruction filter sit on the camera, not the scene, so two
    receivers can be set up differently. The exporter reads the active camera
    for some scene settings, and reading it here too would give every sensor
    the same numbers.
    '''
    add_room()
    add_point_light(100.0, 0.5)
    first = add_receiver('Recv_A', location=(0.0, 1.0, 0.0)).data.mitsuba
    second = add_receiver('Recv_B', location=(0.0, 2.0, 0.0)).data.mitsuba

    for settings, samples, stddev in ((first, 1024, 0.1), (second, 4096, 0.9)):
        getattr(settings.acoustic_samplers,
                settings.acoustic_sampler).sample_count = samples
        getattr(settings.acoustic_rfilters,
                settings.acoustic_rfilter).stddev = stddev

    _, root = export(scene, tmp_path, 'ACOUSTIC')

    sensors = root.findall("sensor[@type='microphone']")
    assert ids(sensors) == ['Recv_A', 'Recv_B']

    assert [sample_count(root, sensor) for sensor in sensors] == [1024, 4096]

    widths = [
        float(sensor.find("film/rfilter/float[@name='stddev']").get('value'))
        for sensor in sensors
    ]
    assert widths == pytest.approx([0.1, 0.9])


def test_each_receiver_becomes_its_own_perspective_sensor(scene, tmp_path):
    add_room()
    add_point_light(100.0, 0.5)
    add_receiver('Recv_A', location=(0.0, 1.0, 0.0))
    add_receiver('Recv_B', location=(0.0, 2.0, 0.0))

    _, root = export(scene, tmp_path, 'VISUAL')

    sensors = root.findall("sensor[@type='perspective']")
    assert ids(sensors) == ['Recv_A', 'Recv_B']
    assert len(root.findall("sensor/film[@type='hdrfilm']")) == 2


#############################
##  What misuka loads      ##
#############################

@skip_on_windows
def test_misuka_loads_a_scene_with_several_emitters_and_receivers(scene, tmp_path):
    '''
    The XML checks say what was written; this says misuka accepts it. Duplicate
    ids and a sensor misuka rejects both pass an XML check and fail here.
    '''
    from misuka import load_file

    add_room()
    add_point_light(100.0, 0.5, location=(1.0, 0.0, 0.0)).name = 'Source_A'
    add_point_light(200.0, 0.25, location=(2.0, 0.0, 0.0)).name = 'Source_B'
    add_emission_mesh('Speaker', strength=3.0, location=(3.0, 0.0, 0.0))
    add_receiver('Recv_A', location=(0.0, 1.0, 0.0))
    add_receiver('Recv_B', location=(0.0, 2.0, 0.0))

    path, _ = export(scene, tmp_path, 'ACOUSTIC')

    with misuka_variant(ACOUSTIC_VARIANT):
        mi_scene = load_file(path)

        assert str(mi_scene.integrator()).startswith('AcousticPathIntegrator')

        sensors = mi_scene.sensors()
        assert len(sensors) == 2, f'expected two receivers, got {len(sensors)}'
        for sensor in sensors:
            assert str(sensor).startswith('Microphone')
            assert str(sensor.film()).startswith('Tape')

        # Two point lights and the emission mesh.
        assert len(mi_scene.emitters()) == 3

        # The room, the two emitter spheres and the emitting mesh.
        assert len(mi_scene.shapes()) == 4


@skip_on_windows
def test_misuka_loads_a_visual_scene_with_several_emitters_and_receivers(scene, tmp_path):
    from misuka import load_file

    add_room()
    add_point_light(100.0, 0.5, location=(1.0, 0.0, 0.0)).name = 'Source_A'
    add_point_light(200.0, 0.5, location=(2.0, 0.0, 0.0)).name = 'Source_B'
    add_emission_mesh('Speaker', strength=3.0, location=(3.0, 0.0, 0.0))
    add_receiver('Recv_A', location=(0.0, 1.0, 0.0))
    add_receiver('Recv_B', location=(0.0, 2.0, 0.0))

    path, _ = export(scene, tmp_path, 'VISUAL')

    with misuka_variant(VISUAL_VARIANT):
        mi_scene = load_file(path)

        assert len(mi_scene.sensors()) == 2
        for sensor in mi_scene.sensors():
            assert str(sensor).startswith('PerspectiveCamera')

        # Two point emitters and the emitting mesh.
        assert len(mi_scene.emitters()) == 3
