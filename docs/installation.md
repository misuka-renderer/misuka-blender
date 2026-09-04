# Installation

## Requirements

Blender 3.6 or newer.
Tested up to 5.2.

:::{warning}

Your Blender build must bundle its own Python.
The official builds from blender.org do.
Some distribution packages do not, and build Blender against the system Python instead.
The Arch Linux `blender` package is the known case.

On such a build the add-on **cannot be enabled at all**.
Ticking its checkbox fails immediately with:

```
Cannot activate misuka-blender add-on. Python pip module cannot be initialized.
```

The cause is PEP 668: the system Python is marked as externally managed, so the add-on cannot install anything into it.

**Fix:** Use an official build from [blender.org](https://www.blender.org/download/).

:::

## Install the add-on

1. Download the latest ZIP from the [Releases page](https://github.com/misuka-renderer/misuka-blender/releases).
2. Either drag & drop the ZIP file into Blender, or:
   1. Open **Edit** > **Preferences** > **Add-ons** > **Install**.
   2. Select the ZIP you downloaded.
3. In the add-on preferences, tick the checkbox next to **misuka** to enable it.
4. Expand the add-on entry to reach its preferences.

```{image} _static/img/preferences.png
:alt: The misuka add-on preferences in Blender
:width: 80%
:align: center
```

## Install the dependencies

The add-on requires the `misuka` Python module.
The preferences show a status line at the top saying what is currently found.

There are two ways to supply the module.

### With pip

Press **Install dependencies**.
This installs the `misuka` module, version 0.1.0.


**Upgrade dependencies** Reinstalls the pinned version.
Use this when the status line says the found version is wrong.

**Uninstall dependencies** Removes the module.
This one needs a Blender restart to take effect.

:::{note}

If the pip install fails, a dialog appears showing pip's own error output.
It offers to retry with `misuka` taken from [TestPyPI](https://test.pypi.org/project/misuka/), where releases land before they reach PyPI.
Only `misuka` itself comes from TestPyPI.
Its dependencies still come from PyPI.

:::

### With a custom build

If you compiled misuka yourself:

1. In **Advanced Settings**, tick **Use custom misuka path**.
2. Set **Custom misuka path** to the *build* directory of your local build.
   If you set the path to the project root folder, misuka-blender will not find it.

A custom path wins over any pip install.
Toggling this setting requires a Blender restart.

:::{warning}

A custom build must be compiled against the same Python version that your Blender bundles.
See the [version matrix](#blender-and-python-versions) below.
A mismatch shows up as "Failed to load custom misuka. Please verify the path to the build directory."

:::

## Add an Acoustic Index API key

Optional, and only needed if you want to pull measured coefficients from [acousticindex.com](https://acousticindex.com).

First, get a key from [acousticindex.com/api](https://acousticindex.com/api).

In the preferences, find the **Acoustic Index Database** box and paste your key into **Acoustic Index API Key**.

Without a key, everything else still works.
You can still manually edit absorption and scattering coefficients yourself.
See [Acoustic export: shoebox room](tutorials/shoebox-room/shoebox-room.md).


(blender-and-python-versions)=
### Blender and Python versions

This only matters for the custom misuka path option.
A pip install always targets the right interpreter on its own.

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

## Update

1. Disable and remove the old add-on in **Edit** > **Preferences** > **Add-ons**.
2. Install the new ZIP the same way as before.
3. Restart Blender.

## Uninstall

1. Press **Uninstall dependencies** in the add-on preferences if you want the `misuka` module gone too.
2. Disable the add-on, then remove it.
3. Restart Blender.

## Reading the status line

The line at the top of the preferences carries either a red error icon or a green checkmark.
What it can say:

`misuka dependencies not installed.`

: Nothing found.
Press **Install dependencies**.

`Found pip misuka vX.`

: A pip install is in use.

`Found custom misuka vX. Supported version is v0.1.0.`

: A custom build is in use, and its version does not match what this add-on expects.

`Failed to load custom misuka. Please verify the path to the build directory.`

: The path is wrong, or the build was compiled against a different Python version.

`A restart is required to apply the changes.`

: Restart Blender.