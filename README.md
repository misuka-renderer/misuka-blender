# misuka Blender Add-on

![misuka Blender](res/banner_misuka.png)

[![Documentation](https://img.shields.io/readthedocs/misuka-blender?label=docs)](https://misuka-blender.readthedocs.io/latest/)

| Blender 3.6 | Blender 4.2 | Blender 4.5 | Blender 5.2 |
|---|---|---|---|
| [![linux / Blender 3.6](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-linux-3.6.yml?branch=master&label=linux)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-linux-3.6.yml)<br>[![windows / Blender 3.6](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-windows-3.6.yml?branch=master&label=windows)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-windows-3.6.yml) | [![linux / Blender 4.2](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-linux-4.2.yml?branch=master&label=linux)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-linux-4.2.yml)<br>[![windows / Blender 4.2](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-windows-4.2.yml?branch=master&label=windows)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-windows-4.2.yml) | [![linux / Blender 4.5](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-linux-4.5.yml?branch=master&label=linux)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-linux-4.5.yml)<br>[![windows / Blender 4.5](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-windows-4.5.yml?branch=master&label=windows)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-windows-4.5.yml) | [![linux / Blender 5.2](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-linux-5.2.yml?branch=master&label=linux)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-linux-5.2.yml)<br>[![windows / Blender 5.2](https://img.shields.io/github/actions/workflow/status/misuka-renderer/misuka-blender/test-windows-5.2.yml?branch=master&label=windows)](https://github.com/misuka-renderer/misuka-blender/actions/workflows/test-windows-5.2.yml) |


A Blender add-on for room acoustics.
It exports Blender scenes to the misuka renderer, where materials carry frequency-dependent absorption and scattering and the result is an energy-time curve rather than an image.
It also imports and exports visual scenes compatible with misuka 0.1 and mitsuba 3.9.1.
Rendering inside Blender is not supported.

## Documentation

**[misuka-blender.readthedocs.io](https://misuka-blender.readthedocs.io/latest/)**

- [Installation](https://misuka-blender.readthedocs.io/latest/installation.html)
- [Acoustic export: shoebox room](https://misuka-blender.readthedocs.io/latest/tutorials/shoebox-room.html)
- [Scene settings](https://misuka-blender.readthedocs.io/latest/guide/scene-settings.html)
- [Contributing](https://misuka-blender.readthedocs.io/latest/contributing.html)

## Requirements

Blender `3.6+`, tested up to `5.2`.

## License

This add-on as a whole is distributed under the [GNU General Public License v3.0 or later](LICENSE).
Code inherited from the `mitsuba-blender` add-on remains under its original BSD 3-Clause notice, and the vendored Blender mesh importers under their original GPL-2.0-or-later notices.
See [NOTICE](NOTICE) for the details.

The misuka renderer it exports to is licensed separately, under [PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0).
Because this add-on imports misuka, it is effectively restricted to noncommercial use as well.
Commercial use needs an agreement with the misuka maintainers.
