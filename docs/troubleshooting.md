# Troubleshooting

## The add-on will not load

**"misuka dependencies not installed."**

Press **Install dependencies** in the add-on preferences.
See [Install the dependencies](installation.md#install-the-dependencies).

**"Failed to load custom misuka. Please verify the path to the build directory."**

The path does not point at the build directory, or the build was compiled against a different Python version than your Blender bundles.
See the [version matrix](installation.md#blender-and-python-versions).

**"Cannot activate misuka-blender add-on. Python pip module cannot be initialized."**

Your Blender build uses the system Python instead of bundling its own, so the add-on cannot install anything into it.
Install an official build from [blender.org](https://www.blender.org/download/).
See the warning at the top of [Installation](installation.md).

**"A restart is required to apply the changes."**

Restart Blender.

**The pip install fails**

A dialog shows pip's own error output and offers to retry from TestPyPI.
See [Install the dependencies](installation.md#install-the-dependencies).

**Any other status line**

See [Reading the status line](installation.md#reading-the-status-line).

(acoustic-panels-missing)=
## The acoustic panels are missing

**Check the render engine first.** Every acoustic panel only draws under **misuka**.
Set **Properties** > **Render** > **Render Engine** to **misuka** and they appear.
Under EEVEE or Cycles there is nothing to find, and an export is refused as well.

With the engine set:

- **Acoustic Format** is in **Properties** > **Output**, at the bottom of the tab.
  Blender draws add-on panels after its own, so it sits below the Format, Frame Range and Output panels rather than beside them.
- **Acoustic Material** needs an active material.
  Select an object, open **Properties** > **Material**, and add a material if there is none.
  Under misuka that tab draws its own material slot list, so you can add a first material there like you would under any other engine.
- **Integrator**, which carries **Samples**, is in **Properties** > **Render**.

## Database problems

**"No API Key set in Addon Preferences"**

Get a key from [acousticindex.com/api](https://acousticindex.com/api) and paste it into the add-on preferences.
See [Set the API key](guide/acousticindex.md#set-the-api-key).

**"No Acoustic Index material found."**

Rename the material to match the database entry, or paste the entry's ID as the name.
See [How the lookup works](guide/acousticindex.md#how-the-lookup-works).

**Any other database message**

See [Errors](guide/acousticindex.md#errors) and [Messages](guide/acousticindex.md#messages).

**The status box says 'Loaded for "..."'**

You renamed the material after loading.
See [The status box](guide/acousticindex.md#the-status-box).

## Coefficient problems

**Interpolate says "Tick at least one band first"**

Interpolation needs at least one anchor.
Tick a Keep box, or type a value into a band, which ticks it for you.
See [Interpolate](guide/acoustic-materials.md#interpolate).

**Rows are greyed out**

The scene is in Octave mode, so the 20 third-octave-only rows are inactive.
Their values are still there.
See [Band Resolution](guide/scene-settings.md#band-resolution).

**"Variant has third-octave data. Set Band Resolution to Third Octave in Output properties to simulate it"**

Every value is in the table, but only the 10 octave bands are exported until you switch resolution.
See [Apply Variant](guide/acousticindex.md#apply-variant).

**"Variant applied, N value(s) outside the band table ignored"**

The variant reported frequencies that do not line up with any of the standard bands.
See [Band matching](reference/acoustic-bands.md#band-matching).

**Absorption above 1**

Allowed, up to 2, because measured Sabine absorption coefficients do exceed 1.
See [Absorption](guide/acoustic-materials.md#absorption).

## Export problems

**"A misuka export needs the misuka render engine"**

Set **Properties** > **Render** > **Render Engine** to **misuka**.
Both export modes read settings that only exist under that engine.
See [Export Mode](guide/exporting.md#export-mode).

**"This acoustic scene has no emitter"**

Add a point light, give a mesh an Emission material, or color the world background.
A scene lit only by sun, spot or area lights ends up here, because an Acoustic export skips all three.
See [Exactly one emitter](guide/exporting.md#exactly-one-emitter) and [Lights](reference/supported-features.md#lights).

**"This acoustic scene has N emitters"**

Leave one and untick **Renders** for the rest, under **Show In** in **Properties** > **Object** > **Visibility**.
Watch for the world: a background you have colored counts as an emitter.
See [Exactly one emitter](guide/exporting.md#exactly-one-emitter).

**"Name 'X' contains a '.', which misuka reserves as a path delimiter"**

Nothing is broken.
Only the ids inside the XML change, not your Blender names.
See [Dots in names](guide/exporting.md#dots-in-names).

**An object is missing from the export**

Check Blender's console for the reason it was skipped.
See [What gets skipped](guide/exporting.md#what-gets-skipped).

**A material came out as plain grey**

The exporter could not convert its shader node and fell back to `diffuse`.
The console says which node type it choked on.
This affects Visual exports only.
In Acoustic mode the node tree is irrelevant.

**One input of a material was ignored**

Look for `Node type X is not supported for the 'Y' input of 'Z'` in the console.
That input took the value Blender shows when nothing is plugged in.
See [Texture inputs](reference/plugin-mapping.md#texture-inputs) for which nodes an input accepts.

**A texture came out too dark**

Its color space is one the exporter does not know, so it was read as sRGB and gamma decoded a second time.
The console names the image and the color space.
Set the image to `sRGB`, or to one of `Non-Color`, `Raw`, `Linear`, `Linear Rec.709` or `Linear BT.709`.

**The room looks wrong around the acoustic emitter**

Check the point light's **Radius** in **Object Data Properties** > **Light / Emitter**.
In Acoustic mode that value is the radius of the emitter sphere, and nothing caps it.
See [Radius limits](reference/plugin-mapping.md#radius-limits).

**The acoustic emitter is far too loud or too quiet**

Set the light's **Power** in **Object Data Properties** > **Light / Emitter**.
That is the only thing that changes the level, and it goes over in watts.
Changing the radius does not change the level.

**The Ignore Default Background checkbox does nothing**

Correct.
The exporter always ignores Blender's default grey world background, whatever the checkbox says.

## Import problems

**"Failed to load misuka scene. See error log."**

Open Blender's console for the detail.
Usually an unsupported plugin.
See [Messages](guide/importing.md#messages).

**Acoustic materials did not come back**

They do not.
See [Acoustic scenes](guide/importing.md#acoustic-scenes).

**The integrator is wrong after importing**

A scene whose integrator the importer does not recognize leaves the property at its default, `acoustic_path`.
Set it explicitly before a visual re-export.

## Where the console is

**Windows**: **Window** > **Toggle System Console**.

**macOS and Linux**: start Blender from a terminal.
