# Getting started

A Blender add-on for room acoustics.
It exports Blender scenes to the [misuka renderer](https://github.com/misuka-renderer/misuka).

## Features

- **Export.** Export acoustic scenes to misuka and visual scenes to misuka or Mitsuba 3.9.
- **Editable acoustic material properties.** Edit absorption and scattering coefficients directly in Blender, in octave or third octave bands, with logarithmic and linear interpolation.
  Bands you set are marked, so measured values stay distinguishable from filled-in ones.
- **Acoustic Index lookup.** Name a material after a database entry on [acousticindex.com](https://acousticindex.com) and pull its measured coefficients straight into Blender.

<!-- Rendering inside Blender is not supported. -->

## Where to go next

- **Setting up:** [Installation](installation.md) covers the add-on, its dependencies, and the Acoustic Index API key.
- **Tutorials:** [Tutorials: Shoebox room](tutorials/shoebox-room/shoebox-room.md) builds a room and exports it in about ten minutes.
- **Guides:** [Scene settings](guide/scene-settings.md), [Acoustic materials](guide/acoustic-materials.md), [Acoustic Index](guide/acousticindex.md), [Exporting](guide/exporting.md) and [Importing](guide/importing.md) document every panel in detail.
  See [Troubleshooting](troubleshooting.md) if you run into problems.
- **Reference:** [Plugin Mapping](reference/plugin-mapping.md), [Supported Features](reference/supported-features.md), [Acoustic Bands](reference/acoustic-bands.md), document implementation details.
  See [Scripting](reference/scripting.md) if you want to use the Python API.
  See [Contributing](contributing.md) if you want to contribute to the project.

## Project links

- [Source code](https://github.com/misuka-renderer/misuka-blender)
- [Releases and downloads](https://github.com/misuka-renderer/misuka-blender/releases)
- [Issue tracker](https://github.com/misuka-renderer/misuka-blender/issues)

## License

This add-on is [GPL-3.0-or-later](https://github.com/misuka-renderer/misuka-blender/blob/master/LICENSE).
Inherited portions keep their own notices.
See [License](contributing.md#license).

The misuka renderer it exports to is licensed separately, under [PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0).
Because this add-on imports misuka, it is effectively restricted to noncommercial use as well.
Commercial use needs an agreement with the misuka maintainers.

```{toctree}
:maxdepth: 2
:hidden:

self
installation
```

```{toctree}
:maxdepth: 2
:caption: Tutorials
:hidden:

tutorials/shoebox-room/shoebox-room
```

```{toctree}
:maxdepth: 2
:caption: Guides
:hidden:

guide/scene-settings
guide/acoustic-materials
guide/acousticindex
guide/exporting
guide/importing
troubleshooting
```

```{toctree}
:maxdepth: 2
:caption: Reference
:hidden:

reference/plugin-mapping
reference/supported-features
reference/acoustic-bands
reference/scripting
contributing
```
