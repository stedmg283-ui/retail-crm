from app.services.phone import normalize_phone


def test_normalize_indian_10_digit():
    assert normalize_phone("9876543210") == "+919876543210"
    assert normalize_phone("09876543210") == "+919876543210"
    assert normalize_phone("+91 98765 43210") == "+919876543210"
    assert normalize_phone("91 9876543210") == "+919876543210"


def test_normalize_invalid():
    assert normalize_phone("") is None
    assert normalize_phone("123") is None
