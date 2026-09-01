'''
Shared definitions for the acoustic band table.

The band centre frequencies and the names of the per-band Blender properties
were spelled out by hand in every place that touched them, which is why the two
octave lookups in the material UI were able to drift apart. Both the UI
(`io/__init__.py`) and the exporter (`io/exporter/materials.py`) take them from
here instead, so adding or removing a band is a one-line change.
'''

# Neutral placeholder for a coefficient the user has not supplied.
ABSORPTION_DEFAULT = 0.5
SCATTERING_DEFAULT = 0.25

# ISO octave band centre frequencies. The 31.5 Hz band is included because room
# acoustics is judged well below 63 Hz.
OCTAVES = (31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)

# ISO 266 preferred third-octave centre frequencies, 25 Hz to 20 kHz, three per
# octave band. Materials are still authored per octave; this is the finer grid
# the acoustic film can be asked to simulate on.
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


def band_suffix(freq):
    '''
    The part of a per-band property name that says which band it is.

    31.5 Hz is the one preferred centre that is not a whole number, and a dot
    cannot appear in an RNA path, so it becomes `31_5`.
    '''
    return str(freq).replace('.', '_')


ABS_PROPS = tuple(f'acoustic_abs_{band_suffix(f)}' for f in OCTAVES)
SCAT_PROPS = tuple(f'acoustic_scat_{band_suffix(f)}' for f in OCTAVES)

# Choices for the scene-wide band resolution, which drives the tape film's
# frequency list and therefore what actually gets simulated.
BAND_RESOLUTION_ITEMS = (
    ('OCTAVE', "Octave Bands", "Simulate the 10 octave centres, 31.5 Hz to 16 kHz"),
    ('THIRD_OCTAVE', "Third Octave Bands",
     "Simulate all 30 third-octave centres, 25 Hz to 20 kHz"),
)


def resolution_frequencies(resolution):
    '''Band centres for a BAND_RESOLUTION_ITEMS identifier.'''
    return THIRD_OCTAVES if resolution == 'THIRD_OCTAVE' else OCTAVES


def time_bins(mts_settings):
    '''
    Number of time samples the tape film records.

    The film is configured by bin count, but a response is naturally described
    by how long it is and how finely it is sampled, so those are what the UI
    asks for.
    '''
    return max(round(mts_settings.acoustic_max_time
                     * mts_settings.acoustic_sampling_rate), 1)


def read_bands(mat, props):
    '''Read the band values of one family.'''
    return [getattr(mat, prop) for prop in props]


def write_bands(mat, props, values):
    '''Write band values back.'''
    for prop, value in zip(props, values):
        setattr(mat, prop, value)


def octave_lookup(oct_data, target_freqs, fallback):
    '''
    Read octave-band measurements onto `target_freqs`, clamping at both ends.

    Measurement data comes from JSON, so its keys are strings. Comparing raw
    numbers against them silently matches nothing, and the clamped ends are read
    back through the original key rather than a rebuilt one, since str(31.5) is
    "31.5" but str(float("63")) is "63.0".
    '''
    keys = sorted(oct_data.keys(), key=float)
    freqs = [float(k) for k in keys]

    def value_at(f):
        if str(f) in oct_data:
            return oct_data[str(f)]
        if f < freqs[0]:
            return oct_data[keys[0]]
        if f > freqs[-1]:
            return oct_data[keys[-1]]
        return fallback

    return [value_at(f) for f in target_freqs]


def interpolate_bands(anchors, target_freqs, fallback=ABSORPTION_DEFAULT):
    '''
    Fill `target_freqs` from the `{frequency: value}` anchors.

    Missing values are filled by linear interpolation; targets outside the
    anchor range take the nearest anchor's value.
    '''
    freqs = sorted(anchors.keys())

    if not freqs:
        return [fallback] * len(target_freqs)

    if len(freqs) == 1:
        return [anchors[freqs[0]]] * len(target_freqs)

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
            values.append(v1 + (f - f1) / (f2 - f1) * (v2 - v1))

    return values
