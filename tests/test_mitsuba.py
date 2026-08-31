
def test_mitsuba_has_correct_variant():
    import misuka as mitsuba
    assert mitsuba.variant() == 'scalar_rgb'
