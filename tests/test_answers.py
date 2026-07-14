from aiapply.apply._form_filler import normalize_label
from aiapply.apply.answers import classify_question, screening_answer
from aiapply.config import Profile


def test_classify_question():
    assert classify_question("Gender") == "demographic"
    assert classify_question("Are you Hispanic/Latino?") == "demographic"
    assert classify_question("Will you require visa sponsorship?") == "sensitive"
    assert classify_question("What's your preferred name?") == "open"


def test_normalize_label_strips_required_markers():
    assert normalize_label("Full name\n✱") == "Full name"
    assert normalize_label("Email*") == "Email"
    assert normalize_label("Current company  ") == "Current company"


def test_screening_answer_matches_keyword():
    profile = Profile(screening_answers={"visa": "No"})
    assert screening_answer("Do you require a visa?", profile) == "No"
    assert screening_answer("What is your favorite color?", profile) is None
