"""
Reference Card Detection & Reaction Zone Localization for PS26231 MVP.
Detects the prototype reference card in the image frame, performs perspective
normalization, and extracts observed patch colours alongside the test reaction zone.
"""
import cv2
import numpy as np
from typing import Optional, Tuple, Dict, Any, List


class DetectedCard:
    def __init__(
        self,
        found: bool,
        card_contour: Optional[np.ndarray] = None,
        warped_card: Optional[np.ndarray] = None,
        patches_rgb: Optional[Dict[str, Tuple[float, float, float]]] = None,
        reaction_rgb: Optional[Tuple[float, float, float]] = None,
        reaction_mask: Optional[np.ndarray] = None
    ):
        self.found = found
        self.card_contour = card_contour
        self.warped_card = warped_card
        self.patches_rgb = patches_rgb or {}
        self.reaction_rgb = reaction_rgb
        self.reaction_mask = reaction_mask


def order_quad_points(pts: np.ndarray) -> np.ndarray:
    """
    Orders 4 quadrilateral points: [top-left, top-right, bottom-right, bottom-left].
    """
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # Top-left has smallest sum
    rect[2] = pts[np.argmax(s)]  # Bottom-right has largest sum

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # Top-right has smallest diff
    rect[3] = pts[np.argmax(diff)]  # Bottom-left has largest diff
    return rect


def four_point_transform(image: np.ndarray, pts: np.ndarray, width: int = 400, height: int = 240) -> np.ndarray:
    """
    Applies perspective warp to obtain a top-down canonical view of the card.
    """
    rect = order_quad_points(pts)
    dst = np.array([
        [0, 0],
        [width - 1, 0],
        [width - 1, height - 1],
        [0, height - 1]
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (width, height))
    return warped


def extract_mean_color(image: np.ndarray, x: int, y: int, w: int, h: int) -> Tuple[float, float, float]:
    """
    Extracts mean RGB from a sub-region (inner 70% to avoid boundary spill).
    Input image is BGR, returns (R, G, B).
    """
    margin_x = int(w * 0.15)
    margin_y = int(h * 0.15)
    roi = image[y + margin_y : y + h - margin_y, x + margin_x : x + w - margin_x]
    if roi.size == 0:
        roi = image[y : y + h, x : x + w]
    
    mean_bgr = cv2.mean(roi)[:3]
    # Return as (R, G, B)
    return (float(mean_bgr[2]), float(mean_bgr[1]), float(mean_bgr[0]))


def detect_prototype_card(
    img_bgr: np.ndarray,
    canonical_w: int = 400,
    canonical_h: int = 240
) -> DetectedCard:
    """
    Searches for the prototype reference card in the image with standardized detection resolution.
    Normalizes orientation (portrait/landscape and 180-degree flips) using the Reference Blue fiducial.
    Extracts observed patch colours and reaction zone using normalized relative coordinates.
    """
    if img_bgr is None or img_bgr.size == 0:
        return DetectedCard(found=False)

    img_h, img_w = img_bgr.shape[:2]

    # 1. Normalize resolution for robust Canny edge detection across camera sensor megapixels
    det_w = 800
    scale = det_w / float(img_w) if img_w > det_w else 1.0
    det_h = int(round(img_h * scale))
    det_img = cv2.resize(img_bgr, (det_w, det_h), interpolation=cv2.INTER_AREA) if scale != 1.0 else img_bgr

    gray = cv2.cvtColor(det_img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Edge and contour detection
    edges = cv2.Canny(blurred, 40, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edges = cv2.dilate(edges, kernel, iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    card_contour = None
    max_area = 0.0
    min_area = (det_w * det_h) * 0.05  # At least 5% of frame

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > min_area:
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)
            if len(approx) == 4:
                # Check aspect ratio
                x, y, w, h = cv2.boundingRect(approx)
                aspect = max(w, h) / max(min(w, h), 1)
                if 1.1 <= aspect <= 2.5 and area > max_area:
                    card_contour = approx
                    max_area = area

    # Fallback: if entire image is already a cropped card or direct scan
    if card_contour is None:
        aspect = max(img_w, img_h) / max(min(img_w, img_h), 1)
        if 1.2 <= aspect <= 2.5:
            orig_pts = np.array([
                [0, 0],
                [img_w - 1, 0],
                [img_w - 1, img_h - 1],
                [0, img_h - 1]
            ], dtype=np.float32)
            card_contour = orig_pts.reshape(-1, 1, 2).astype(np.int32)
        else:
            return DetectedCard(found=False)
    else:
        orig_pts = (card_contour.reshape(4, 2) / scale).astype("float32")
        card_contour = (orig_pts.reshape(-1, 1, 2)).astype(np.int32)

    # 2. Order corners and evaluate physical quad aspect ratio
    rect = order_quad_points(orig_pts)
    (tl, tr, br, bl) = rect
    quad_w = max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl))
    quad_h = max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl))

    # 3. Perspective Warp with Portrait/Landscape Handling
    if quad_h > quad_w:
        # Portrait card capture: warp to tall rectangle, then rotate to landscape
        dst = np.array([
            [0, 0],
            [canonical_h - 1, 0],
            [canonical_h - 1, canonical_w - 1],
            [0, canonical_w - 1]
        ], dtype="float32")
        M = cv2.getPerspectiveTransform(rect, dst)
        warped_tall = cv2.warpPerspective(img_bgr, M, (canonical_h, canonical_w))
        c1 = cv2.rotate(warped_tall, cv2.ROTATE_90_CLOCKWISE)
        c2 = cv2.rotate(warped_tall, cv2.ROTATE_90_COUNTERCLOCKWISE)
        candidates = [c1, c2, cv2.rotate(c1, cv2.ROTATE_180), cv2.rotate(c2, cv2.ROTATE_180)]
    else:
        # Landscape card capture
        dst = np.array([
            [0, 0],
            [canonical_w - 1, 0],
            [canonical_w - 1, canonical_h - 1],
            [0, canonical_h - 1]
        ], dtype="float32")
        M = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(img_bgr, M, (canonical_w, canonical_h))
        candidates = [warped, cv2.rotate(warped, cv2.ROTATE_180)]

    # 4. Canonical Orientation Normalization:
    # The reference card has the Reference Blue patch at bottom-left (H in [90, 135], S >= 40).
    best_warped = candidates[0]
    best_blue_score = -1
    for cand in candidates:
        ch, cw = cand.shape[:2]
        bl_roi = cand[int(ch * 0.6):, :int(cw * 0.35)]
        hsv = cv2.cvtColor(bl_roi, cv2.COLOR_BGR2HSV)
        blue_cnt = np.count_nonzero((hsv[:, :, 0] >= 90) & (hsv[:, :, 0] <= 135) & (hsv[:, :, 1] >= 40))
        if blue_cnt > best_blue_score:
            best_blue_score = blue_cnt
            best_warped = cand

    warped = best_warped

    # 5. Extract observed patch RGBs from normalized relative coordinates
    # On the canonical warped card (400 x 240):
    # Left column patches: x: 8% to 17% (width 9%), y: 14% to 86%
    # This samples solely inside the color boxes, strictly avoiding surrounding text labels and borders.
    cw, ch = canonical_w, canonical_h
    pw, ph = int(cw * 0.09), int(ch * 0.14)
    px = int(cw * 0.08)

    white_rgb = extract_mean_color(warped, px, int(ch * 0.14), pw, ph)
    gray_rgb = extract_mean_color(warped, px, int(ch * 0.34), pw, ph)
    black_rgb = extract_mean_color(warped, px, int(ch * 0.53), pw, ph)
    blue_rgb = extract_mean_color(warped, px, int(ch * 0.72), pw, ph)

    # 6. Reaction Zone sampling:
    # Localize reaction circle within the designated reaction column (x: 52% to 95%, y: 15% to 85%)
    rx_start, rx_end = int(cw * 0.52), int(cw * 0.95)
    ry_start, ry_end = int(ch * 0.15), int(ch * 0.85)
    reac_roi = warped[ry_start:ry_end, rx_start:rx_end]
    reac_gray = cv2.cvtColor(reac_roi, cv2.COLOR_BGR2GRAY)
    reac_blur = cv2.GaussianBlur(reac_gray, (9, 9), 2)
    circles = cv2.HoughCircles(
        reac_blur,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=30,
        param1=50,
        param2=25,
        minRadius=20,
        maxRadius=55
    )

    if circles is not None:
        c = circles[0][0]
        full_cx = rx_start + int(c[0])
        full_cy = ry_start + int(c[1])
        sample_r = max(10, int(c[2] * 0.5))
    else:
        full_cx, full_cy, sample_r = int(cw * 0.75), int(ch * 0.48), 20

    # Sample only the interior core to avoid boundary and background bleed
    reaction_mask = np.zeros((ch, cw), dtype=np.uint8)
    cv2.circle(reaction_mask, (full_cx, full_cy), sample_r, 255, -1)
    reac_bgr = cv2.mean(warped, mask=reaction_mask)[:3]
    reaction_rgb = (float(reac_bgr[2]), float(reac_bgr[1]), float(reac_bgr[0]))

    patches = {
        "white": white_rgb,
        "gray": gray_rgb,
        "black": black_rgb,
        "reference_blue": blue_rgb
    }

    return DetectedCard(
        found=True,
        card_contour=card_contour,
        warped_card=warped,
        patches_rgb=patches,
        reaction_rgb=reaction_rgb,
        reaction_mask=reaction_mask
    )
