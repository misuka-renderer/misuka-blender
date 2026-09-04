# Shoebox room

This builds a simple room and exports it as an acoustic scene.
It starts from Blender's default startup scene, so there is nothing to download.

You need the add-on installed and its dependencies working.
See [Installation](../../installation.md).

:::{note}

Shortcuts that differ by platform are written Windows and Linux first, then macOS: {kbd}`Alt+N`/{kbd}`⌥N`.
Every shortcut below also has a menu equivalent, named where it is used, so nothing here depends on one firing.

:::

## Make the room

The default startup scene already has a cube, a camera and a light.
First, we will scale up the cube and flip its normals so it becomes the room.

1. Select the cube.
2. Press {kbd}`S`, type `10`, press {kbd}`Enter`, or set **Scale** X, Y and Z to `10` in **Properties** > **Object** > **Transform**.
   The cube is now 20 meters across, since the default cube is 2 meters.
3. Optional: Enter Edit Mode with {kbd}`Tab`, select everything with {kbd}`A`, then open the Normals menu with {kbd}`Alt+N`/{kbd}`⌥N` and choose **Flip**, or use **Mesh** > **Normals** > **Flip**.
   Leave Edit Mode with {kbd}`Tab`.
   Enable **Backface Culling** in the Viewport Shading options.
   With the normals flipped, the near walls now disappear and you can look into the room from outside.
   This changes the Blender viewport only, not the export.

```{image} viewport-shading.png
:alt: The Acoustic Index Database panel after a successful load
:width: 40%
:align: center
```

:::{note}

Flipping the normals is **not** required for the export.
On export, misuka-blender will apply the material to both sides of surfaces.

:::

A room this size holds the startup scene's camera and light, so you do not have to move either one.
They are several meters apart, which is what you want.

## Switch the render engine to misuka

**Properties** > **Render** > **Render Engine** > **misuka**.

All acoustic setting are only visible when this render engine is selected, and an export from another engine is refused with:

> A misuka export needs the misuka render engine.
> Set Render Properties > Render Engine to misuka.

Switching the engine does not change your scene, but the Properties editor looks a little different under it:

- **Render** gains an **Acoustic** and a **Visual** section, each holding an **Integrator**, a **Sampler** and a **Reconstruction Filter** panel.
- **Output** gains **Acoustic Format**.
- **Object Data** shows **Light / Emitter** in place of Blender's Light panel.
- **Material** gains **Acoustic Material**, and its **Surface** panel offers Base Color only.

You can go back to EEVEE or Cycles at any point to preview visual renderings of the room, then switch back to export.

## Give the emitter a size

Select the light and open **Object Data Properties** > **Light / Emitter**.
Leave the type on **Point** and set **Radius** to `0.5` m.

The visual render does not change at all.
A visual export has no use for an emitter size, so it drops the value and says so in the console.

The acoustic render changes twice over, because the emitter is that sphere:

- **Less variance.** A bigger sphere is a bigger target, so more of the traced rays find it.
  The energy-time curve comes out smoother for the same sample count.
- **A wider direct sound peak.** Sound leaves every point of the sphere, so the shortest and longest paths to the microphone differ by about the sphere's diameter.
  One meter of path is about 3 milliseconds, which at the default 1000 Hz sampling rate spreads the direct sound over roughly three time bins instead of one.

That is the trade.
Take the smoother curve when you want the decay, keep the emitter small when you want the arrival times sharp.

## Move the emitter

Move the emitter to the scene origin.

1. Select the emitter
2. Move the mouse to the viewport, hold {kbd}`Shift+S` and select **Cursor to World Origin** with the mouse to move Blender's [3D Cursor](https://docs.blender.org/manual/en/latest/editors/3dview/3d_cursor.html) to the world origin {math}`(0, 0, 0)`.
3. Hold {kbd}`Shift+S` and select **Selection to Cursor** to move the emitter to the 3D Cursor.
4. Press {kbd}`0` on the numpad to align the viewport with the camera.
   If you don't have a numpad on your keyboard, enable [Emulate Numpad](https://docs.blender.org/manual/en/latest/editors/preferences/input.html#keyboard) in the settings.

Since the camera is pointed towards the origin in the default scene, the emitter should now be in direct view.

```{image} shoebox-emitter.png
:align: center
```

## Choose the band resolution

Open **Properties** > **Output**.
At the bottom, below Blender's own panels, is a panel called **Acoustic Format**.

1. Leave **Band Resolution** on **Octave Bands**.
2. Leave **Interpolation** on **Logarithmic**.
3. Leave **Max Time** at `2.0` seconds and **Sampling Rate** at `1000` Hz.

```{image} ../../_static/img/output-settings.png
:alt: The Acoustic Format panel in Output properties
:align: center
:width: 60%
```

For more information about these settings, see [Scene settings](../../guide/scene-settings.md).

## Give the room a material

1. Select the cube and open **Properties** > **Material**.
2. Add a material if the cube has none.
   The default startup cube usually has one already.
3. Find the **Acoustic Material** panel and expand **Coefficients**.

You get a table with one row per band.
The frequency is on the left, then **Absorption** and **Scattering** coefficients.
In Octave mode the rows that octave bands do not use are greyed out, but they keep their values.

Set two absorption values:

1. In the `125 Hz` row, set **Absorption** to `0.1`.
   Notice that its **Keep** box ticks itself.
2. In the `4000 Hz` row, set **Absorption** to `0.9`.
   Its **Keep** box ticks too.

Now press **Interpolate** under the Absorption column.
Every band that is not ticked gets a value interpolated between your two.
Bands below 125 Hz take `0.1`, bands above 4000 Hz take `0.6`.

Optional: Set scattering coefficients as well.

```{image} shoebox-material.png
:align: center
```

Leave **Specular Reflection** alone.
**Specular Lobe Width** is a tuning control, and the default is the right starting point until you know what you want from it.
See [Specular Reflection](../../guide/acoustic-materials.md#specular-reflection).

### Optional: Pull measured values from Acoustic Index

With an [acousticindex.com](https://acousticindex.com) API key you can load measured coefficients instead of typing them.
Name the material after the product name or ID, then press **Load from Database** and apply one of the variants it finds.
See [Acoustic Index](../../guide/acousticindex.md).

### Optional: Assign a texture to the material for visual export

1. Select the cube and open **Properties** > **Material** > **Surface**.
2. Change the Base Color to Checker Texture.
3. Set the Scale to 50.

:::{note}

The squares come out a different size than Blender draws them (visible in the Material Preview or Render view when changing the rendering engine to EEVEE or Cycles), because misuka checkers the local UV coordinates and Blender checkers the 3D texture coordinates.
See [Checker Texture](../../reference/plugin-mapping.md#checker-texture).

:::

```{image} shoebox-checkerboard.png
:align: center
```

(export-both-scenes)=
## Export both scenes

Export the same Blender scene twice, once in Acoustic mode and once in Visual mode.

### The acoustic scene

1. **File** > **Export** > **misuka (.xml)**.
2. In the options on the right, leave **Export Mode** on **Acoustic**.
3. Save it as `acoustic.xml` and press **misuka Export**.

### The visual scene

1. **File** > **Export** > **misuka (.xml)** again.
2. Set **Export Mode** to **Visual**.
3. Save it as `visual.xml`.

:::{note}

Nothing to set up first.
A Visual export reads the panels under **Visual** in the Render properties, which are already set up for an image, so the acoustic ones above them are left alone.
See [Exporting](../../guide/exporting.md#export-mode).

:::

## Check out the `.xml` files

The export generated two misuka scenes in the `.xml` file format.
See the [Mitsuba documentation](https://mitsuba.readthedocs.io/en/v3.9.1/src/key_topics/scene_format.html) for more information about the scene format.

`acoustic.xml` contains:

- An `acoustic_path` integrator with `max_time` set to your 2.0 seconds.
- A `microphone` sensor where your camera was.
- A `tape` film configured to store 2000 `time_bins` and a `frequencies` list holding the 10 octave centers.
- A `sphere` shape of radius 0.5 with an `area` emitter where your point light was.
- An `acousticbsdf` for your material, with an `absorption` and a `scattering` spectrum holding the 10 values the table showed.

`visual.xml` contains a `path` integrator, a `perspective` sensor, an `hdrfilm` and a `principled` BSDF instead.

Mesh data is written to binary PLY files beside the XML.
Both scenes reference the same PLY files, so keep them together.

## Render the scenes in misuka

Rendering happens in Python, outside Blender.
You need `misuka` plus [pyfar](https://pyfar.readthedocs.io/) for the acoustic plot:

```bash
python -m pip install misuka pyfar
```

Run this python code from the directory holding `acoustic.xml` and `visual.xml`:

```python
import misuka as mi
import pyfar as pf
import matplotlib.pyplot as plt
import xml.etree.ElementTree as ET

def read_sampling_rate(xml_path):
   '''Helper function to read the sampling rate from the xml file'''

   root = ET.parse(xml_path).getroot()

   max_time = float(root.find(".//integrator/float[@name='max_time']").get('value'))
   time_bins = int(root.find(".//film[@type='tape']/integer[@name='time_bins']").get('value'))

   return time_bins / max_time

def read_rendered_frequencies(xml_path):
    '''Helper function to read the rendered frequencies from the xml file.'''
    root = ET.parse(xml_path).getroot()
    element = root.find(".//film[@type='tape']/string[@name='frequencies']")
    if element is None:
        return []
    return [float(f) for f in element.get('value').split(',')]


# visual rendering
mi.set_variant('cuda_ad_rgb', 'metal_ad_rgb', 'llvm_ad_rgb')
scene = mi.load_file('visual.xml')
image = mi.render(scene, spp=16)

plt.figure()
plt.imshow(mi.util.convert_to_bitmap(image))
plt.axis('off')

# acoustic rendering
mi.set_variant('cuda_ad_acoustic', 'metal_ad_acoustic', 'llvm_ad_acoustic')
scene = mi.load_file('acoustic.xml')
sampling_rate = read_sampling_rate('acoustic.xml')

etc = mi.render(scene, spp=2**18)
etc = pf.Signal(etc.numpy()[..., 0].T, sampling_rate=sampling_rate)

plt.figure()
pf.plot.time(etc, log_prefix=10, dB=True)
plt.legend(read_rendered_frequencies('acoustic.xml'),
           title='Frequency in Hz',
           loc='upper right')
plt.show()
```

````{list-table}
:widths: 50 50
:class: borderless

* - ```{image} shoebox-visual.png
    :alt: Visual render
    ```
  - ```{image} shoebox-acoustic-light.png
    :alt: Acoustic render
    :class: only-light
    ```
    ```{image} shoebox-acoustic-dark.png
    :alt: Acoustic render
    :class: only-dark
    ```
````
Note how the point emitter is invisible in the visual rendering (it is placed right in the center of the image).
Point emitters are infinitely small, so the probability of a ray hitting them is 0.
In visual rendering, this is intended behavior.
In acoustic rendering, this would discard the direct sound contribution, which is not intended behavior in most cases


### Things worth knowing

- `set_variant` takes several names and uses the first one available.
  The same script runs on an NVIDIA GPU (`cuda`), on Apple silicon (`metal`) and on any CPU (`llvm`), picking the fastest each machine has.
- An acoustic scene needs an acoustic variant.
  `acoustic.xml` cannot be rendered with `rgb`, `mono` or `spectral`.
  Those read the frequency values in the spectra as wavelengths in nanometers, which is silently wrong rather than an error.
- The `tape` film's output is shaped `(time_bins, frequencies, 1)`.
  So `etc.numpy()[..., 0].T` gives `(frequencies, time_bins)`, which is 10 channels of 2000 samples, the shape `pf.Signal` wants.
- The `log_prefix` must be set to `10`. misuka renders an energy-time curve (ETC), which corresponds to the **squared** impulse response and is an energy quantity.
  Using the default of 20 will produce wrong decay tails.
  See the [misuka documentation](https://misuka.readthedocs.io/latest/src/key_topics/acoustic_rendering.html) for more information on acoustic rendering.
- Pass `spp=` to `mi.render` to override the number of rays used per pixel (visual) or per frequency (acoustic), or change the setting in Blender.
  When rendering images, misuka produces adequate quality at low values, even rendering with one ray per pixel produces noisy, but usable images.
  For acoustic rendering, the `spp` needs to be set much higher.
  Because a microphone is essentially a 1x1 pixel sensor, acoustic rendering is fast with `spp` values up to 1 million and more.
  See [Sampler](../../guide/scene-settings.md#sampler).
- A material with no acoustic values set still exports, with every band at `0.5`, which is a half-absorbing, half-scattering surface.
  That is rarely what you want, so check every material before a real run.























