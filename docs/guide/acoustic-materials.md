# Acoustic materials

Every Blender material carries acoustic coefficients.
They live in **Properties** > **Material** > **Acoustic Material**, which holds three subpanels: **Acoustic Index Database**, **Coefficients** and **Specular Reflection**.

:::{note}

This panel only draws under the **misuka** render engine.
See [The acoustic panels are missing](#acoustic-panels-missing).

:::

## The coefficient table

```{image} ../_static/img/coefficients-panel.png
:alt: The coefficients table with several bands ticked
:width: 60%
:align: center
```

In Octave mode the 20 rows that octave bands do not use are greyed out (see screenshot above), but they keep their values.
Switching band resolution never discards values.
You can drag a value down an aligned column to set several bands at once.

### Absorption coefficient

Fraction of incident sound energy absorbed at that band.
`0` reflects everything, `1` absorbs everything.

Range 0 to 1.
Values outside this range are clamped.

### Scattering coefficient

Fraction of reflected sound energy scattered at that band.
`0` reflects like a mirror, `1` scatters in all directions.

Range 0 to 1.
Values outside this range are clamped.

### Keep

A per-band, per-quantity checkbox meaning "this value is claimed".
**Interpolate** preserves ticked bands and overwrites the rest.

Editing a band's value ticks its Keep box automatically.
Interpolate, Reset and Apply Variant set the boxes themselves.

## Interpolate

One button per quantity, at the bottom of its column.

It fills every **unticked** band by interpolating between the ticked ones, the anchors the result has to pass through:

- Bands between two ticked bands get a value interpolated between them.
- Bands below the lowest ticked band take that band's value.
- Bands above the highest ticked band take that band's value.
- Ticked bands are left alone.

The axis, logarithmic or linear, comes from **Interpolation** in the [Output properties](scene-settings.md#interpolation).

## Reset to 0.5

One button per quantity.
Sets every band of that quantity back to `0.5` and unticks every Keep box.

(specular-reflection)=
## Specular Reflection

**Specular Lobe Width** sets the angular width of the specular reflection lobe.
See [acousticbsdf](https://misuka.readthedocs.io/latest/src/generated/plugins_bsdfs.html#acoustic-material-acousticbsdf) in the misuka documentation.

Default `0.001`, range `0.001` to `1.0`.

Leave this at the default value unless you know what you're doing.

## What gets exported

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

The `twosided` wrapper assigns the Acoustic BSDF to both sides of every surface.
You don't need to ensure that all normals point inward.

