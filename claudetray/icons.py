"""Tray icon: a hex disc with a hex ring knocked out, drawn with Pillow (no image files).

Copied from Claude Hub tray/icons.py."""
from __future__ import annotations

import math

from PIL import Image, ImageChops, ImageDraw

_SIZE = 64        # final icon size
_SUPERSAMPLE = 8  # draw big, downscale for crisp anti-aliased edges

_RGB: dict[str, tuple[int, int, int]] = {
    "green":  (53, 179, 107),
    "yellow": (221, 160, 27),
    "red":    (226, 76, 75),
    "gray":   (124, 131, 142),
}

# Hex disc: circle of radius 30 in a 64-unit square, flattened by six chords cut
# at distance 28 from the centre. Shallow enough to still read as a disc at 16 px,
# angular enough not to be mistaken for a generic status dot.
_RADIUS = 30.0
_CUT_DISTANCE = 28.0
_CUT_ANGLES = (0, 60, 120, 180, 240, 300)

# The inner hex, same construction and same orientation so the two nest. The
# knockout band runs from _INNER_RADIUS down to _CORE_RADIUS; a solid inner hex
# (no core) was tried and lost — it is a hole, not a feature.
_INNER_RADIUS = 20.0
_CORE_RADIUS = 11.0
_CUT_RATIO = _CUT_DISTANCE / _RADIUS       # flats stay proportional at any radius


def _disc_mask(pixels: int, scale: float, radius: float, cut_distance: float) -> Image.Image:
    """Solid hex-disc mask: a circle with a flat chord cut at each of six angles."""
    mask = Image.new("L", (pixels, pixels), 0)
    draw = ImageDraw.Draw(mask)
    center = 32.0
    draw.ellipse(
        [(center - radius) * scale, (center - radius) * scale,
         (center + radius) * scale, (center + radius) * scale],
        fill=255,
    )
    for angle in _CUT_ANGLES:
        radians = math.radians(angle)
        ux, uy = math.cos(radians), math.sin(radians)
        vx, vy = -uy, ux                      # along the chord
        px, py = center + cut_distance * ux, center + cut_distance * uy
        far = 200.0                           # comfortably past the canvas
        draw.polygon(
            [((px + vx * far) * scale, (py + vy * far) * scale),
             ((px - vx * far) * scale, (py - vy * far) * scale),
             ((px - vx * far + ux * far) * scale, (py - vy * far + uy * far) * scale),
             ((px + vx * far + ux * far) * scale, (py + vy * far + uy * far) * scale)],
            fill=0,
        )
    return mask


def _frame_mask(pixels: int, scale: float) -> Image.Image:
    """The frame as a solid hex disc; the glyph is knocked out of it."""
    return _disc_mask(pixels, scale, _RADIUS, _CUT_DISTANCE)


def _glyph_mask(pixels: int, scale: float) -> Image.Image:
    """The hub's mark: a hex ring — a smaller hex, hollowed so a hex core survives."""
    outer = _disc_mask(pixels, scale, _INNER_RADIUS, _INNER_RADIUS * _CUT_RATIO)
    core = _disc_mask(pixels, scale, _CORE_RADIUS, _CORE_RADIUS * _CUT_RATIO)
    return ImageChops.subtract(outer, core)


def make_icon(color: str) -> Image.Image:
    """Build a 64x64 RGBA hex-disc tray icon for the given color."""
    fill = _RGB.get(color, _RGB["gray"])
    pixels = _SIZE * _SUPERSAMPLE
    scale = pixels / 64.0

    alpha = ImageChops.subtract(_frame_mask(pixels, scale), _glyph_mask(pixels, scale))
    alpha = alpha.resize((_SIZE, _SIZE), Image.LANCZOS)

    image = Image.new("RGBA", (_SIZE, _SIZE), fill + (0,))
    image.putalpha(alpha)
    return image



