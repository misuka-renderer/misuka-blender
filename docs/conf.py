'''Sphinx configuration for the misuka-blender documentation.

The add-on cannot be imported here. Its package directory is named
`misuka-blender`, which is not a valid Python identifier, and importing it
would pull in `bpy`, which only exists inside Blender. The version is therefore
read out of `bl_info` with a regex.
'''
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

project = 'misuka-blender'
author = 'Tobias Jüterbock, Julius Schwarz'
copyright = '2026, misuka-renderer'

GITHUB_URL = 'https://github.com/misuka-renderer/misuka-blender'


def _addon_version():
    '''Read `'version': (x, y, z)` out of the add-on's bl_info.'''
    source = (REPO_ROOT / 'misuka-blender' / '__init__.py').read_text(encoding='utf-8')
    match = re.search(r"['\"]version['\"]\s*:\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", source)
    if match is None:
        return '0.0.0'
    return '.'.join(match.groups())


release = _addon_version()
version = '.'.join(release.split('.')[:2])

extensions = [
    'myst_parser',
    'sphinx_copybutton',
]

# `docs/agents/` holds untracked, agent-facing notes. Read the Docs never sees
# them, but a local build would sweep them into the site without this.
exclude_patterns = ['agents/*', '_build', 'Thumbs.db', '.DS_Store']

myst_enable_extensions = [
    'colon_fence',
    'deflist',
    'substitution',
]

# Generate anchors down to h3 so pages can link to a specific section,
# for example guide/acoustic-materials.html#specular-reflection.
myst_heading_anchors = 3

# Open links that leave the site in a new tab, so a reader following one of
# the misuka or Acoustic Index links does not lose their place here.
myst_links_external_new_tab = True

html_theme = 'furo'
html_static_path = ['_static']
html_css_files = ['custom.css']
templates_path = ['_templates']
html_title = f'misuka-blender {release}'
# The misuka project's own icon, sized the way the misuka docs size it.
# The project name stays visible below it, since the icon says "misuka" and
# this is misuka-blender.
html_logo = '_static/img/misuka_icon.png'

html_theme_options = {
    # Adds an "Edit this page" link to the top of every page.
    'source_repository': f'{GITHUB_URL}/',
    'source_branch': 'master',
    'source_directory': 'docs/',
    # "view" is repurposed by _templates/components/view-this-page.html into a
    # link to the repository, so the GitHub icon sits beside the light/dark
    # theme toggle at the top of the page rather than in the footer. The footer
    # is hidden by _static/custom.css.
    'top_of_page_buttons': ['view', 'edit'],
}

# External links that need no checking on every build.
linkcheck_ignore = [
    r'https://acousticindex\.com/api/.*',
]
