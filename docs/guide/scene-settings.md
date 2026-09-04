# Scene settings

This page documents the UI settings inside Blender.

:::{note}

All panels listed here are only shown when the **misuka** render engine is selected.
See [The acoustic panels are missing](#acoustic-panels-missing).

:::


## Rendering settings

The rendering settings live in **Properties** > **Render**.
Each setting can be set independently for visual and acoustic export.

::: {note}

When rendering a misuka scene in Python, you can override all settings listed on this page.

```python
mi.render(scene, integrator=..., sensor=..., spp=...)
```
You can also override absorption and scattering spectra and replace materials entirely.
You can also modify the scene geometry by applying transformations, but you can not *replace* geometry objects from within Python.

:::

```{image} ../_static/img/engine-settings.png
:alt: The Acoustic Format panel in Output properties
:align: center
:width: 60%
```

### Integrator

The integrator misuka renders with.
The acoustic setting defaults to the [Acoustic Path Tracer](https://misuka.readthedocs.io/latest/src/generated/plugins_integrators.html#acoustic-path-tracer-acoustic-path).
The visual setting defaults to the [Path Tracer](https://mitsuba.readthedocs.io/en/latest/src/generated/plugins_integrators.html#path-tracer-path).

Each link documents that integrator's parameters.

### Sampler

The Sampler that generates the ray directions, as well as the number of rays used for rendering.

**Acoustic** > **Sampler** > **Sample Count**

: Rays traced per frequency band.
Default `262144`, which is `2**18`.
Minimum `1`.
The slider stops at `2**28`, and you can type up to `2**32 - 1`.

**Visual** > **Sampler** > **Sample Count**

: Rays traced per pixel.
Default `64`, minimum `1`.

An acoustic run needs far more samples than an image does, which is why the two panels are separate.
The ray contributions are spread over many time bins, so a sample count that gives a clean image can give a noisy energy-time curve.

### Reconstruction Filter

How the energy of one sample is spread over the bins next to the one it lands in.
See [Reconstruction filters](https://mitsuba.readthedocs.io/en/latest/src/generated/plugins_rfilters.html) for what each one does.

**Acoustic** > **Reconstruction Filter** > **Filter**

: Spreads each contributions over neighboring time bins.
You don't need this for forward rendering and can disable it by selecting the **Box** filter.
However, misuka needs a differentiable reconstruction filter in order to compute *derivatives* of moving geometry with respect to time.
The default, a Gaussian reconstruction filter with a standard deviation of 0.25 time bins enables these derivatives to be tracked and produces no significant smoothing.

**Visual** > **Reconstruction Filter** > **Filter**

: Spreads each sample over neighboring pixels, in both directions.


## Output settings

The output settings live in **Properties** > **Output**.
It is the acoustic counterpart to Blender's own Format panel.

```{image} ../_static/img/output-settings.png
:alt: The Acoustic Format panel in Output properties
:align: center
:width: 60%
```

## Band Resolution

Which frequency bands the simulation runs at.
Material coefficients are sampled at these centers.

**Octave Bands**

: The 10 octave centers, 31.5 Hz to 16 kHz.
The default.

**Third Octave Bands**

: All 30 third-octave centers, 25 Hz to 20 kHz.


Material values are always stored on the full 30-band third-octave table, whichever you pick.
Switching to Octave does not lose the third-octave values.
It greys their rows out in the coefficient table and leaves them there.

See [Acoustic bands](../reference/acoustic-bands.md) for the list of center frequencies.

::: {note}

In misuka, you can change the rendered frequencies to your choosing.
See [Tape](https://misuka.readthedocs.io/latest/src/generated/plugins_films.html#tape-tape).
Internally, the absorption and scattering spectra will then be interpolated linearly from the values stored in the xml file.
Logarithmic interpolation in misuka is planned, the progress is tracked in [#42](https://github.com/misuka-renderer/misuka/issues/42).

:::

## Interpolation

The frequency axis that the material **Interpolate** buttons work along.

**Logarithmic**

: Interpolates along `log(frequency)`.
The default.

**Linear**

: Interpolates along frequencies in Hz.

Logarithmic is the default because band centers are evenly spaced on that axis.
With anchors at 500 Hz and 2 kHz, the logarithmic axis puts 1 kHz exactly halfway between their values, while the linear axis puts it a third of the way.

## Max Time

The cut-off time for the simulated energy-time curve, in seconds.
Default `2.0`, minimum `0.001`.

This is also written into the exported `acoustic_path` integrator as its `max_time`.

## Sampling Rate

How finely the energy-time curve is sampled in time, in Hz.
Default `1000.0`, minimum `1.0`.

:::{warning}

This is not an audio sample rate.
It is the time resolution of the energy-time curve, and 1000 Hz means one bin per millisecond.
It does not need to be 44100 Hz or 48000 Hz.
In fact, a sampling rate that high will produce very noisy results without significant benefits for computing room acoustic parameters.

:::