# Exporting

**File** > **Export** > **misuka (.xml)**.

The exporter writes a misuka scene XML, with mesh data in binary PLY files beside it.

```{image} ../_static/img/export-dialog.png
:alt: The misuka export dialog with its options
:align: center
```

## Export Mode

The export dialog can be used to export to acoustic as well as visual scenes.

**Acoustic** (the default)

: An acoustic scene.
Uses the integrator chosen in the [rendering settings](./scene-settings.md#rendering-settings), a `microphone` sensor, a `tape` film, and `acousticbsdf` materials.
Point lights become spheres with `area` emitters.

**Visual**

: A visual scene.
Uses the integrator, sensor and materials chosen in the misuka panels.

Both modes need the **misuka** render engine.
Every setting an export writes lives on that engine, so an export from EEVEE or Cycles is refused.
See [Plugin mapping](../reference/plugin-mapping.md) for the full substitution table, and [Acoustic rendering](https://misuka.readthedocs.io/latest/src/key_topics/acoustic_rendering.html) in the misuka documentation for what these plugins do.

## Options

**Selection Only**

: Export only the selected objects.
Default off.

**Allow Multiple Emitters**

: Export an acoustic scene holding more than one emitter.
Default off, and Acoustic mode only.
A visual render is free to have several emitters, so the option is grayed out there.
See [Multiple emitters](#multiple-emitters).

**Ignore Default Background**

: Skip Blender's default constant gray world background.
Default on, and Visual mode only.
An acoustic export writes no background at all, so the option is grayed out there.
See [The world background](#the-world-background).

**Forward Axis** / **Up Axis**

: Default `Y` forward and `Z` up, which is what makes Blender and misuka coordinates agree.
Change these only when fitting an export into an existing scene that uses a different convention.

## Multiple emitters

An acoustic export expects one emitter by default, because an energy-time curve is commonly used to describe the propagation from one emitter to one receiver.

Two things count as an emitter in acoustic export mode:

- A point light.
- A mesh with an Emission material.

A sun, spot or area light does not, and an acoustic export skips all three.
Neither does the world background.

Objects disabled for render do not count, so you do not have to delete anything.
Untick **Renders**, under **Show In** in **Properties** > **Object** > **Visibility**, on every emitter but one.

### The world background

An acoustic export writes no world background, whatever the world is set to.

In Visual mode a colored world becomes a `constant` emitter surrounding the scene, and Blender's default gray one is skipped unless you untick **Ignore Default Background**.

### Why rendering multiple acoustic emitters is disabled by default

When a misuka scene contains multiple emitters, their contributions are added together.
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

## Multiple receivers

Receivers need no such trick: export as many cameras as you like and choose one by passing a sensor index to the render function.

`0` is the first receiver.

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
See [Where the console is](../troubleshooting.md#where-the-console-is).

`Object: X is hidden for render. Ignoring it.`

: Objects disabled for render are not exported.

`Object: X of type 'Y' is not supported!`

: See [Objects](../reference/plugin-mapping.md#objects).

`Mesh: X has no faces. Skipping.`

: An empty mesh.

`Mesh: X has multiple UV layers. misuka only supports one. Exporting the one set active for render.`

: Only relevant to visual exports.
