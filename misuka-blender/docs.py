'''
Links from the add-on's UI into the documentation.

Panels carry a HELP button rather than their own prose, so the explanation
lives in one place and can be longer than a panel has room for.

`bl_info['wiki_url']` in the add-on's `__init__.py` holds the same base URL as
a literal. Blender reads `bl_info` by parsing the file rather than importing
it, so that one entry cannot reference this constant.
'''

DOCS_URL = 'https://misuka-blender.readthedocs.io/latest/'


def url(page):
    '''Absolute URL of a documentation page, e.g. `guide/exporting.html`.'''
    return DOCS_URL + page


def draw_help_button(layout, page):
    '''
    Add a HELP button opening `page`.

    Meant for a panel's `draw_header_preset`, which Blender right-aligns in the
    header. `draw_header` puts its content between the disclosure triangle and
    the title instead, where the button crowds the label.
    '''
    row = layout.row()
    row.alignment = 'RIGHT'
    row.operator('wm.url_open', text='', icon='HELP', emboss=False).url = url(page)
