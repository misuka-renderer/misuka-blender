# Acoustic Index

[acousticindex.com](https://acousticindex.com) is a database of measured acoustic material data.
The add-on can look a material up there and write its coefficients straight into Blender.
This feature is entirely optional.

```{figure} ../_static/img/database-panel.png
:alt: The Acoustic Index Database panel after a successful load
:width: 60%
:align: center

The Acoustic Index Database panel after a successful load
```

## Set the API key

First, get an API key from [acousticindex.com/api](https://acousticindex.com/api).

In Blender, **Edit** > **Preferences** > **Add-ons** > **misuka**, then paste your key into **Acoustic Index API Key**.

Without a key, **Load from Database** reports `No API Key set in Addon Preferences`.

## How the lookup works

The lookup uses the **Blender material's name**.

The add-on tries two things, in order:

1. Find an exact match for a product ID.
2. If no exact ID match is found, it searches product names and uses the top result.

To see product IDs on Acoustic Index, enable the developer view in the [Account Settings](https://acousticindex.com/konto/einstellungen).
This will show an `ID` field that you can copy to the clipboard.
The image below shows the product ID that was used to name the material in the screenshot above.

```{figure} ../_static/img/acoustic-index-id.png
:alt: The ID shown in the Acoustic Index Database
:width: 70%
:align: center

The ID shown in the Acoustic Index Database
```

Name your material after the product, or paste its Acoustic Index ID as the name.
Either works.

## Load from Database

Press it, and the add-on fetches the matched entry with every measured variant it holds.
It reports `N variants loaded`.

Absorption variants (measured to ISO 354) and scattering variants (measured to ISO 17497-1) arrive together in one list.
The dropdown starts on "Select a Variant".
A failed lookup keeps whatever was loaded before.

:::{note}

Currently, Acoustic Index only provides absorption measurements.
Type scattering coefficients in by hand.

:::

## The status box

Once a measurement is loaded, a box shows the entry's label and manufacturer, with one of three lines above it:

**Matched Database Entry**, green checkmark

: The loaded entry was looked up under the material's current name.

**Loaded for "..."**, info icon

: The material was renamed after loading.
The data is still valid, but it belongs to the name shown, not to the current one.
Press **Load from Database** again to look the new name up.

**Last lookup failed**, red error icon

: The most recent attempt failed.
Earlier data, if any, is untouched.

## Variants

One material can have several measured datasets.
They differ in sample thickness, air gap behind the sample, and which quantity was measured.

The **Variant Selection** dropdown shows each one as its label plus the details that separate it:

- `50mm`: sample thickness.
- `air 100mm`: air gap behind the sample.
- `a=0.85`: the calculated absorption.
  Absorption variants only.

Absorption and scattering are separate variants.
Apply one, then the other.

## Apply Variant

Writes the selected variant's measured values into the material's absorption or scattering coefficients.
A dialog confirms first, naming which quantity is about to be overwritten.

**Keep** is ticked on the bands the variant measured and unticked on every other one, so the panel keeps showing which numbers came from the lab.
The remaining bands are filled in using the scene's [interpolation axis](scene-settings.md#interpolation).

Third-octave data is kept at third-octave resolution.
It is never averaged down to octaves, even when the scene is in Octave mode.

Measured Sabine absorption coefficients can exceed 1, but misuka expects values between 0 and 1.
Values outside this range are clamped to this interval on import.

## Band matching

Measured data does not always land on the ISO 266 preferred center frequencies.
When a variant is applied, each measured frequency is matched to the nearest one.
A near miss is accepted: a dataset reporting 3200 Hz lands on the 3150 Hz band.
A frequency too far from every center is ignored, counted, and reported as `N value(s) outside the band table ignored`.

## Errors

`Not authorised: 401` or `Not authorised: 403`

: The API key is missing, wrong, or lacks access.

`No Acoustic Index material found.`

: Neither the id lookup nor the name search matched.
Check the material's name.

`API request failed: 5xx`

: An Acoustic Index server error.
Try again later.

`Search failed: N`

: The search endpoint rejected the request.

`Material name required.`

: The material's name is empty.

`No measurement data available.`

: The entry matched, but holds no ISO 354 or ISO 17497-1 measurements.
