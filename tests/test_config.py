from aiapply.config import load_profile, load_sites


def test_load_profile_defaults():
    profile = load_profile()
    assert profile.min_fit_score == 75
    assert profile.daily_application_cap == 15
    assert "sponsorship" in profile.screening_answers


def test_load_sites_defaults():
    sites = load_sites()
    assert sites.whitelist
    assert sites.whitelist[0].board in ("greenhouse", "lever")
