# Scene settings

The acoustic scene settings live in **Properties** > **Output**, in a panel called **Acoustic Format**.
It is the acoustic counterpart to Blender's own Format panel.
Blender puts add-on panels after its own, so this one sits at the bottom of the tab.

```{image} ../_static/img/output-acoustic-film.png
:alt: The Acoustic Format panel in Output properties
:align: center
:width: 60%
```

:::{note}

This panel only draws under the **misuka** render engine, like the rest of the acoustic interface.
See [The acoustic panels are missing](#acoustic-panels-missing).

:::

## Band Resolution

Which frequency bands the simulation runs at.
Material coefficients are sampled at these centers.

**Octave Bands**

: The 10 octave centers, 31.5 Hz to 16 kHz.
The default.

**Third Octave Bands**

: All 30 third-octave centers, 25 Hz to 20 kHz.

A label below the dropdown confirms the choice, for example "10 bands, 31.5 Hz to 16 kHz".

Material values are always stored on the full 30-band third-octave table, whichever you pick.
Switching to Octave does not lose the third-octave values.
It greys their rows out in the coefficient table and leaves them there.

See [Acoustic bands](../reference/acoustic-bands.md) for both tables.

## Interpolation

The frequency axis that the material **Interpolate** buttons work along.

**Logarithmic**

: Interpolates along `log(frequency)`.
The default.

**Linear**

: Interpolates along frequency in Hz.

Logarithmic is the default because band centers are evenly spaced on that axis.
With anchors at 500 Hz and 2 kHz, the logarithmic axis puts 1 kHz exactly halfway between their values, while the linear axis puts it a third of the way.

Use Linear when your source data was tabulated that way.

This setting also affects **Apply Variant**, which interpolates the bands a database variant did not measure.

## Max Time

How long a tail the energy-time curve captures, in seconds.
Default `2.0`, minimum `0.001`.

This is also written into the exported `acoustic_path` integrator as its `max_time`.

Longer costs proportionally more time bins.

## Sampling Rate

How finely the energy-time curve is sampled in time, in Hz.
Default `1000.0`, minimum `1.0`.

:::{warning}

This is not an audio sample rate.
It does not need to be 44100 or 48000.
It is the time resolution of the energy-time curve, and 1000 Hz means one bin per millisecond.

:::

## Time bins

Not a setting.
A label at the bottom of the panel showing what Max Time and Sampling Rate work out to:

```
time_bins = round(max_time * sampling_rate)
```

with a floor of 1.

At the defaults, 2.0 seconds at 1000 Hz gives 2000 time bins.
The `tape` film's output tensor is then shaped `(2000, 10, 1)`: time bins, then frequencies.

## Samples

This one is not in the Output panel.
It is in **Properties** > **Render**, in the **Sampler** panel each export mode has of its own, and it belongs to the active camera rather than to the scene.

**Acoustic** > **Sampler** > **Sample Count**

: Rays traced per frequency band.
Default `262144`, which is `2**18`.
Minimum `1`.
The slider stops at `2**28`, and you can type up to `2**31 - 1`.

**Visual** > **Sampler** > **Sample Count**

: Rays traced per pixel.
Default `64`, minimum `1`.

An acoustic run needs far more samples than an image does, which is why the two panels are separate.
The same rays are spread over time bins and frequency bands, so a count that gives a clean image gives a noisy energy-time curve. misuka traces a square number of samples most efficiently, so use an even power of two: `2**18` is 512 squared, `2**20` is 1024 squared.

The export writes whichever count matches its mode into the exported scene as the sensor sampler's `sample_count`, so `mi.render(scene)` uses it.
Passing `spp` to `mi.render` overrides it.

:::{note}

The Sampler panels only exist under the **misuka** render engine, and so does the export that uses these counts.
See [The acoustic panels are missing](#acoustic-panels-missing).

:::
