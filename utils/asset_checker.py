"""Basic pixel-based comparison for approved and submitted image assets.

This is a lightweight review aid. It is not semantic image recognition,
trademark verification, or proof that an asset is authentic.
"""

from io import BytesIO

from PIL import Image, ImageChops, ImageOps, ImageStat

ASSET_SIMILARITY_THRESHOLD = 95.0
NORMALIZED_SIZE = (512, 512)


def _normalize_image(image_bytes: bytes) -> Image.Image:
    """Open an image, apply EXIF orientation, and fit it on a white canvas."""
    if not image_bytes:
        raise ValueError("The uploaded image is empty.")

    try:
        with Image.open(BytesIO(image_bytes)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGBA")
    except Exception as exc:
        raise ValueError(f"Could not read the image: {exc}") from exc

    white_background = Image.new("RGBA", image.size, (255, 255, 255, 255))
    white_background.alpha_composite(image)
    image = white_background.convert("RGB")

    contained = ImageOps.contain(
        image,
        NORMALIZED_SIZE,
        method=Image.Resampling.LANCZOS,
    )

    canvas = Image.new("RGB", NORMALIZED_SIZE, "white")
    x = (NORMALIZED_SIZE[0] - contained.width) // 2
    y = (NORMALIZED_SIZE[1] - contained.height) // 2
    canvas.paste(contained, (x, y))
    return canvas


def _content_bounds(image: Image.Image):
    """Find non-white content so large white margins do not dominate the score."""
    white = Image.new("RGB", image.size, "white")
    difference = ImageChops.difference(image, white).convert("L")
    mask = difference.point(lambda value: 255 if value > 10 else 0)
    bounds = mask.getbbox()

    if bounds is None:
        return (0, 0, image.width, image.height)

    left, top, right, bottom = bounds
    padding = max(6, int(max(right - left, bottom - top) * 0.025))
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(image.width, right + padding),
        min(image.height, bottom + padding),
    )


def compare_images(reference_bytes: bytes, submitted_bytes: bytes) -> dict:
    """Return a normalized pixel-similarity estimate for two image files."""
    reference = _normalize_image(reference_bytes)
    submitted = _normalize_image(submitted_bytes)

    reference_bounds = _content_bounds(reference)
    submitted_bounds = _content_bounds(submitted)

    bounds = (
        min(reference_bounds[0], submitted_bounds[0]),
        min(reference_bounds[1], submitted_bounds[1]),
        max(reference_bounds[2], submitted_bounds[2]),
        max(reference_bounds[3], submitted_bounds[3]),
    )

    reference_crop = reference.crop(bounds)
    submitted_crop = submitted.crop(bounds)
    difference = ImageChops.difference(reference_crop, submitted_crop)
    channel_means = ImageStat.Stat(difference).mean
    mean_absolute_difference = sum(channel_means[:3]) / 3.0

    similarity = 100.0 * (1.0 - (mean_absolute_difference / 255.0))
    similarity = max(0.0, min(100.0, similarity))
    exact_match = difference.getbbox() is None

    return {
        "similarity_score": round(similarity, 2),
        "mean_absolute_difference": round(mean_absolute_difference, 2),
        "exact_match": exact_match,
        "is_match": similarity >= ASSET_SIMILARITY_THRESHOLD,
        "threshold": ASSET_SIMILARITY_THRESHOLD,
    }
