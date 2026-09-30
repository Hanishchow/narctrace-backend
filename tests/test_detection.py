import numpy as np

from app.detection import detect_prototype_card


def test_plain_card_shaped_image_is_not_accepted_as_reference_card():
    """The full-frame fallback needs an actual reference-card fiducial."""
    image = np.full((300, 500, 3), 220, dtype=np.uint8)
    detected = detect_prototype_card(image)
    assert detected.found is False
