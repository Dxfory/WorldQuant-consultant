"""Pixel Intact: keep every original pixel, then refine clarity."""

from .safety import allow_large_local_images

allow_large_local_images()

from .batch import batch_enhance
from .completeness import ImageReport, inspect_image
from .enhance import EnhanceSettings, enhance_image, enhance_pil
from .join import JoinResult, join_tiles
from .slice import SlicePlan, SliceTile, plan_slice, slice_image
from .superres import fsr_available

__all__ = [
    "EnhanceSettings",
    "ImageReport",
    "JoinResult",
    "SlicePlan",
    "SliceTile",
    "batch_enhance",
    "enhance_image",
    "enhance_pil",
    "fsr_available",
    "inspect_image",
    "join_tiles",
    "plan_slice",
    "slice_image",
    "__version__",
]

__version__ = "0.2.1"
