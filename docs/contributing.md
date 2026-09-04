# Contributing

Source: [misuka-renderer/misuka-blender](https://github.com/misuka-renderer/misuka-blender).

## Running the tests

The tests run **inside Blender**, with the add-on enabled.
`scripts/run_tests.py` symlinks the working copy into Blender's add-ons directory, enables it, and hands control to pytest.
On Windows it uses a directory junction instead of a symlink.

Blender's bundled Python needs `pytest` and the pinned `misuka` first:

```bash
BLENDER_PYTHON=/path/to/blender/python/bin/python3.11
uv pip install --python "$BLENDER_PYTHON" --upgrade pytest pytest-cov
uv pip install --python "$BLENDER_PYTHON" "misuka==0.1.0" --reinstall
```

Then run the suite:

```bash
/path/to/blender -b -noaudio --factory-startup \
  --python scripts/run_tests.py -- -v
```

Everything after `--` goes to pytest.

`scripts/blender_downloader.py` fetches a specific Blender version, which is how CI gets its matrix:

```bash
python scripts/blender_downloader.py 4.2 -o blender
```

:::{note}

Blender faults on Windows while tearing misuka down, after every test has already run.
See [issue #4](https://github.com/misuka-renderer/misuka-blender/issues/4).
CI judges the run on pytest's own report through `scripts/check_pytest_report.py`, not on Blender's exit code.

The same issue makes misuka fault on Windows as soon as a scene is instantiated, so tests that load an exported scene carry the `skip_on_windows` mark from `tests/fixtures/__init__.py`.
`tests/test_render_equivalence.py`, which renders the same scene in Cycles and in misuka and compares the two images, is skipped there in full.

:::

## Continuous integration

`.github/workflows/test-suite.yml` is the reusable workflow.
It runs on Linux and Windows against Blender 3.6, 4.2, 4.5 and 5.2.
One badge workflow per cell exists so the README table can show each combination separately.

:::{warning}

`DEPS_MITSUBA_VERSION` appears twice and the two must match: `misuka-blender/__init__.py` and `.github/workflows/test-suite.yml`.
The workflow says so in a comment.

:::

## Building these docs

The docs live in `docs/`, are written in [MyST Markdown](https://myst-parser.readthedocs.io/), and are built with Sphinx using the Furo theme.

```bash
uv venv
uv pip install -r docs/requirements.txt
uv run sphinx-build -W -b html docs docs/_build/html
```

Open `docs/_build/html/index.html`.

`-W` turns warnings into errors, matching `fail_on_warning: true` in `.readthedocs.yaml`.
A warning here is almost always a broken cross-reference or a page missing from a toctree, so catch it locally rather than on Read the Docs.

Check external links with:

```bash
uv run sphinx-build -b linkcheck docs docs/_build/linkcheck
```

Read the Docs builds `latest` from `master`, and builds a preview for every pull request.
`scripts/setup_readthedocs.sh` walks through the one-time project setup.

### Semantic line breaks

Every Markdown file under `docs/`, and the repository `README.md`, is formatted with [semantic line breaks](https://sembr.org/): one sentence per line, and no fixed line length.
Rendered output is unchanged, because Markdown joins consecutive lines with a space.
The point is the diff.
Editing one word touches one line, instead of reflowing the whole paragraph.

[snapper](https://snapper.turtletech.us) does it:

```bash
uv tool install snapper-fmt
snapper-fmt -i README.md $(git ls-files 'docs/*.md')
```

There is also a VS Code extension, `TurtleTech.snapper`, which formats on save.

`.snapperrc.toml` at the repository root turns off snapper's long-line advisory.
A sentence on its own line trips it constantly, and the hints bury anything real.

snapper reads MyST directives as ordinary prose, so two constructs need blank lines to survive it:

**Directives**

: Put a blank line after the opening `:::{note}` and before the closing `:::`.
Without them snapper glues the fence onto the neighboring sentence, the directive never closes, and the build fails.

**Definition lists**

: Put a blank line between the term and its `:` line.
Without it snapper joins the two into one paragraph and the definition list is gone.

snapper also removes the indentation of a directive nested inside a list or a definition, which lifts it out of that item.
Keep admonitions at the top level.

### Adding a page

Check first that no existing page owns the subject.
Every fact in `docs/` has one home and every other mention links to it, so most new material belongs on a page that already exists.

1. Create the `.md` file under `docs/`.
2. Add it to a `toctree` in `docs/index.md`.
   A page not in a toctree is a build warning, which `-W` turns into a failure.

### Linking from Blender

Panels link into these docs through `wm.url_open` buttons carrying `icon='HELP'`.
The base URL is the `DOCS_URL` constant in `misuka-blender/docs.py`.
`bl_info['wiki_url']` points at the same place, which is what Blender's own **Documentation** button in the add-on preferences uses.

If you rename or move a page, update the buttons that point at it.

## Releasing

`release/package.py` builds `misuka-blender.zip`, taking `*.py` and `*.json` from `misuka-blender/` plus `README.md`, `LICENSE` and `NOTICE`.
The `docs/` directory is not included.

`.github/workflows/release.yml` runs the full test matrix, packages the add-on and opens a draft GitHub release.
It is triggered manually with `workflow_dispatch`, taking a version tag as input.
Releasing automatically on tag push is set up but commented out.

`.github/workflows/nightly.yml` publishes a rolling prerelease from `master`.

The add-on version lives in `bl_info` in `misuka-blender/__init__.py`.
There is no `blender_manifest.toml`: this is a legacy add-on, not a Blender 4.2 extension.

## License

The add-on as a whole is under [GPL-3.0-or-later](https://github.com/misuka-renderer/misuka-blender/blob/master/LICENSE).
Code inherited from `mitsuba-blender` stays under its BSD 3-Clause notice, and the vendored Blender mesh importers under their GPL-2.0-or-later notices.
See [NOTICE](https://github.com/misuka-renderer/misuka-blender/blob/master/NOTICE).
