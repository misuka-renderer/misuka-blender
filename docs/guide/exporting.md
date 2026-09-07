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

: Export an acoustic scene holding more than one source.
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

An acoustic export expects one emitter by default, because an energy-time curve runs from one source to one receiver.

Two things count as an emitter:

- A point light.
- A mesh with an Emission material.

A sun, spot or area light does not, and an acoustic export skips all three.
Neither does the world background.
See [The world background](#the-world-background).

With no source, the export stops with:

> This acoustic scene has no emitter.
> Add a point light, or give a mesh an Emission material, and export again.

With more than one, it stops and names them:

> This acoustic scene has 2 emitters (emit-Point, emit-Point_001).
> Their energy sums into one energy-time curve.
> Tick Allow Multiple Emitters to export anyway, or hide all but one source.

The names in that list are the exported ids, not the Blender names: a light is listed as `emit-<light name>` and an emitting mesh as `mesh-<object name>`.
See [Plugin ids](../reference/plugin-mapping.md#plugin-ids).

Objects disabled for render do not count, so you do not have to delete anything.
Untick **Renders**, under **Show In** in **Properties** > **Object** > **Visibility**, on every source but one.

### The world background

An acoustic export writes no world background, whatever the world is set to.

In Visual mode a colored world becomes a `constant` emitter surrounding the scene, and Blender's default grey one is skipped unless you untick **Ignore Default Background**.
In Acoustic mode neither happens.
A background emits from every direction at once and never reflects, so as a sound source it is a room with no walls rather than anything a measurement uses.

The console says so when the world would otherwise have been exported:

> An acoustic export skips the world background.

This is also why **Ignore Default Background** is greyed out under Acoustic.

### What several sources mean

Every source emits at once and their energy adds together, so the curve is the sum of all of them rather than the response of any one.
For a room measurement that is almost never what you want, and nothing in the result says it happened.

The export refuses it by default for that reason.
An export driven from Python is not refused, since a script asking for the export is taken to mean it.

### Exporting several sources on purpose

Tick **Allow Multiple Emitters** in the export options and every source is written to the file.
The warning stays in the panel, because the scene still holds several sources.

This is the way to avoid one file per source position.
Export once, then pick the source you want at render time by zeroing the radiance of the others:

```python
import misuka as mi

# optimize=False matters here, see below.
scene = mi.load_file('scene.xml', optimize=False)
params = mi.traverse(scene)

# Silence every source, then bring one back.
sources = [k for k in params.keys() if k.endswith('.emitter.radiance.value')]
for key in sources:
    params[key] = 0.0
params['emit-Source.emitter.radiance.value'] = 1.0
params.update()

etc = mi.render(scene)
```

The keys are the exported ids, which is why every plugin carries one.
Receivers need no such trick: export as many cameras as you like and choose one with `mi.render(scene, sensor=1)`.

:::{warning}

Pass `optimize=False` to `load_file`.

Loading a scene normally merges plugins that are identical, and two sources of the same **Power** export identical radiance.
They then share one parameter, so `sources` holds a single key and setting it to zero silences both.
Sources at the same level are the usual case, which is what makes this easy to walk into.

:::

## Dots in names

misuka reserves `.` as a delimiter in scene paths and rejects a key that has one.
Blender names every duplicate `Light.001`, so this comes up often.
The exporter rewrites the dot to `_` in the exported id and warns once per name:

> Name 'emit-Point.001' contains a '.', which misuka reserves as a path delimiter.
> Exporting it as 'emit-Point_001'.

The export succeeds.
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

## Progress

A progress bar runs while the scene is written.
When it finishes the status bar reports "Scene exported successfully!".

