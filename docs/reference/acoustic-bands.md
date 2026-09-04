# Acoustic bands

Material coefficients are always stored on the full 30-band third-octave table, whatever the scene's [band resolution](../guide/scene-settings.md#band-resolution) is.
The band resolution decides which of them get simulated and exported.

The frequencies are the ISO 266 preferred center frequencies.

## The tables

30 third-octave centers, 25 Hz to 20 kHz.
The 10 octave centers are every third one, starting at 31.5 Hz, which is the one preferred center that is not a whole number.

| Center frequency in Hz | In octave mode |
|---|---|
| 25 |  |
| 31.5 | yes |
| 40 |  |
| 50 |  |
| 63 | yes |
| 80 |  |
| 100 |  |
| 125 | yes |
| 160 |  |
| 200 |  |
| 250 | yes |
| 315 |  |
| 400 |  |
| 500 | yes |
| 630 |  |
| 800 |  |
| 1000 | yes |
| 1250 |  |
| 1600 |  |
| 2000 | yes |
| 2500 |  |
| 3150 |  |
| 4000 | yes |
| 5000 |  |
| 6300 |  |
| 8000 | yes |
| 10000 |  |
| 12500 |  |
| 16000 | yes |
| 20000 |  |

The Blender property name of every band is in [Scripting](scripting.md).

## Band matching

Measured data does not always land on the preferred centers.
When a database variant is applied, each measured frequency is matched to the nearest one.
A near miss is accepted: a dataset reporting 3200 Hz lands on the 3150 Hz band.
A frequency too far from every center is ignored, counted, and reported as `N value(s) outside the band table ignored`.

## Interpolation

Interpolation fills the unkept bands from the kept ones.
The rules are at [Interpolate](../guide/acoustic-materials.md#interpolate), and the frequency axis they run along is [Interpolation](../guide/scene-settings.md#interpolation).
