# Importing

**File** > **Import** > **misuka (.xml)**.

Reads a misuka or mitsuba scene XML and builds the equivalent Blender scene.

## Options

**Override Current Scene**

: Default on.
Replaces the current scene's contents with the imported one.
Turn it off to put the imported objects into a new scene called `misuka` instead, leaving your current scene alone.

**Forward Axis** / **Up Axis**

: Default `-Z Forward` and `Y Up`, which is misuka's own convention.
These are the inverse of the export defaults, so a round trip lands where it started.

## What happens

The importer forces Object Mode, then converts each plugin it recognizes:

- Shapes become Blender objects.
- Sensors become cameras.
- Emitters become lights.
- BSDFs become Cycles node trees.
- Textures become image nodes.
- Environment and constant emitters become the Blender world.
- The integrator, sampler, reconstruction filter and film settings are written onto the Blender render settings, so a re-export reproduces them.

See [Supported features](../reference/supported-features.md) for the full list of recognized plugins.

## Acoustic scenes

Acoustic plugins are not imported back into the acoustic material panel.
There is no importer for `acousticbsdf`, `microphone` or `tape`.
The importer is for visual scenes and for the geometry of any scene.

`acoustic_path` is the default value of the integrator property, so a scene whose integrator the importer does not recognize leaves it there.
If you then export in Visual mode you will get the warning about the acoustic integrator.
Set the integrator explicitly before a visual re-export.

## Messages

`Scene imported successfully.`

: Done.

`Failed to load misuka scene. See error log.`

: Something went wrong.
The Blender console holds the detail.

`misuka class "X" not supported.`

: A whole plugin category the importer has no handler for.

`misuka Sensor type "X" not supported.`, `misuka Emitter type "X" not supported.`

: A specific plugin.
See [Supported features](../reference/supported-features.md).

`Multiple Blender worlds is not supported.`

: The scene has more than one environment emitter.
