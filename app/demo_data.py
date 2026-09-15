"""
Demo Samples & Prototype Reference Card Generator for PS26231.
Generates synthetic proxy test images (Positive, Negative, Inconclusive, Blurry, Glared)
so that judges and evaluators can verify every code path without physical reagents.
All generated data is explicitly SIMULATED and safe for demonstration.
"""
import cv2
import numpy as np
from pathlib import Path
from app.constants import DEMO_SAMPLES_DIR, PROTOTYPE_CARD_NOMINAL


def render_prototype_card(
    reaction_rgb: tuple = (210, 195, 135),
    card_width: int = 400,
    card_height: int = 240,
    border_thickness: int = 10,
    warm_tint: float = 1.0  # Optional illuminant cast multiplier
) -> np.ndarray:
    """
    Renders the prototype reference card as a BGR image.
    Contains:
    - High-contrast outer black border
    - Header text: 'PROTOTYPE REF CARD (SIMULATED)'
    - Left column: 4 Calibration Patches (White, Gray, Black, Reference Blue)
    - Right column: Reaction Well
    """
    # Background: off-white card body
    img = np.full((card_height, card_width, 3), 245, dtype=np.uint8)

    # Outer high-contrast black border
    cv2.rectangle(img, (0, 0), (card_width - 1, card_height - 1), (20, 20, 20), border_thickness)

    # Header label
    cv2.putText(
        img,
        "PROTOTYPE REF CARD (SIMULATED)",
        (25, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        (40, 40, 40),
        1,
        cv2.LINE_AA
    )

    # 4 Calibration Patches
    pw, ph = 100, 40
    # 1. White patch (nominal RGB [240, 240, 240] -> BGR)
    w_rgb = PROTOTYPE_CARD_NOMINAL["white"]
    cv2.rectangle(img, (25, 25), (25 + pw, 25 + ph), (w_rgb[2], w_rgb[1], w_rgb[0]), -1)
    cv2.rectangle(img, (25, 25), (25 + pw, 25 + ph), (180, 180, 180), 1)
    cv2.putText(img, "WHITE", (30, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (50, 50, 50), 1)

    # 2. Gray patch (nominal RGB [128, 128, 128])
    g_rgb = PROTOTYPE_CARD_NOMINAL["gray"]
    cv2.rectangle(img, (25, 75), (25 + pw, 75 + ph), (g_rgb[2], g_rgb[1], g_rgb[0]), -1)
    cv2.putText(img, "GRAY 50%", (30, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (230, 230, 230), 1)

    # 3. Black patch (nominal RGB [25, 25, 25])
    k_rgb = PROTOTYPE_CARD_NOMINAL["black"]
    cv2.rectangle(img, (25, 130), (25 + pw, 130 + ph), (k_rgb[2], k_rgb[1], k_rgb[0]), -1)
    cv2.putText(img, "BLACK", (30, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)

    # 4. Ref Blue patch (nominal RGB [40, 80, 200])
    b_rgb = PROTOTYPE_CARD_NOMINAL["reference_blue"]
    cv2.rectangle(img, (25, 185), (25 + pw, 185 + ph), (b_rgb[2], b_rgb[1], b_rgb[0]), -1)
    cv2.putText(img, "REF BLUE", (30, 205), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)

    # Reaction Zone: circular test well
    rx, ry, rw, rh = 230, 75, 110, 100
    center = (rx + rw // 2, ry + rh // 2)
    radius = int(rw * 0.42)

    # Well shadow / rim
    cv2.circle(img, center, radius + 4, (160, 160, 160), -1)
    cv2.circle(img, center, radius + 2, (200, 200, 200), -1)

    # Reaction liquid color (RGB -> BGR)
    bgr_reaction = (int(reaction_rgb[2]), int(reaction_rgb[1]), int(reaction_rgb[0]))
    cv2.circle(img, center, radius, bgr_reaction, -1)

    cv2.putText(
        img,
        "TEST REACTION WELL",
        (rx + 5, ry - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.35,
        (50, 50, 50),
        1,
        cv2.LINE_AA
    )
    cv2.putText(
        img,
        "(PROXY SPOT)",
        (rx + 25, ry + rh + 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.35,
        (80, 80, 80),
        1,
        cv2.LINE_AA
    )

    # Apply slight warm lighting tint if requested (to demonstrate calibration)
    if warm_tint != 1.0:
        # e.g., slightly yellower/warmer indoor light
        img = img.astype(np.float32)
        img[:, :, 2] = np.clip(img[:, :, 2] * warm_tint, 0, 255)       # Red
        img[:, :, 0] = np.clip(img[:, :, 0] * (2.0 - warm_tint), 0, 255) # Blue
        img = img.astype(np.uint8)

    return img


def embed_in_realistic_scene(card_img: np.ndarray, blur: bool = False, overexpose: bool = False, glare: bool = False) -> np.ndarray:
    """
    Places the card onto a neutral tabletop background.
    """
    card_h, card_w = card_img.shape[:2]
    scene_h, scene_w = 480, 640
    # Neutral tabletop
    scene = np.full((scene_h, scene_w, 3), (170, 175, 180), dtype=np.uint8)

    # Slight texture
    noise = np.random.randint(-5, 5, (scene_h, scene_w, 3), dtype=np.int16)
    scene = np.clip(scene.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # Place card in center
    offset_y = (scene_h - card_h) // 2
    offset_x = (scene_w - card_w) // 2
    scene[offset_y : offset_y + card_h, offset_x : offset_x + card_w] = card_img

    if blur:
        scene = cv2.GaussianBlur(scene, (25, 25), 9.0)

    if overexpose:
        scene = np.clip(scene.astype(np.float32) * 1.6 + 50, 0, 255).astype(np.uint8)

    if glare:
        # Add high-luminance specular reflection over reaction well
        glare_center = (offset_x + 285, offset_y + 125)
        cv2.circle(scene, glare_center, 28, (255, 255, 255), -1)

    return scene


def generate_all_demo_samples(overwrite: bool = False):
    """
    Generates all demonstration images into data/demo_samples/
    """
    DEMO_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    required = [
        "sample_alpha_positive.jpg",
        "sample_alpha_negative.jpg",
        "sample_alpha_inconclusive.jpg",
        "sample_beta_positive.jpg",
        "sample_beta_negative.jpg",
        "sample_blurry_rejection.jpg",
        "sample_overexposed_rejection.jpg",
        "sample_glare_rejection.jpg",
        "prototype_reference_card.jpg"
    ]
    if not overwrite and all((DEMO_SAMPLES_DIR / f).is_file() for f in required):
        return

    np.random.seed(42)

    # 1. Profile Alpha Positive (Purple proxy: RGB ~ 144, 117, 138 matching physical specimen)
    card_alpha_pos = render_prototype_card(reaction_rgb=(144, 117, 138), warm_tint=1.0)
    scene_alpha_pos = embed_in_realistic_scene(card_alpha_pos)
    cv2.imwrite(str(DEMO_SAMPLES_DIR / "sample_alpha_positive.jpg"), scene_alpha_pos)

    # 2. Profile Alpha Negative (Pale Amber proxy: RGB ~ 220, 200, 140)
    card_alpha_neg = render_prototype_card(reaction_rgb=(220, 200, 140), warm_tint=1.05)
    scene_alpha_neg = embed_in_realistic_scene(card_alpha_neg)
    cv2.imwrite(str(DEMO_SAMPLES_DIR / "sample_alpha_negative.jpg"), scene_alpha_neg)

    # 3. Profile Alpha Inconclusive (Ambiguous murky olive/brown: RGB ~ 130, 120, 60)
    card_alpha_inc = render_prototype_card(reaction_rgb=(130, 120, 60))
    scene_alpha_inc = embed_in_realistic_scene(card_alpha_inc)
    cv2.imwrite(str(DEMO_SAMPLES_DIR / "sample_alpha_inconclusive.jpg"), scene_alpha_inc)

    # 4. Profile Beta Positive (Cobalt Blue proxy: RGB ~ 113, 151, 189 matching physical specimen)
    card_beta_pos = render_prototype_card(reaction_rgb=(113, 151, 189))
    scene_beta_pos = embed_in_realistic_scene(card_beta_pos)
    cv2.imwrite(str(DEMO_SAMPLES_DIR / "sample_beta_positive.jpg"), scene_beta_pos)

    # 5. Profile Beta Negative (Neutral Clear proxy: RGB ~ 230, 225, 215)
    card_beta_neg = render_prototype_card(reaction_rgb=(230, 225, 215))
    scene_beta_neg = embed_in_realistic_scene(card_beta_neg)
    cv2.imwrite(str(DEMO_SAMPLES_DIR / "sample_beta_negative.jpg"), scene_beta_neg)

    # 6. Blurry Rejection Sample
    scene_blurry = embed_in_realistic_scene(card_alpha_pos, blur=True)
    cv2.imwrite(str(DEMO_SAMPLES_DIR / "sample_blurry_rejection.jpg"), scene_blurry)

    # 7. Overexposed Rejection Sample
    scene_overexposed = embed_in_realistic_scene(card_alpha_pos, overexpose=True)
    cv2.imwrite(str(DEMO_SAMPLES_DIR / "sample_overexposed_rejection.jpg"), scene_overexposed)

    # 8. Glare Rejection Sample
    scene_glare = embed_in_realistic_scene(card_alpha_pos, glare=True)
    cv2.imwrite(str(DEMO_SAMPLES_DIR / "sample_glare_rejection.jpg"), scene_glare)

    # 9. Printable / Clean Standalone Reference Card
    card_clean = render_prototype_card(reaction_rgb=(240, 240, 240))
    cv2.imwrite(str(DEMO_SAMPLES_DIR / "prototype_reference_card.jpg"), card_clean)


if __name__ == "__main__":
    generate_all_demo_samples()
    print("Demo samples generated successfully.")
