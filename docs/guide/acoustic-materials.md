# Acoustic materials

Every Blender material carries acoustic coefficients.
They live in **Properties** > **Material** > **Acoustic Material**, which holds three subpanels: **Acoustic Index Database**, **Coefficients** and **Specular Reflection**.

This page documents the controls.
For the order to use them in, see [Acoustic export: shoebox room](../tutorials/shoebox-room/shoebox-room.md).

The panel only draws under the **misuka** render engine.
See [The acoustic panels are missing](#acoustic-panels-missing).

:::{note}

The panel appears on every material, but an acoustic export only reads the coefficients of a material whose surface node is a **Principled BSDF**, which is what a new Blender material has.
Build one on a Diffuse BSDF or an Emission node and the export writes that node's visual BSDF instead, coefficients and all ignored.
See [Material nodes](../reference/supported-features.md#material-nodes).

:::

## The coefficient table

```{image} ../_static/img/coefficients-panel.png
:alt: The coefficients table with several bands ticked
:width: 60%
:align: center
```

Five columns, one row per band:

| Column | What it is |
|---|---|
| Frequency | The band center, from 25 Hz to 20 kHz |
| Keep | Whether this absorption value is claimed |
| Absorption | Fraction of incident sound energy absorbed |
| Keep | Whether this scattering value is claimed |
| Scattering | Fraction of reflected sound energy scattered |

All 30 rows are always shown.
In Octave mode the 20 rows that octave bands do not use are greyed out, but they keep their values.
Switching band resolution never loses anything.

You can drag a value down an aligned column to set several bands at once.

### Absorption

Fraction of incident sound energy absorbed at that band.
`0` reflects everything, `1` absorbs everything.

Range 0 to 2.
The slider stops at 1.0, but you can type higher.
Measured Sabine absorption coefficients do exceed 1.

### Scattering

Fraction of reflected sound energy scattered at that band.
`0` reflects like a mirror, `1` scatters in all directions.

Range 0 to 1.

### Keep

A per-band, per-quantity checkbox meaning "this value is claimed".
Either you set it, or a database variant measured it.

**Interpolate** preserves ticked bands and overwrites the rest.
That is the only thing Keep does.

Editing a band's value ticks its Keep box automatically.
Interpolate, Reset and Apply Variant set the boxes themselves.

Keep is your intent.
It is not a claim about the value being non-default: a band can be kept at `0.5`, and it will survive interpolation like any other.

## Interpolate

One button per quantity, at the bottom of its column.
Both ask for confirmation first.

It fills every **unticked** band by interpolating between the ticked ones, the anchors the result has to pass through:

- Bands between two ticked bands get a value interpolated between them.
- Bands below the lowest ticked band take that band's value.
- Bands above the highest ticked band take that band's value.
- Ticked bands are left alone.

There is no extrapolation.
Outside the ticked range the value goes flat.

The axis, logarithmic or linear, comes from **Interpolation** in the [Output properties](scene-settings.md#interpolation).

With nothing ticked, the operator reports `Tick at least one band first` and cancels.

## Reset to 0.5

One button per quantity.
Sets every band of that quantity back to `0.5` and unticks every Keep box.
Asks for confirmation.

`0.5` is a deliberate placeholder.
It carries no physical meaning.

(specular-reflection)=
## Specular Reflection

**Specular Lobe Width** sets the angular width of the specular reflection lobe.
Small values reflect like a mirror.
Larger ones spread the reflection out.

Default `0.001`, range `0.001` to `1.0`.
**Reset to 0.001** puts it back, with a confirmation.

This is a tuning control.
The default is the right starting point until you know what you want from it.
See [acousticbsdf](https://misuka.readthedocs.io/latest/src/generated/plugins_bsdfs.html#acoustic-material-acousticbsdf) in the misuka documentation for what it does physically.

## What gets exported

Exactly what the table shows, at the scene's band resolution.
Nothing is inferred at export time, and no interpolation happens behind your back.
Interpolation is a button you press.

For an Octave scene, the 10 octave rows are read and written.
For a Third Octave scene, all 30 are.
Values are rounded to three decimals in the XML.

A material with no values set still exports.
Every band sits at `0.5`, which is a half-absorbing, half-scattering surface.
That is rarely what you want, so it is worth checking every material before a real run.

The exported BSDF looks like this:

```xml
<bsdf type="twosided">
  <bsdf type="acousticbsdf">
    <spectrum name="absorption" value="31.5:0.1, 63:0.15, ..."/>
    <spectrum name="scattering" value="31.5:0.5, 63:0.5, ..."/>
    <float name="specular_lobe_width" value="0.001"/>
  </bsdf>
</bsdf>
```

The `twosided` wrapper is why face normal direction does not affect an acoustic export.
