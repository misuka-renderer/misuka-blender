![Addon Banner](res/banner.jpg)

# MISUKA Blender Add-on

This add-on extends the Mitsuba Blender add-on with support for MISUKA-based geometric acoustic simulation and acoustic scene export.

## Main Features

* **Acoustic scene export**: Export Blender scenes as MISUKA-compatible acoustic XML scenes.

* **Acoustic Mode**: Automatically replaces visual Mitsuba components with acoustic equivalents during export:
  - `path` → `acoustic_path`
  - `perspective` → `microphone`
  - `hdrfilm` → `tape`
  - point lights → sphere + area emitters
  - `principled_bsdf` → `acousticbsdf`

* **Acoustic material workflow**:
  - frequency-dependent absorption and scattering
  - octave-band editing inside Blender
  - interpolation and reset utilities
  - manual material input

* **AcousticIndex integration**:
  - API-based material lookup
  - automatic download of absorption/scattering data
  - third-octave to octave conversion
  - interpolation of incomplete datasets

* **Coordinate consistency**:
  Blender and MISUKA coordinates match by default (`Y Forward`, `Z Up`).

## Installation

- Install the original Mitsuba Blender add-on.
- Clone or download this repository.
- In Blender, go to **Edit** -> **Preferences** -> **Add-ons** -> **Install**.
- Select the ZIP archive.
- Enable the add-on.
- In the add-on preferences:
  - enable *Use custom Mitsuba path*
  - select the MISUKA build directory
  - optionally enter an AcousticIndex API key

## Requirements

- Blender `3.6+`
- MISUKA build with acoustic plugins enabled
- Compatible Mitsuba 3 build
