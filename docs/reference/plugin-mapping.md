# Plugin mapping

What the exporter writes for each Blender component, in Visual mode and in Acoustic mode.

## Scene components

| Blender | Visual mode | Acoustic mode |
|---|---|---|
| Integrator | The one chosen under Visual | The one chosen under Acoustic, with `max_time` from the Output properties |
| Camera | `perspective` sensor | `microphone` sensor |
| Film | `hdrfilm`, with the reconstruction filter chosen under Visual | `tape`, with `time_bins`, `frequencies` and the reconstruction filter chosen under Acoustic |
| Principled BSDF | `principled` | `acousticbsdf`, wrapped in `twosided` |
| Emission material on a mesh | `area` emitter on the shape, with a black `diffuse` BSDF that makes it shadeless, and an RGB `radiance` | `area` emitter on the shape, with a `null` BSDF so the emitter does not absorb what reaches it, and a `uniform` `radiance` built from **Strength** alone |
| Point light | `point` emitter | `sphere` shape with an `area` emitter and a `null` BSDF |

## Objects

Exported as meshes:

- Mesh
- Text
- Surface (NURBS)
- Metaball

Everything else is skipped, which covers armatures, lattices, empties, grease pencil, speakers and light probes.
Meshes with no faces are skipped too.
See [What gets skipped](../guide/exporting.md#what-gets-skipped) for the warnings each one logs.

One mesh is written per material slot.
Instances and particles use a `shapegroup`.

Only one UV layer is exported.
If a mesh has several, the one set active for render is used and a warning is logged.
This affects visual exports only.

## Plugin ids

Every plugin in the exported file carries an `id` naming the Blender object it came from, in both modes:

| Plugin | id |
|---|---|
| Shape | `mesh-<object name>` |
| Point light | `emit-<light name>` |
| Camera | the camera's object name |
| World background | `World`, Visual mode only |
| Material | `mat-<material name>` |
| Integrator | `integrator` |

A mesh split across several material slots exports one shape per slot, named `mesh-<object name>-<material name>`, with a numeric suffix when two slots share a material.

The id is what a script addresses a plugin by after loading the file.
A `.` in a Blender name is rewritten to `_`, because misuka reserves it as a path delimiter.
See [Dots in names](../guide/exporting.md#dots-in-names).

## What each acoustic plugin does

`acoustic_path`

: Solves the room acoustic rendering equation, which is the rendering equation with the incident term evaluated at the retarded time.
Takes `max_time` in seconds.

`microphone`

: A receiver at a single point, defined by an origin and a direction.
It records energy across time and frequency, in place of a camera recording pixels.

`tape`

: Records the energy-time curve.
`frequencies` lists the band centers in Hz, `time_bins` discretizes propagation time.
The output tensor is shaped `(time_bins, frequencies, 1)`.

`acousticbsdf`

: The only material model in an acoustic scene.
Carries frequency-dependent `absorption` and `scattering` spectra, plus `specular_lobe_width`.

For the physics, see [Acoustic rendering](https://misuka.readthedocs.io/latest/src/key_topics/acoustic_rendering.html) in the misuka documentation.

## Lights

| Blender light | Visual mode | Acoustic mode |
|---|---|---|
| Point | `point` emitter | `sphere` with an `area` emitter |
| Sun | `directional` emitter | Skipped |
| Spot | `spot` emitter | Skipped |
| Area | `area` emitter on a rectangle or disk | Skipped |

Area lights support square, rectangle and disk shapes.
Ellipse shapes raise "Light shape: ELLIPSE is not supported."
This is a Visual-mode limit, since an area light never reaches Acoustic mode.

A non-zero soft shadow radius on a point or spot light is ignored in Visual mode, with a warning.
misuka's `point` and `spot` emitters have no size, so there is nothing to carry it over to.
On a point light in Acoustic mode it becomes the emitter sphere's radius.
See [Radius limits](#radius-limits).

### Why point lights become spheres

An acoustic emitter has a size.
The exporter turns a Blender point light into a `sphere` shape carrying an `area` emitter, with a `null` BSDF so the emitter itself does not reflect sound.

The sphere's radius comes from the light's **Radius**, in **Object Data Properties** > **Light / Emitter**.
If that is zero, the exporter falls back to `0.1` meters.

**Power** is the only input.
The light's **Color** is used in a Visual export and dropped here.
The Light / Emitter panel documents this next to the settings themselves.

Only a point light is converted this way.
The other three write radiance tinted by the light's color and shaped by its geometry, neither of which means anything to a sound simulation, so an Acoustic export skips them rather than exporting them wrong.
Each one logs a warning naming it:

> Light 'Sun' is a Sun light.
> An acoustic export only supports point lights, so it is skipped.
> Use a point light, or give a mesh an Emission material to emit from its surface.

Skipping every light this way can leave the scene with no emitter at all, which stops the export.
See [Multiple emitters](../guide/exporting.md#multiple-emitters).

### Radius limits

The exporter sets no minimum and no maximum of its own.
Any positive **Radius** is written straight through, however small, and only an exact zero gets the `0.1` meter fallback.

Blender sets the floor.
**Radius** cannot go below 0, so the exported radius is never negative.
The slider stops at 100 meters, but you can type a larger number and the exporter uses it.

So there is nothing to stop you from exporting an emitter the size of a building.
The sphere is real geometry in the scene: it has to fit inside the room, and the microphone (your active camera) has to stay outside it.
A sphere that swallows the microphone, or that pushes through the walls, gives a result that has little to do with the room.

The level does not change.
The sphere puts out exactly the light's **Power** in watts whatever its radius, the same total as Blender's point light.
Radius controls how big the emitter is, not the level it puts out.

## Materials in Acoustic mode

The coefficient table replaces the surface shader.
Any material that does not emit becomes an `acousticbsdf` built from the table, whatever its node tree.
Base color, roughness and textures are all ignored.
A material with **Use Nodes** off becomes one too, and so does a material the exporter could not read.

Emission is the exception.
A material that emits exports as an `area` emitter, so its acoustic coefficients are never read.
A Mix or an Add counts as emitting if either side does.
See [Emission materials](#emission-materials).

## Visual BSDF mapping

For Visual mode exports, these Cycles shader nodes are converted:

| Cycles node | misuka BSDF |
|---|---|
| Principled BSDF | `principled` |
| Diffuse BSDF | `diffuse`, or `roughdiffuse` when rough |
| Glossy BSDF | `conductor`, or `roughconductor` when rough |
| Glass BSDF | `dielectric`, or `roughdielectric` when rough |
| Emission | `area` emitter |
| Mix Shader | `blendbsdf`, or a mixed emitter |
| Add Shader | A BSDF plus an `area` emitter |

Every BSDF except a transmissive one is wrapped in `twosided`.

Anything else raises "Node type: X is not supported in misuka." and the object falls back to a plain `diffuse` material.

Limitations:

- Glass BSDF supports only the default IOR.
- Emission supports only the default strength and color.
  Drive it from the socket defaults, not from a linked node.
  In Acoustic mode a linked color is fine, since only strength is read.
- Add Shader works only as the final node, directly behind Material Output.
- Add Shader cannot add two BSDFs.
  Use a Mix Shader.
- Mix Shader cannot mix a BSDF with an emitter.
  Use an Add Shader.
- Mixing emitters requires a uniform weight.
- Rough Diffuse is exported as plain `diffuse`, and its alpha is ignored.

## Emission materials

### In Acoustic mode

An Acoustic export reads **Strength** and writes it as a `uniform` spectrum, so the emitter puts out that radiance in every band.

```xml
<shape type="ply">
    <string name="filename" value="meshes/sphere.ply"/>
    <bsdf type="null"/>

    <emitter type="area">
        <texture type="uniform" name="radiance">
            <float name="value" value="10"/>
        </texture>
    </emitter>
</shape>
```

**Strength** is exported to [radiance](https://pbr-book.org/3ed-2018/Color_and_Radiometry/Radiometry#x1-Radiance).
An `area` emitter of radiance `L` on a surface of area `A` puts out a power of `pi * A * L`, so the same **Strength** on a bigger mesh emits more total power.
**Strength** must be a plain value: when linked from another node it raises "Only default emitter strength value is supported."

**Color** is Visual-only and is ignored in acoustic mode.

### In Visual mode

The exporter attaches an `area` emitter to the shape itself and points its BSDF at a shared black `diffuse` called `empty-emitter-bsdf`, so the surface emits but does not reflect:

```xml
<shape type="ply">
    <string name="filename" value="meshes/EmissivePanel.ply"/>
    <ref name="bsdf" id="empty-emitter-bsdf"/>

    <emitter type="area">
        <rgb name="radiance" value="10 5 2.5"/>
    </emitter>
</shape>
```

`radiance` is the Emission node's **Color** multiplied by its **Strength**, here a Color of `1.0 0.5 0.25` and a Strength of `10`.
Both must be plain socket values here too.
Either one driven from another node raises "Only default emitter color is supported." or "Only default emitter strength value is supported.", and the material falls back to the magenta dummy.
A Color and Strength that multiply out to zero logs a warning and exports a black `diffuse` instead, since a zero emitter makes misuka fail.

## Texture inputs

| Cycles node | misuka |
|---|---|
| Image Texture | `bitmap` |
| Checker Texture | `checkerboard` |
| RGB | A constant spectrum |
| Color Attribute | `mesh_attribute` |

Float inputs accept only Image Texture.
Color inputs accept all four.

Any other node on an input is dropped, with a warning naming the node and the input:

> Node type X is not supported for the 'Y' input of 'Z'.
> Exporting the fallback value instead.

The fallback is the socket's own value, the one Blender shows when nothing is plugged in.
So an unsupported texture costs you that one input, not the whole material.

### Image Texture color spaces

`Non-Color`, `Raw`, `Linear`, `Linear Rec.709` and `Linear BT.709` export with `raw` set, which tells misuka the pixels are already linear and must not be gamma decoded again.

Anything other than those and `sRGB` is read as sRGB, with a warning naming the image and its color space.
A linear image read as sRGB comes out too dark.

### Checker Texture

Blender checkers the 3D texture coordinates, which default to Generated: the object's bounding box, normalized. misuka checkers the UV coordinates.
The two agree only where the mesh is a single 0 to 1 unwrap, such as a plane.
Anywhere else the squares land in different places, and usually at a different size.

**Scale** is halved on the way over, because a misuka checkerboard has two squares per unit of UV where a Blender one has `Scale`.
That keeps the squares the same size wherever the two spaces agree.
A **Scale** of 0 exports as a solid **Color1**, which is what Blender paints.

Unwrap the mesh 0 to 1, or bake the checker to an image with Cycles and plug that in instead.

A linked **Vector** input is ignored, with a warning.
A linked **Scale** input falls back to its own value, with a warning.
