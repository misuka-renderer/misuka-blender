# Supported features

## Export

### Objects

Exported as meshes:

- Mesh
- Text
- Surface (NURBS)
- Metaball

Everything else logs `Object: X of type 'Y' is not supported!` and is skipped.
That includes armatures, lattices, empties, grease pencil, speakers and light probes.

Objects disabled for render are skipped with `Object: X is hidden for render. Ignoring it.`

Meshes with no faces are skipped.

One mesh is written per material slot.
Instances and particles use a `shapegroup`.

:::{note}

Only one UV layer is exported.
If a mesh has several, the one set active for render is used and a warning is logged.
This affects visual exports only.

:::

### Material nodes

See [Plugin mapping](plugin-mapping.md#visual-bsdf-mapping) for the full table of supported shader nodes.

Limitations:

- Glass BSDF supports only the default IOR.
- Emission supports only the default strength and color.
  Drive it from the socket defaults, not from a linked node.
- Add Shader works only as the final node, directly behind Material Output.
- Add Shader cannot add two BSDFs.
  Use a Mix Shader.
- Mix Shader cannot mix a BSDF with an emitter.
  Use an Add Shader.
- Mixing emitters requires a uniform weight.
- Rough Diffuse is exported as plain `diffuse`, and its alpha is ignored.

A material whose **shader** node the converter cannot handle falls back to plain `diffuse` and logs why.

An unsupported node on an **input** costs only that input.
It falls back to the value Blender shows when nothing is plugged in, and logs a warning naming the node and the input.
The rest of the material still exports.

Texture nodes accepted on an input: Image Texture, Checker Texture, RGB and Color Attribute.
Float inputs, such as Roughness, Metallic and a Mix Shader's **Fac**, accept only Image Texture.
See [Texture inputs](plugin-mapping.md#texture-inputs).

**In Acoustic mode the coefficient table replaces the Principled BSDF.** A material whose surface node is a Principled BSDF becomes an `acousticbsdf` built from the table, and nothing else about its node tree matters: base color, roughness, textures are all ignored.

Other shader nodes are not substituted.
A Diffuse BSDF stays a `diffuse`, an Emission stays an `area` emitter, and a material with **Use Nodes** off stays a `diffuse` built from its viewport color.
Those materials carry acoustic coefficients in the panel, but an acoustic export never reads them.

So give every surface you want to hear a Principled BSDF, which is what a new Blender material has.

### Lights

| Blender light | Visual mode | Acoustic mode |
|---|---|---|
| Point | `point` emitter | `sphere` with an `area` emitter |
| Sun | `directional` emitter | Skipped |
| Spot | `spot` emitter | Skipped |
| Area | `area` emitter on a rectangle or disk | Skipped |

An acoustic source is a sphere carrying an `area` emitter, and only a point light builds one.
The other three write radiance tinted by the light's color and shaped by its geometry, neither of which means anything to a sound simulation, so an Acoustic export skips them rather than exporting them wrong.
Each one logs a warning naming it:

> Light 'Sun' is a Sun light.
> An acoustic export only supports point lights, so it is skipped.
> Use a point light, or give a mesh an Emission material to emit from its surface.

Skipping every light this way can leave the scene with no source at all, which stops the export.
See [Exactly one emitter](../guide/exporting.md#exactly-one-emitter).

Area lights support square, rectangle and disk shapes.
Ellipse shapes raise "Light shape: ELLIPSE is not supported."
This is a Visual-mode limit, since an area light never reaches Acoustic mode.

A non-zero soft shadow radius on a point or spot light is ignored in Visual mode, with a warning. misuka's `point` and `spot` emitters have no size, so there is nothing to carry it over to.
On a point light in Acoustic mode it becomes the emitter sphere's radius.
See [Radius limits](plugin-mapping.md#radius-limits).

A light type with no converter logs `Could not export 'X', light type Y is not supported`.
Blender has only the four types above, all of which convert, so this is a guard against a type a future Blender adds rather than something you can trigger today.

## Import

### Shapes

- `ply`
- `obj`
- `sphere`
- `disk`
- `rectangle`
- `cube`

`serialized` meshes are not imported.

### BSDFs

- `principled`
- `diffuse`
- `twosided`
- `dielectric`, `roughdielectric`, `thindielectric`
- `conductor`, `roughconductor`
- `plastic`, `roughplastic`
- `blendbsdf`
- `mask`
- `bumpmap`, `normalmap`
- `null`

`acousticbsdf` is **not** imported.
Acoustic materials do not round-trip back into the coefficient table.

### Sensors

- `perspective`

`microphone` is not imported.

### Emitters

- `point`
- `directional`

Environment and constant emitters become the Blender world.
A scene with more than one raises "Multiple Blender worlds is not supported."

### Textures

- `bitmap`

### Scene settings

The integrator, sampler, reconstruction filter and film settings are written onto the Blender render settings, so a re-export reproduces them.

Integrators known to the add-on: `acoustic_path`, `path`, `direct`, `aov`, `moment`, `stokes`, `depth`.

Samplers: `independent`, `stratified`, `multijitter`.
Each export mode picks its own, in its own panel, and keeps its own sample count for it.

Reconstruction filters: `box`, `tent`, `gaussian`, `mitchell`, `catmullrom`, `lanczos`.
Each export mode picks its own, in its own panel, and keeps its own settings for it.
Both start on `gaussian` with a standard deviation of `0.25`, which is a little sharper than misuka's own default.

:::{note}

The importer has no Blender equivalent for the `moment` integrator.
A scene using it keeps the property default, which is `acoustic_path`.
Set the integrator explicitly before a visual re-export.

:::
