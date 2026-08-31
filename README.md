# misuka Blender Add-on

![misuka Blender](res/banner_misuka.png)

| Blender 3.6 | Blender 4.2 | Blender 4.5 | Blender 5.2 |
|---|---|---|---|
| [![linux / Blender 3.6](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-linux-3.6.yml?branch=master&label=linux)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-linux-3.6.yml)<br>[![windows / Blender 3.6](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-windows-3.6.yml?branch=master&label=windows)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-windows-3.6.yml) | [![linux / Blender 4.2](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-linux-4.2.yml?branch=master&label=linux)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-linux-4.2.yml)<br>[![windows / Blender 4.2](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-windows-4.2.yml?branch=master&label=windows)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-windows-4.2.yml) | [![linux / Blender 4.5](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-linux-4.5.yml?branch=master&label=linux)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-linux-4.5.yml)<br>[![windows / Blender 4.5](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-windows-4.5.yml?branch=master&label=windows)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-windows-4.5.yml) | [![linux / Blender 5.2](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-linux-5.2.yml?branch=master&label=linux)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-linux-5.2.yml)<br>[![windows / Blender 5.2](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-windows-5.2.yml?branch=master&label=windows)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-windows-5.2.yml) |

This add-on is dedicated to importing and exporting Blender scenes from and to misuka.
It supports importing and exporting acoustic scenes that are compatible with misuka 0.1,
as well as visual scenes that are fully compatible with misuka 0.1 and mitsuba 3.9.1.
Rendering inside Blender is not supported.

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
  - editable absorption and scattering coefficients in octave-bands directly inside Blender
  - adjustable lobe width of the specular reflection component
  - interpolation and reset utilities
  - manual material input

- **AcousticIndex integration**:

  - API-based material lookup
  - automatic download of absorption and scattering coefficients
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
  - install dependencies, either
    - install misuka into Blender's python environment via `pip` with one click, or
    - set a custom misuka build path
  - optionally enter an AcousticIndex API key

The pip route also offers **Upgrade dependencies** and **Uninstall dependencies**.
Uninstalling needs a Blender restart to take effect, since the misuka module stays
loaded in the running interpreter.

If a pip install fails, a dialog shows pip's own error output and offers to retry
with misuka taken from [TestPyPI](https://test.pypi.org/project/misuka/), where
releases land before they reach PyPI. Only misuka itself comes from TestPyPI; its
dependencies are still installed from PyPI.

**Note:** if you use a custom misuka path, that build must have been compiled
against the same Python version as Blender's bundled Python interpreter (see table below).

## Requirements

- Blender `3.6+` (tested up to `5.2`)

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

## License

This add-on as a whole is distributed under the
[GNU General Public License v3.0 or later](LICENSE). Code inherited from the
`mitsuba-blender` add-on remains under its original BSD 3-Clause notice, and the
vendored Blender mesh importers under their original GPL-2.0-or-later notices.
See [NOTICE](NOTICE) for the details.
