from mathutils import Matrix
import numpy as np
from math import degrees

from ..acoustic_bands import resolution_frequencies

def export_camera(camera_instance, b_scene, export_ctx):    #camera

    #acoustic_mode for camera
    acoustic_mode = export_ctx.acoustic_mode
    b_camera = camera_instance.object
    params = {}

    if acoustic_mode:
        params['type'] = 'microphone'
    else:
        params['type'] = 'perspective'

        res_x = b_scene.render.resolution_x
        res_y = b_scene.render.resolution_y

        # Extract fov
        sensor_fit = b_camera.data.sensor_fit
        if sensor_fit == 'AUTO':
            params['fov_axis'] = 'x' if res_x >= res_y else 'y'
            params['fov'] = degrees(b_camera.data.angle_x)
        elif sensor_fit == 'HORIZONTAL':
            params['fov_axis'] = 'x'
            params['fov'] = degrees(b_camera.data.angle_x)
        elif sensor_fit == 'VERTICAL':
            params['fov_axis'] = 'y'
            params['fov'] = degrees(b_camera.data.angle_y)
        else:
            export_ctx.log(
                f"Unknown 'sensor_fit' value when exporting camera: {sensor_fit}",
                'ERROR'
            )

        params["principal_point_offset_x"] = (
            b_camera.data.shift_x / res_x * max(res_x, res_y)
        )
        params["principal_point_offset_y"] = (
            -b_camera.data.shift_y / res_y * max(res_x, res_y)
        )
        #TODO: test other parameters relevance (camera.lens, orthographic_scale, dof...)
        params['near_clip'] = b_camera.data.clip_start
        params['far_clip'] = b_camera.data.clip_end
        #TODO: check that distance units are consistent everywhere (e.g. mm everywhere)
        #TODO enable focus thin lens / cam.dof


    init_rot = Matrix.Rotation(np.pi, 4, 'Y')
    params['to_world'] = export_ctx.transform_matrix(b_camera.matrix_world @ init_rot)

    # An export needs the misuka engine, so the camera's own panels are always
    # the ones to read. They are settings rather than evaluated data, and the
    # depsgraph copy of them is stale until something tags the camera, so a
    # script that sets one and exports would otherwise write the old value.
    mts_camera = b_camera.original.data.mitsuba

    if acoustic_mode:
        sampler = getattr(
            mts_camera.acoustic_samplers,
            mts_camera.acoustic_sampler
        ).to_dict()
    else:
        sampler = getattr(
            mts_camera.visual_samplers,
            mts_camera.visual_sampler
        ).to_dict()

    params['sampler'] = sampler

    film = {}

    if acoustic_mode:
        film['type'] = 'tape'
        film['time_bins'] = export_ctx.acoustic_time_bins
        # The band centres the simulation runs at, and so the bands material
        # coefficients are sampled at.
        film['frequencies'] = ", ".join(
            str(f) for f in resolution_frequencies(export_ctx.acoustic_band_resolution)
        )
        film['rfilter'] = getattr(
            mts_camera.acoustic_rfilters,
            mts_camera.acoustic_rfilter
        ).to_dict()

    else:
        film['type'] = 'hdrfilm'

        scale = b_scene.render.resolution_percentage / 100
        film['width'] = int(res_x * scale)
        film['height'] = int(res_y * scale)

        film['rfilter'] = getattr(
            mts_camera.visual_rfilters,
            mts_camera.visual_rfilter
        ).to_dict()

    params['film'] = film

    if export_ctx.export_ids:
        export_ctx.data_add(params, name=b_camera.name_full)
    else:
        export_ctx.data_add(params)
