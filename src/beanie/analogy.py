"""Abstraction / analogy — a demonstrated rule applied to kinds never demonstrated.

Traceability: VISION §5 test **T6** ("a concept learned in one domain is
correctly applied in a structurally similar domain it has never seen — e.g.
'grouping by type' learned on downloads, applied to a photo library"),
ARCHITECTURE §4.1 (planning) and §7 (the body's needs-first actions), register
row 43.

`learning.py` infers the rule ".pdf → docs, .jpg → images" from one
demonstration. That is transfer *within* the demonstrated kinds (T1). T6 asks
for more: the *structure* behind the rule — "files of a kind belong in the
folder shown for that kind of thing" — should carry to kinds the owner never
touched. This module does that lift mechanically:

    demonstrated:  .pdf → docs, .jpg → images
    lifted:        category "documents" → docs, category "images" → images
    applied:       .docx → docs (documents), .png → images (images)

Honesty rules, because a wrong guess moves the owner's files:
  * an inference is only made when the demonstration showed *some* extension of
    the same category — a category never demonstrated is refused, not guessed;
  * every inferred move carries the reason it was made, so the plan and the
    trace can show the owner what the mind assumed;
  * nothing here invents new destinations: the target folders are always the
    ones the owner demonstrated.
"""

from __future__ import annotations

from typing import Optional

#: kind → category. Categories are *structural*: they describe what a file is,
#: not where it goes (the destination always comes from the demonstration).
CATEGORY_BY_EXTENSION: dict[str, str] = {}
for _category, _extensions in {
    "documents": ("pdf", "doc", "docx", "odt", "rtf", "txt", "md", "tex", "pages"),
    "images": ("jpg", "jpeg", "png", "gif", "bmp", "webp", "heic", "tif", "tiff", "svg", "raw"),
    "audio": ("mp3", "wav", "flac", "aac", "ogg", "m4a", "opus"),
    "video": ("mp4", "mov", "avi", "mkv", "webm", "m4v"),
    "archives": ("zip", "tar", "gz", "bz2", "xz", "rar", "7z"),
    "spreadsheets": ("csv", "tsv", "xls", "xlsx", "ods"),
    "slides": ("ppt", "pptx", "odp", "key"),
    "code": ("py", "js", "ts", "json", "yaml", "yml", "toml", "sh", "c", "h", "rs", "go", "java", "rb"),
}.items():
    for _extension in _extensions:
        CATEGORY_BY_EXTENSION[_extension] = _category


#: singular labels so inference reasons read like English, not like a table
CATEGORY_LABEL: dict[str, str] = {
    "documents": "document", "images": "image", "audio": "audio", "video": "video",
    "archives": "archive", "spreadsheets": "spreadsheet", "slides": "slide", "code": "code",
}


def _article(label: str) -> str:
    return "an" if label[:1].lower() in "aeiou" else "a"


def category_of(extension: str) -> Optional[str]:
    """Structural category of a file extension ('png' → 'images'), or None."""
    return CATEGORY_BY_EXTENSION.get(extension.lower().lstrip(".").strip())


def demonstrated_categories(mapping: dict[str, str]) -> dict[str, str]:
    """The category → destination map implied by a demonstrated extension map."""
    lifted: dict[str, str] = {}
    for extension, destination in mapping.items():
        category = category_of(extension)
        if category and destination:
            lifted.setdefault(category, destination)
    return lifted


def infer_destination(mapping: dict[str, str], extension: str) -> tuple[Optional[str], str]:
    """Destination for a kind the demonstration never covered, with its reason.

    Returns `(None, reason)` when the category was not demonstrated — the mind
    then reports the gap instead of guessing where the owner's files should go.
    """
    extension = extension.lower().lstrip(".")
    if extension in mapping:
        return mapping[extension], "demonstrated directly"
    category = category_of(extension)
    if category is None:
        return None, f"unknown category for .{extension}"
    lifted = demonstrated_categories(mapping)
    label = CATEGORY_LABEL.get(category, category)
    if category in lifted:
        example = next(ext for ext, dst in mapping.items() if category_of(ext) == category)
        return lifted[category], (f"inferred by analogy: .{extension} is {_article(label)} {label} file, "
                                  f"like the demonstrated .{example} → {lifted[category]}")
    return None, (f"your demonstration never placed {_article(label)} {label} file anywhere — "
                  f"I don't know where these belong")
