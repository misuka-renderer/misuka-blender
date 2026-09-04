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
  See [Samples](scene-settings.md#samples).
- **Reconstruction Filter**, both starting on `gaussian` with a standard deviation of `0.25`.

Both sections are set up at once, so you can see what either export would write.

:::

See [Plugin mapping](../reference/plugin-mapping.md) for the full substitution table, and [Acoustic rendering](https://misuka.readthedocs.io/latest/src/key_topics/acoustic_rendering.html) in the misuka documentation for what these plugins do.

## Options

**Selection Only**

: Export only the selected objects.
Default off.

**Export IDs**

: Add an `id` field to every shape, emitter and sensor.
Default off, and forced on in Acoustic mode, where ids are how the scene is addressed.

**Ignore Default Background**

: Skip Blender's default constant grey world background.
Default on.

:::{warning}

This checkbox currently has no effect.
The exporter always ignores the default background, whatever the box says.
Unticking it does not export the grey world.

:::

**Forward Axis** / **Up Axis**

: Default `Y Forward` and `Z Up`, which is what makes Blender and misuka coordinates agree.
Change these only when fitting an export into an existing scene that uses a different convention.

## What the acoustic scene contains

The full Blender-to-misuka substitution table is [Plugin mapping](../reference/plugin-mapping.md#scene-components).
Light handling is [Lights](../reference/supported-features.md#lights), and the emitter sphere's size is [Radius limits](../reference/plugin-mapping.md#radius-limits).

One value comes from outside those tables.
The sensor's sampler carries `sample_count` from the active camera's Sampler panel for that mode, defaulting to `262144` under Acoustic and `64` under Visual.
See [Samples](scene-settings.md#samples).

## Exactly one emitter

An acoustic export needs one sound source and no more, because an energy-time curve runs from one source to one receiver.

Three things count as a source:

- A point light.
- A mesh with an Emission material.
- The world background, unless it is Blender's default grey.
  Change its color in **Properties** > **World** > **Surface** and it becomes a `constant` emitter that surrounds the scene.

A sun, spot or area light does not.
An acoustic export skips all three.

With no source, the export stops with:

> This acoustic scene has no emitter.
> Add a point light, or give a mesh an Emission material, and export again.

With more than one, it stops and names them:

> This acoustic scene has 2 emitters (emit-Point, emit-Point_001), and an impulse response runs from one source.
> Leave one of them, and hide or remove the rest.

The names in that list are the exported ids, not the Blender names: a light is listed as `emit-<light name>`, an emitting mesh under its own name, and the world background under the world's name.

Objects disabled for render do not count, so you do not have to delete anything.
Untick **Renders**, under **Show In** in **Properties** > **Object** > **Visibility**, on every source but one.

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
