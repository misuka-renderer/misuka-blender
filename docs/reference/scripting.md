# Scripting

The add-on stores everything the panels show on ordinary Blender properties, so a script can read and write it without touching the interface.
This page names them.

The panels are the normal way to work.
Reach for these when you are doing the same thing to many materials at once.

## Material properties

Every Blender material carries all 30 third-octave bands, whatever the scene's [band resolution](../guide/scene-settings.md#band-resolution) is.
The index column is the position in the band table, which is also the index into the Keep flags below.

| Index | Center frequency in Hz | Absorption | Scattering |
|---|---|---|---|
| 0 | 25 | `acoustic_abs_25` | `acoustic_scat_25` |
| 1 | 31.5 | `acoustic_abs_31_5` | `acoustic_scat_31_5` |
| 2 | 40 | `acoustic_abs_40` | `acoustic_scat_40` |
| 3 | 50 | `acoustic_abs_50` | `acoustic_scat_50` |
| 4 | 63 | `acoustic_abs_63` | `acoustic_scat_63` |
| 5 | 80 | `acoustic_abs_80` | `acoustic_scat_80` |
| 6 | 100 | `acoustic_abs_100` | `acoustic_scat_100` |
| 7 | 125 | `acoustic_abs_125` | `acoustic_scat_125` |
| 8 | 160 | `acoustic_abs_160` | `acoustic_scat_160` |
| 9 | 200 | `acoustic_abs_200` | `acoustic_scat_200` |
| 10 | 250 | `acoustic_abs_250` | `acoustic_scat_250` |
| 11 | 315 | `acoustic_abs_315` | `acoustic_scat_315` |
| 12 | 400 | `acoustic_abs_400` | `acoustic_scat_400` |
| 13 | 500 | `acoustic_abs_500` | `acoustic_scat_500` |
| 14 | 630 | `acoustic_abs_630` | `acoustic_scat_630` |
| 15 | 800 | `acoustic_abs_800` | `acoustic_scat_800` |
| 16 | 1000 | `acoustic_abs_1000` | `acoustic_scat_1000` |
| 17 | 1250 | `acoustic_abs_1250` | `acoustic_scat_1250` |
| 18 | 1600 | `acoustic_abs_1600` | `acoustic_scat_1600` |
| 19 | 2000 | `acoustic_abs_2000` | `acoustic_scat_2000` |
| 20 | 2500 | `acoustic_abs_2500` | `acoustic_scat_2500` |
| 21 | 3150 | `acoustic_abs_3150` | `acoustic_scat_3150` |
| 22 | 4000 | `acoustic_abs_4000` | `acoustic_scat_4000` |
| 23 | 5000 | `acoustic_abs_5000` | `acoustic_scat_5000` |
| 24 | 6300 | `acoustic_abs_6300` | `acoustic_scat_6300` |
| 25 | 8000 | `acoustic_abs_8000` | `acoustic_scat_8000` |
| 26 | 10000 | `acoustic_abs_10000` | `acoustic_scat_10000` |
| 27 | 12500 | `acoustic_abs_12500` | `acoustic_scat_12500` |
| 28 | 16000 | `acoustic_abs_16000` | `acoustic_scat_16000` |
| 29 | 20000 | `acoustic_abs_20000` | `acoustic_scat_20000` |

31.5 Hz is the one preferred center that is not a whole number.
A dot cannot appear in a Blender property name, so it becomes `31_5`.

Absorption accepts 0 to 2, scattering 0 to 1.
See [Acoustic bands](acoustic-bands.md) for what the table is.

### Keep flags

`acoustic_abs_keep`

: A 30-item boolean vector, one per band, in the order of the table above.
`True` means the value is claimed and Interpolate will not overwrite it.

`acoustic_scat_keep`

: The same for scattering.

:::{warning}

Writing a band value ticks its Keep box, the same as typing into the panel.
Set the flags after the values, not before.

:::

### Specular reflection

`acoustic_specular_lobe_width`

: Float, default `0.001`, range `0.001` to `1.0`.
See [Specular Reflection](../guide/acoustic-materials.md#specular-reflection).

## Scene properties

These live on `scene.mitsuba`, and they drive the [Acoustic Format](../guide/scene-settings.md) panel.

`acoustic_band_resolution`

: `'OCTAVE'` or `'THIRD_OCTAVE'`.
Default `'OCTAVE'`.

`acoustic_interpolation`

: `'LOG'` or `'LINEAR'`.
Default `'LOG'`.

`acoustic_max_time`

: Float, seconds.
Default `2.0`, minimum `0.001`.

`acoustic_sampling_rate`

: Float, Hz.
Default `1000.0`, minimum `1.0`.

## Camera properties

Each export mode has a sampler and a reconstruction filter of its own on the camera data, one pair per [panel](../guide/scene-settings.md#sampler).
Both start on `independent` and `gaussian`:

```python
mitsuba = camera.data.mitsuba
mitsuba.acoustic_samplers.independent.sample_count = 2**20
mitsuba.visual_samplers.independent.sample_count = 128
mitsuba.acoustic_rfilters.gaussian.stddev = 0.5
```

`acoustic_sampler` / `visual_sampler`

: `'independent'`, `'stratified'` or `'multijitter'`.
Both default `'independent'`.

`acoustic_samplers.<name>.sample_count`

: Integer, rays per frequency band.
Default `262144`, minimum `1`, maximum `2**32 - 1`.
See [Sampler](../guide/scene-settings.md#sampler).

`visual_samplers.<name>.sample_count`

: Integer, rays per pixel.
Default `64`, minimum `1`.

`acoustic_rfilter` / `visual_rfilter`

: `'box'`, `'tent'`, `'gaussian'`, `'mitchell'`, `'catmullrom'` or `'lanczos'`.
Both default `'gaussian'`, and each keeps its settings in `acoustic_rfilters` or `visual_rfilters`.

## Operators

Every button on the acoustic panels is an operator you can call.
They act on the active material, so set `context.material` or run them from a context where one is active.

| Operator | Button |
|---|---|
| `bpy.ops.acoustic.load_from_api()` | Load from Database |
| `bpy.ops.acoustic.apply_variant()` | Apply Variant |
| `bpy.ops.acoustic.interpolate_abs()` | Interpolate, under Absorption |
| `bpy.ops.acoustic.interpolate_scat()` | Interpolate, under Scattering |
| `bpy.ops.acoustic.reset_abs()` | Reset to 0.5, under Absorption |
| `bpy.ops.acoustic.reset_scat()` | Reset to 0.5, under Scattering |
| `bpy.ops.acoustic.reset_specular_lobe_width()` | Reset to 0.001 |

## Example

Set two absorption bands on every material in the scene, then interpolate the rest:

```python
import bpy

bpy.context.scene.mitsuba.acoustic_band_resolution = 'THIRD_OCTAVE'

for mat in bpy.data.materials:
    mat.acoustic_abs_125 = 0.1
    mat.acoustic_abs_4000 = 0.6

    with bpy.context.temp_override(material=mat):
        bpy.ops.acoustic.interpolate_abs()
```

Writing the two values ticks their Keep boxes, so Interpolate treats them as the anchors and fills everything else between them.

`temp_override` needs Blender 3.2 or newer.
