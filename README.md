# misuka Blender
![misuka Blender](res/banner_misuka.png)

| Blender 3.6 | Blender 4.2 | Blender 4.5 | Blender 5.2 |
|---|---|---|---|
| [![linux / Blender 3.6](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-linux-3.6.yml?branch=master&label=linux)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-linux-3.6.yml)<br>[![windows / Blender 3.6](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-windows-3.6.yml?branch=master&label=windows)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-windows-3.6.yml) | [![linux / Blender 4.2](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-linux-4.2.yml?branch=master&label=linux)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-linux-4.2.yml)<br>[![windows / Blender 4.2](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-windows-4.2.yml?branch=master&label=windows)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-windows-4.2.yml) | [![linux / Blender 4.5](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-linux-4.5.yml?branch=master&label=linux)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-linux-4.5.yml)<br>[![windows / Blender 4.5](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-windows-4.5.yml?branch=master&label=windows)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-windows-4.5.yml) | [![linux / Blender 5.2](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-linux-5.2.yml?branch=master&label=linux)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-linux-5.2.yml)<br>[![windows / Blender 5.2](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-windows-5.2.yml?branch=master&label=windows)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-windows-5.2.yml) |

This add-on extends the Mitsuba Blender add-on with support for misuka-based geometric acoustic simulation and acoustic scene export.

## Main Features

- **Acoustic scene export**: Export Blender scenes as misuka-compatible acoustic XML scenes.

- **Acoustic Mode**: Automatically replaces visual misuka components with acoustic equivalents during export:

  - `path` → `acoustic_path`
  - `perspective` → `microphone`
  - `hdrfilm` → `tape`
  - point lights → sphere + area emitters
  - `principled_bsdf` → `acousticbsdf`

- **Acoustic material workflow**:

  - frequency-dependent absorption and scattering
  - adjustable specular lobe width
  - octave-band editing inside Blender
  - interpolation and reset utilities
  - manual material input

- **AcousticIndex integration**:

  - API-based material lookup
  - automatic download of absorption/scattering data
  - third-octave to octave conversion
  - interpolation of incomplete datasets

- **Coordinate consistency**:
  Blender and misuka coordinates match by default (`Y Forward`, `Z Up`).

## Installation

- Download the latest ZIP archive from the GitHub Releases page.
- In Blender, go to **Edit** -> **Preferences** -> **Add-ons** -> **Install**.
- Select the downloaded ZIP archive.
- Enable the add-on.
- In the add-on preferences:
  - enable *Use custom misuka path*
  - select the misuka build directory
  - optionally enter an AcousticIndex API key

**Note:** if you use a custom misuka path, that build must have been compiled
against the same Python version as Blender's bundled Python interpreter (e.g.
Python 3.11 for Blender 4.2) — the native extension modules are ABI-locked to
a specific Python minor version and will fail to import otherwise.

## Requirements

- Blender `3.6+` (tested up to `5.2`; see Python version table below)
- misuka build with acoustic plugins enabled

### Blender / Python version matrix

The misuka build used with the *custom misuka path* option must be compiled
against the same Python version Blender bundles:

| Blender version | Python version |
|---|---|
| 3.6 LTS | 3.10 |
| 4.0 | 3.11 |
| 4.1 | 3.11 |
| 4.2 LTS | 3.11 |
| 4.3 | 3.11 |
| 4.4 | 3.11 |
| 4.5 LTS | 3.11 |
| 5.0 | 3.11 |
| 5.1 | 3.13 |
| 5.2 | 3.13 |

## Development status

This project was originally developed by Julius Schwarz, and has since been
updated for compatibility with misuka v0.1.0.
