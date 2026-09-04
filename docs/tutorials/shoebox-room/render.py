from pathlib import Path

import misuka as mi
import pyfar as pf
import matplotlib.pyplot as plt
import xml.etree.ElementTree as ET

# The scenes name their meshes relative to themselves, and misuka resolves
# those against the scene file's own directory. Everything here is therefore
# anchored to this script rather than to the working directory, so the render
# works from anywhere.
HERE = Path(__file__).resolve().parent

# pyfar's own cycle holds eight colors, picked to read on a light and on a
# dark background alike. The scene renders ten octave bands, so the cycle
# would wrap and give 8 kHz and 16 kHz the colors of 31.5 Hz and 63 Hz. The
# last two continue the same palette: a pink taken from the CARTOColors Prism
# set pyfar draws on, lightened the way pyfar lightened the others, and a grey
# light enough to stay visible on black.
BAND_COLORS = [
    '#1471B9', '#D83C27', '#ECAD20', '#5F4690', '#078554',
    '#4EBEBE', '#E07D26', '#72AF47', '#C9569B', '#9A9A9A',
]

WIDTH = 5.5

def read_sampling_rate(xml_path):
   '''Helper function to read max_time and time_bins from the xml file'''

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

def save_etc_plot(etc, frequencies, style, path):
    '''Plot the energy-time curve in one of pyfar's two styles and save it.

    The docs show the light file to a reader in light mode and the dark file
    to a reader in dark mode, so the plot has to exist twice. Everything runs
    inside the style context, including the legend, because the legend picks
    up its own text and background color from the active style.
    '''
    with pf.plot.context(style):
        plt.figure(layout='constrained', figsize=(WIDTH, WIDTH / 16 * 9))
        plt.gca().set_prop_cycle(color=BAND_COLORS)
        pf.plot.time(etc, log_prefix=10, dB=True, style=style)
        plt.legend(frequencies, title='Frequency in Hz', loc='upper right')
        # `transparent` drops the figure and axes background, so the page
        # behind the image shows through and the plot needs no color of its
        # own to match the theme. The legend keeps its background and stays
        # readable over the curves.
        plt.savefig(path, pad_inches=0.1, dpi=300, transparent=True)
        plt.close()

# visual rendering
mi.set_variant('cuda_ad_rgb', 'metal_ad_rgb', 'llvm_ad_rgb')
scene = mi.load_file(str(HERE / 'scene-visual.xml'))
image = mi.render(scene)

# Written straight out rather than through matplotlib, which wraps the render
# in a figure and leaves a white margin around it. `write_async=False` so the
# file is complete before the script moves on.
mi.util.write_bitmap(str(HERE / 'shoebox-visual.png'), image, write_async=False)

# acoustic rendering
mi.set_variant('cuda_ad_acoustic', 'metal_ad_acoustic', 'llvm_ad_acoustic')
scene = mi.load_file(str(HERE / 'scene-acoustic.xml'))
sampling_rate = read_sampling_rate(HERE / 'scene-acoustic.xml')

etc = mi.render(scene, spp=2**18)
etc = pf.Signal(etc.numpy()[..., 0].T, sampling_rate=sampling_rate)

frequencies = read_rendered_frequencies(HERE / 'scene-acoustic.xml')
for style in ('light', 'dark'):
    save_etc_plot(etc, frequencies, style, HERE / f'shoebox-acoustic-{style}.png')
