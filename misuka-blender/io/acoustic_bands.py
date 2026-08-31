'''
Shared definitions for the acoustic band tables.

Both the material UI (`io/__init__.py`) and the scene exporter
(`io/exporter/materials.py`) need the band centre frequencies, the names of the
per-band Blender properties and the interpolation helper. Keeping them here
avoids the UI importing from the exporter, and means adding or removing a band
is a one-line change.
'''

from math import log

# Neutral placeholder for a coefficient the user has not supplied. It carries no
# physical meaning: it is simply a mid-range value that is obviously not a
# measurement. Absorption and scattering share it so the panel has one number to
# explain instead of two.
ACOUSTIC_DEFAULT = 0.5

# ISO 266 preferred third-octave centre frequencies, 25 Hz to 20 kHz.
THIRD_OCTAVES = (
    25, 31.5, 40,
    50, 63, 80,
    100, 125, 160,
    200, 250, 315,
    400, 500, 630,
    800, 1000, 1250,
    1600, 2000, 2500,
    3150, 4000, 5000,
    6300, 8000, 10000,
    12500, 16000, 20000,
)

# Octave centres, every third entry of THIRD_OCTAVES starting at the second.
# The 31.5 Hz band is included because room acoustics is judged well below 63 Hz.
OCTAVES = THIRD_OCTAVES[1::3]

# Positions of the octave centres within THIRD_OCTAVES, so the panel can grey
# out the rows that octave mode does not use.
OCTAVE_INDICES = tuple(THIRD_OCTAVES.index(f) for f in OCTAVES)


def band_suffix(freq):
    '''
    The part of a per-band property name that says which band it is.

    31.5 Hz is the one preferred centre that is not a whole number, and a dot
    cannot appear in an RNA path, so it becomes `31_5`.
    '''
    return str(freq).replace('.', '_')


ABS_PROPS = tuple(f'acoustic_abs_{band_suffix(f)}' for f in THIRD_OCTAVES)
SCAT_PROPS = tuple(f'acoustic_scat_{band_suffix(f)}' for f in THIRD_OCTAVES)

# Largest relative deviation still counted as the same band when matching a
# measured frequency onto the table. Third-octave centres are spaced by a
# constant factor of about 1.26, so anything below ~12% cannot reach a
# neighbouring band.
BAND_MATCH_TOLERANCE = 0.03


# Choices for the scene-wide band resolution, which drives the tape film's
# frequency list and therefore what actually gets simulated.
BAND_RESOLUTION_ITEMS = (
    ('OCTAVE', "Octave Bands", "Simulate the 10 octave centres, 31.5 Hz to 16 kHz"),
    ('THIRD_OCTAVE', "Third Octave Bands",
     "Simulate all 30 third-octave centres, 25 Hz to 20 kHz"),
)


def active_bands(resolution):
    '''
    The (frequencies, indices) pair a BAND_RESOLUTION_ITEMS identifier selects.

    `indices` positions each frequency in the full third-octave table, which is
    what the material properties are always stored on.
    '''
    if resolution == 'THIRD_OCTAVE':
        return THIRD_OCTAVES, tuple(range(len(THIRD_OCTAVES)))
    return OCTAVES, OCTAVE_INDICES


def resolution_frequencies(resolution):
    '''Band centres for a BAND_RESOLUTION_ITEMS identifier.'''
    return active_bands(resolution)[0]


def time_bins(mts_settings):
    '''
    Number of time samples the tape film records.

    The film is configured by bin count, but a response is naturally described
    by how long it is and how finely it is sampled, so those are what the UI
    asks for.
    '''
    return max(round(mts_settings.acoustic_max_time
                     * mts_settings.acoustic_sampling_rate), 1)


def scene_resolution(scene):
    '''
    The band resolution a scene exports at.

    Falls back to the default when the misuka scene settings are not registered,
    which keeps the material panel drawable in isolation.
    '''
    settings = getattr(scene, 'mitsuba', None)
    return getattr(settings, 'acoustic_band_resolution', 'OCTAVE')


def scene_interpolation(scene):
    '''The frequency axis a scene interpolates along. See scene_resolution.'''
    settings = getattr(scene, 'mitsuba', None)
    return getattr(settings, 'acoustic_interpolation', 'LOG')


# Axis the interpolation runs on. Band centres are spaced by a constant factor,
# so the logarithmic axis is the one they are evenly distributed along: between
# anchors at 500 Hz and 2 kHz it puts 1 kHz halfway, where the linear axis puts
# it a third of the way. Linear stays available for datasets that were tabulated
# that way.
INTERPOLATION_ITEMS = (
    ('LOG', "Logarithmic",
     "Interpolate along log(frequency), the axis band centres are evenly spaced on"),
    ('LINEAR', "Linear", "Interpolate along frequency in Hz"),
)


def nearest_band_index(freq, frequencies):
    '''
    Index of the band centre closest to `freq`, or None if none is close enough.

    Measured data is not always reported on the preferred centres (3150 Hz may
    come back as 3200 Hz), so match by relative distance rather than equality.
    '''
    best = min(range(len(frequencies)), key=lambda i: abs(log(frequencies[i]) - log(freq)))
    if abs(frequencies[best] - freq) / frequencies[best] > BAND_MATCH_TOLERANCE:
        return None
    return best


# The per-band float properties tick their own "set" checkbox when edited, which
# is what makes typing a value mark it as an anchor. Batch writes (interpolate,
# reset, applying a database variant) manage the checkboxes themselves and must
# not trip that callback.
_suppress_band_update = False


def band_updates_suppressed():
    return _suppress_band_update


def read_bands(mat, props, indices):
    '''Read the band values of one family at `indices`.'''
    return [getattr(mat, props[i]) for i in indices]


def write_bands(mat, props, values):
    '''Write a whole family back, skipping the per-band "set" callback.'''
    global _suppress_band_update

    _suppress_band_update = True
    try:
        for prop, value in zip(props, values):
            setattr(mat, prop, value)
    finally:
        _suppress_band_update = False


def interpolate_bands(anchors, target_freqs, fallback=ACOUSTIC_DEFAULT,
                      interpolation='LOG'):
    '''
    Fill `target_freqs` from the `{frequency: value}` anchors.

    `interpolation` is an INTERPOLATION_ITEMS identifier choosing the frequency
    axis. Targets outside the anchor range take the nearest anchor's value on
    either axis.
    '''
    freqs = sorted(anchors.keys())

    if not freqs:
        return [fallback] * len(target_freqs)

    if len(freqs) == 1:
        return [anchors[freqs[0]]] * len(target_freqs)

    axis = (lambda f: f) if interpolation == 'LINEAR' else log

    values = []

    for f in target_freqs:
        if f in anchors:
            values.append(anchors[f])
        elif f <= freqs[0]:
            values.append(anchors[freqs[0]])
        elif f >= freqs[-1]:
            values.append(anchors[freqs[-1]])
        else:
            i = max(j for j in range(len(freqs) - 1) if freqs[j] < f)
            f1, f2 = freqs[i], freqs[i + 1]
            v1, v2 = anchors[f1], anchors[f2]
            t = (axis(f) - axis(f1)) / (axis(f2) - axis(f1))
            values.append(v1 + t * (v2 - v1))

    return values
