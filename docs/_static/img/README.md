# Screenshots

Seven screenshots are referenced by the docs, plus the misuka icon.
Each entry below names the file, where to capture it, and which page uses it.

The build runs with `-W`, so an image directive pointing at a missing file fails the build.
Add the entry here and the image directive to the page in the same change.

Capture the Blender screenshots at Blender's default theme and default UI scale, cropped to the panel with a little margin.
`acoustic-index-id.png` is a web page, not a Blender panel, so that rule does not apply to it.

The shoebox tutorial keeps its own screenshots in `docs/tutorials/shoebox-room/`, beside the scene files and the render script that produce three of them.

Set the render engine to **misuka** first, in **Properties** > **Render**.
The Acoustic Format and Acoustic Material panels do not draw under any other engine.

## `preferences.png`

**Edit** > **Preferences** > **Add-ons** > **misuka**, expanded.

Show: the status line with a green checkmark, the three dependency buttons, the **Advanced Settings** box with **Use custom misuka path** unticked, and the **Acoustic Index Database** box.
Blank the API key field.

Used by `docs/installation.md`.

## `engine-settings.png`

**Properties** > **Render**, with **Render Engine** on **misuka**.

Show: both the **Acoustic** and the **Visual** panel expanded, each with its **Integrator**, **Sampler** and **Reconstruction Filter** sub-panel open.
Leave every value at its default, so Acoustic reads Acoustic Path Tracer with a sample count of `262144` and Visual reads Path Tracer with `64`.
The point of the shot is that the two modes carry the same three settings side by side.

Used by `docs/guide/scene-settings.md`.

## `output-settings.png`

**Properties** > **Output** > **Acoustic Format**.

Show: **Band Resolution** on **Octave Bands**, the "10 bands, 31.5 Hz to 16 kHz" label, **Interpolation** on **Logarithmic**, **Max Time** `2.0`, **Sampling Rate** `1000`, and the "2000 time bins" label.

Used by `docs/guide/scene-settings.md` and `docs/tutorials/shoebox-room/shoebox-room.md`.

## `coefficients-panel.png`

**Properties** > **Material** > **Acoustic Material** > **Coefficients**, with the scene in **Octave Bands** mode.

Show: the greyed-out third-octave rows next to the active octave rows, several **Keep** boxes ticked with non-default values, and the **Interpolate** and **Reset to 0.5** buttons at the bottom.
Scroll so both the header row and the buttons are visible if it fits, otherwise favor the header and the ticked rows.

Used by `docs/guide/acoustic-materials.md`.

## `database-panel.png`

**Properties** > **Material** > **Acoustic Material** > **Acoustic Index Database**, after a successful **Load from Database**.

Show: the **Load from Database** button, the status box with the green **Matched Database Entry** line plus the label and manufacturer, and the **Variant Selection** dropdown open so several variants and their thickness/air-gap details are readable.

Used by `docs/guide/acousticindex.md`.

## `acoustic-index-id.png`

A product page on [Acoustic Index](https://acousticindex.com), with the developer view enabled in the account settings.

Show: the product title and manufacturer, and the **ID** field in the row of buttons below them, close enough to read the ID.
Use the same product as `database-panel.png`, so the two shots tell one story.

Used by `docs/guide/acousticindex.md`.

## `export-dialog.png`

**File** > **Export** > **misuka (.xml)**.

Show: the options column on the right, with **Export Mode** set to **Acoustic**, plus **Selection Only**, **Export IDs**, **Ignore Default Background**, **Forward Axis** and **Up Axis**.

Used by `docs/guide/exporting.md`.

## `misuka_icon.png`

Not a screenshot.
The misuka project's own icon, used as the sidebar logo and taken from the [misuka documentation](https://misuka.readthedocs.io/latest/) (`docs/images/misuka_icon_cropped.png` in `misuka-renderer/misuka`).
It is scaled the way the misuka docs scale it, see `docs/_static/custom.css`.
