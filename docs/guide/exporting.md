# Exporting

**File** > **Export** > **misuka (.xml)**.

The exporter writes a misuka scene XML, with mesh data in binary PLY files beside it.

```{image} ../_static/img/export-dialog.png
:alt: The misuka export dialog with its options
:align: center
```

## Export Mode

Two whole scenes, not a modifier on one scene.

**Acoustic** (the default)

: An acoustic simulation.
The `acoustic_path` integrator, a `microphone` sensor, a `tape` film, and `acousticbsdf` materials.
Point lights become spheres with area emitters.

**Visual**

: An image render.
The integrator, sensor and materials chosen in the misuka panels.

Both modes need the **misuka** render engine.
Every setting an export writes lives on that engine, so an export from EEVEE or Cycles is refused:

> A misuka export needs the misuka render engine.
> Set Render Properties > Render Engine to misuka.

:::{note}

**Properties** > **Render** has a section per mode, **Acoustic** above **Visual**, with the same three panels under each:

- **Integrator**, starting on `acoustic_path` under Acoustic and `path` under Visual.
  Neither dropdown offers the other's integrators, so a mode cannot be pointed at one it would reject.
- **Sampler**, both starting on `independent`, each with a sample count of its own.
  See [Sampler](scene-settings.md#sampler).
- **Reconstruction Filter**, both starting on `gaussian` with a standard deviation of `0.25`.

Both sections are set up at once, so you can see what either export would write.

:::

See [Plugin mapping](../reference/plugin-mapping.md) for the full substitution table, and [Acoustic rendering](https://misuka.readthedocs.io/latest/src/key_topics/acoustic_rendering.html) in the misuka documentation for what these plugins do.

## Options

**Selection Only**

: Export only the selected objects.
Default off.

**Allow Multiple Emitters**

: Export an acoustic scene holding more than one emitter.
Default off, and Acoustic mode only.
A visual render is free to have several emitters, so the option is greyed out there.
See [Multiple emitters](#multiple-emitters).

**Ignore Default Background**

: Skip Blender's default constant grey world background.
Default on, and Visual mode only.
An acoustic export writes no background at all, so the option is greyed out there.
See [The world background](#the-world-background).

**Forward Axis** / **Up Axis**

: Default `Y` forward and `Z` up, which is what makes Blender and misuka coordinates agree.
Change these only when fitting an export into an existing scene that uses a different convention.

## What the acoustic scene contains

The full Blender-to-misuka substitution table is [Plugin mapping](../reference/plugin-mapping.md#scene-components).
Light handling is [Lights](../reference/supported-features.md#lights), and the emitter sphere's size is [Radius limits](../reference/plugin-mapping.md#radius-limits).

One value comes from outside those tables.
The sensor's sampler carries `sample_count` from the active camera's Sampler panel for that mode, defaulting to `262144` under Acoustic and `64` under Visual.
See [Sampler](scene-settings.md#sampler).

## Multiple emitters

An acoustic export expects one emitter by default, because an energy-time curve runs from one emitter to one receiver.

Two things count as an emitter:

- A point light.
- A mesh with an Emission material.

A sun, spot or area light does not, and an acoustic export skips all three.
Neither does the world background.
See [The world background](#the-world-background).

Objects disabled for render do not count, so you do not have to delete anything.
Untick **Renders**, under **Show In** in **Properties** > **Object** > **Visibility**, on every emitter but one.

### The world background

An acoustic export writes no world background, whatever the world is set to.

In Visual mode a colored world becomes a `constant` emitter surrounding the scene, and Blender's default grey one is skipped unless you untick **Ignore Default Background**.

### Why rendering multiple acoustic emitters is disabled by default

When a misuka scene contains multiple emitters, their contributions are simply added together.
When rendering energy impulse responses that is almost never what you want, so the export refuses it by default.
Scripted exports are executed literally and do not refuse multiple emitters.

### Exporting several emitters on purpose

If you want to render scenes with multiple emitter positions and only export them once, you can export all emitters at once and then pick the emitter you want at render time by zeroing the radiance of the others.
Tick **Allow Multiple Emitters** in the export options and every emitter is written to the file.
Then in python, set the radiance of all but one emitter to 0:

```python
import misuka as mi

# optimize=False matters here, see below.
scene = mi.load_file('scene.xml', optimize=False)
params = mi.traverse(scene)

# Silence every emitter, then bring one back.
emitters = [k for k in params.keys() if k.endswith('.emitter.radiance.value')]
for key in emitters:
    params[key] = 0.0
params['emit-Point.emitter.radiance.value'] = 1.0
params.update()

etc = mi.render(scene)
```

:::{warning}

Pass `optimize=False` to `load_file`.

Loading a scene normally merges plugins that are identical, and two emitters of the same **Power** export identical radiance.
They then share one parameter, so `emitters` holds a single key and setting it to zero silences both.
Emitters at the same level are the usual case, which is what makes this easy to walk into.

:::

## Multiple Receivers

Receivers need no such trick: export as many cameras as you like and choose one by passing a sensor index to the render function.

The following code renders the first receiver (index `0`).
`1` renders the second receiver, and so on.

```python
mi.render(scene, sensor=0)
```

## Dots in names

misuka reserves `.` as a delimiter in scene paths and rejects a key that has one.
Blender names every duplicate `Light.001`, so this comes up often.
The exporter rewrites the dot to `_` in the exported id and warns once per name.

Only the ids inside the XML change, not your Blender names.
Rename the object or material in Blender if you want the id to match exactly.

## What gets skipped

The exporter writes warnings to Blender's console rather than stopping, so a skipped object is easy to miss.
You only see them if Blender is showing its console: **Window** > **Toggle System Console** on Windows, or by starting Blender from a terminal on macOS and Linux.

Watch for:

`Object: X is hidden for render. Ignoring it.`

: Objects disabled for render are not exported.

`Object: X of type 'Y' is not supported!`

: See [Supported features](../reference/supported-features.md).

`Mesh: X has no faces. Skipping.`

: An empty mesh.

`Mesh: X has multiple UV layers. misuka only supports one. Exporting the one set active for render.`

: Only relevant to visual exports.

`Could not export 'X', light type Y is not supported`

: See [Supported features](../reference/supported-features.md).
