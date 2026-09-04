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

width = 5.5
plt.figure(layout='constrained', figsize=(width, width/16*9))
pf.plot.time(etc, log_prefix=10, dB=True)
plt.legend(read_rendered_frequencies(HERE / 'scene-acoustic.xml'),
           title='Frequency in Hz',
           loc='upper right')
plt.savefig(HERE / 'shoebox-acoustic.png', pad_inches=0.1, dpi=300)