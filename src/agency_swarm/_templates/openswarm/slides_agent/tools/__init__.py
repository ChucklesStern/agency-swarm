"""Tools for the slides_agent."""

# Slide creation and management: InsertNewSlides then ModifySlide
from .InsertNewSlides import InsertNewSlides
from .ModifySlide import ModifySlide
from .ManageTheme import ManageTheme
from .DeleteSlide import DeleteSlide
from .SlideScreenshot import SlideScreenshot
from .ReadSlide import ReadSlide

# PPTX building and validation
from .BuildPptxFromHtmlSlides import BuildPptxFromHtmlSlides
from .RestoreSnapshot import RestoreSnapshot
from .CreatePptxThumbnailGrid import CreatePptxThumbnailGrid
from .CheckSlideCanvasOverflow import CheckSlideCanvasOverflow
from .CheckSlide import CheckSlide

# Template-based editing (for existing PPTX files)
from .ExtractPptxTextInventory import ExtractPptxTextInventory
from .RearrangePptxSlidesFromTemplate import RearrangePptxSlidesFromTemplate
from .ApplyPptxTextReplacements import ApplyPptxTextReplacements

# Asset utilities
from .EnsureRasterImage import EnsureRasterImage
from .CreateImageMontage import CreateImageMontage
from .DownloadImage import DownloadImage
from .ImageSearch import ImageSearch
from .GenerateImage import GenerateImage

__all__ = [
    # Slide management
    "InsertNewSlides",
    "ModifySlide",
    "ManageTheme",
    "DeleteSlide",
    "SlideScreenshot",
    "ReadSlide",
    # PPTX building
    "BuildPptxFromHtmlSlides",
    "RestoreSnapshot",
    "CreatePptxThumbnailGrid",
    "CheckSlideCanvasOverflow",
    "CheckSlide",
    # Template editing
    "ExtractPptxTextInventory",
    "RearrangePptxSlidesFromTemplate",
    "ApplyPptxTextReplacements",
    # Assets
    "EnsureRasterImage",
    "CreateImageMontage",
    "DownloadImage",
    "ImageSearch",
    "GenerateImage",
]
