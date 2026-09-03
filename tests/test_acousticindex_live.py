'''
Contract tests against the real AcousticIndex API.

Everything else stubs the network, which pins our own logic but says nothing
about whether the API still returns what we read. These check the shape we
depend on, not particular values, so they only fail when the contract moves.

They need a key and are skipped without one, so a normal run is unaffected.
The key comes from the environment and is never written anywhere: it goes in
an Authorization header, not a URL, so a failing assertion cannot print it.
'''
import importlib
import os
import uuid

import pytest


io_module = importlib.import_module('misuka-blender.io')

API_KEY = os.environ.get('ACOUSTICINDEX_API_KEY', '').strip()

pytestmark = pytest.mark.skipif(
    not API_KEY,
    reason='set ACOUSTICINDEX_API_KEY to run the live AcousticIndex tests')

# Any of these finding something is enough; they are only a way in.
SEARCH_TERMS = ('carpet', 'foam', 'wood', 'panel')


@pytest.fixture(scope='module')
def material():
    '''A real material, found by name, as the search path returns it.'''
    for term in SEARCH_TERMS:
        try:
            return io_module.fetch_material(API_KEY, term)
        except io_module.AcousticIndexError:
            continue

    pytest.fail(f'AcousticIndex returned nothing for any of {SEARCH_TERMS}')


def test_the_search_path_returns_a_material(material):
    '''What the panel reads off a fetched material.'''
    assert isinstance(material, dict)
    assert isinstance(material.get('id', ''), str) and material.get('id')
    assert isinstance(material.get('measurements', {}), dict)


def test_a_known_id_is_fetched_without_searching(material):
    '''
    The id path, against an id the API just gave us. If the id endpoint stopped
    accepting these, every lookup would silently fall through to the search.
    '''
    by_id = io_module.fetch_material(API_KEY, material['id'])

    assert by_id.get('id') == material['id']
    assert by_id.get('label') == material.get('label')


def test_an_unknown_query_reports_no_material():
    '''
    The query is generated rather than a fixed nonsense string. The search
    matches loosely, so any fixed string can start matching the day a product
    is added that shares a word with it. The previous one already did:
    'zzzz-no-such-material-zzzz' contains 'material', which is common in the
    German product names, and it found two. Hex digits are a word in no
    language, so nothing real can match this.
    '''
    with pytest.raises(io_module.AcousticIndexError, match='No Acoustic Index material'):
        io_module.fetch_material(API_KEY, 'zz' + uuid.uuid4().hex)


def test_the_measurement_keys_we_read_still_exist(material):
    '''
    The variant keys the importer reads. A material need not carry every kind,
    so this checks the ones present rather than demanding all of them.
    '''
    measurements = material.get('measurements', {})

    known = {'absorption_iso_354', 'scatter_iso_17497_1'}
    assert set(measurements) & known or not measurements, sorted(measurements)

    for kind, band_keys in (
        ('absorption_iso_354', ('alpha_s_third_octave', 'alpha_s_octave')),
        ('scatter_iso_17497_1', ('scatter_third_octave', 'scatter_octave')),
    ):
        for variant in measurements.get(kind, []):
            assert isinstance(variant, dict)

            for key in band_keys:
                bands = variant.get(key)
                if not bands:
                    continue

                # frequency-keyed, and the keys parse as frequencies
                assert isinstance(bands, dict)
                assert all(str(f).isdigit() for f in bands), (kind, key, bands)
