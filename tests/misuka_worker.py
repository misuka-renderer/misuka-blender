'''
The misuka half of the tests, run outside Blender.

Instantiating a misuka scene inside `blender.exe` faults on Windows under
Blender 3.6, 4.2 and 4.5: misuka's build needs a newer Microsoft C++ runtime
than those ship in `blender.crt`, and Blender forces its own copy on everything
in its process. The fault kills the process, and pytest writes its report at the
end of a run, so one such test used to cost every other test's result.

Blender's own bundled `python.exe` is not subject to that. It sits outside
`blender.exe` and loads the system runtime, so it loads scenes happily on every
version. That is the whole trick: the tests still run inside Blender, because
they need `bpy` to build and export a scene, and hand the misuka half to the
interpreter Blender ships.

This module is the other side of that boundary. It imports misuka and never
imports `bpy`, so it runs under a plain Python. It is invoked as

    python tests/misuka_worker.py <command> <json>

and prints one JSON object on stdout. Renders are written to `.npy` files
rather than returned, because a tape or an image is too big to go through a
pipe comfortably; the caller reads them back and does the comparing, so the
aggregate maths lives in one place (`tests/shoebox.py`) rather than two.
'''
import json
import sys

# Kept in step with tests/shoebox.py, which this module must not import: that
# one is written for the process that has bpy, and this one runs without it.
VISUAL_VARIANT = 'scalar_rgb'


def _scene(xml_path, variant, optimize=True):
    import misuka as mi

    mi.set_variant(variant)
    return mi, mi.load_file(xml_path, optimize=optimize)


def inspect(xml_path, variant, optimize=True):
    '''What the scene holds, as names and counts rather than objects.'''
    mi, scene = _scene(xml_path, variant, optimize)

    radiance_keys = [k for k in mi.traverse(scene).keys()
                     if k.endswith('.emitter.radiance.value')]

    def first_line(obj):
        return str(obj).splitlines()[0]

    return {
        'integrator': first_line(scene.integrator()),
        'sensors': [first_line(s) for s in scene.sensors()],
        'films': [first_line(s.film()) for s in scene.sensors()],
        'emitter_count': len(scene.emitters()),
        'shape_count': len(scene.shapes()),
        'radiance_keys': radiance_keys,
    }


def render(xml_path, variant, out_path, spp, sensor=0, isolate_emitter=None,
           acoustic=False):
    '''
    Render one sensor and save the result to `out_path` as a .npy.

    `isolate_emitter` picks a single emitter by index, the way
    docs/guide/exporting.md describes: silence every radiance parameter, then
    restore one. That needs `optimize=False`, or emitters at equal levels share
    a parameter and zeroing it silences all of them.
    '''
    import numpy as np

    mi, scene = _scene(xml_path, variant, optimize=isolate_emitter is None)

    if isolate_emitter is not None:
        params = mi.traverse(scene)
        keys = [k for k in params.keys() if k.endswith('.emitter.radiance.value')]
        levels = [params[k] for k in keys]
        chosen = keys[isolate_emitter]
        for key, level in zip(keys, levels):
            params[key] = level if key == chosen else 0.0
        params.update()

    result = mi.render(scene, spp=spp, seed=0, sensor=sensor)

    if acoustic:
        # A tape comes back as (time bins, bands, 1); the suite works in
        # (bands, time bins).
        array = np.array(result)[..., 0].T
    else:
        array = np.array(result)[:, :, :3]

    np.save(out_path, array)
    return {'path': out_path, 'shape': list(array.shape)}


def read_exr(xml_path, variant, out_path):
    """Convert a stored .exr reference to .npy, since reading one needs misuka."""
    import misuka as mi
    import numpy as np

    mi.set_variant(variant)
    array = np.array(mi.Bitmap(xml_path))
    np.save(out_path, array)
    return {'path': out_path, 'shape': list(array.shape)}


def write_exr(npy_path, out_path):
    """Store a rendered image as .exr, so a failing test can be looked at."""
    import misuka as mi
    import numpy as np

    mi.set_variant(VISUAL_VARIANT)
    mi.Bitmap(np.load(npy_path)).write(out_path)
    return {'path': out_path}


COMMANDS = {'inspect': inspect, 'render': render, 'read_exr': read_exr,
            'write_exr': write_exr}


def main():
    if len(sys.argv) != 3:
        sys.exit('usage: misuka_worker.py <command> <json>')

    command, payload = sys.argv[1], json.loads(sys.argv[2])
    if command not in COMMANDS:
        sys.exit(f'unknown command {command!r}')

    # The result marker keeps this apart from anything misuka prints on the way
    # up, which would otherwise land in the middle of the JSON.
    print('__RESULT__' + json.dumps(COMMANDS[command](**payload)))


if __name__ == '__main__':
    main()
