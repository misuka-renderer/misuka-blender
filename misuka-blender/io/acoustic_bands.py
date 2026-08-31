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

# ISO octave band centre frequencies.
OCTAVES = (63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)

ABS_PROPS = tuple(f'acoustic_abs_{f}' for f in OCTAVES)
SCAT_PROPS = tuple(f'acoustic_scat_{f}' for f in OCTAVES)


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
    ints against them silently matches nothing.
    '''
    freqs = sorted(int(k) for k in oct_data.keys())

    def value_at(f):
        if str(f) in oct_data:
            return oct_data[str(f)]
        if f < freqs[0]:
            return oct_data[str(freqs[0])]
        if f > freqs[-1]:
            return oct_data[str(freqs[-1])]
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
