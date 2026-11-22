"""Whole-machine file index — owner directive §D6 ("Everything"-grade search).

Spec: ARCHITECTURE §11 (owner directives) and §3.2 (world state — where things are).


The problem this solves, in the owner's words: a song can be ``kaba.mp3``,
``Kaba by Kapeke.m4a``, ``KAABA (Official Video).mpg``, ``02 - kaba (128kbps).mp3``
or a dozen other shapes — and it can be *anywhere* on the PC, not in a music folder.
YouTube finds it anyway. So the index has to match like that, for every file kind.

Three properties, in the order they matter:

1. **Coverage** — walk the whole machine, not a curated folder. Exclusions exist but are
   declared and reported, never silent.
2. **Speed** — the first scan is the expensive one; later scans are incremental
   (a directory whose ``(mtime, size, entry-count)`` signature is unchanged is skipped
   entirely). Query time is a single pass over the in-memory name table with cheap
   early rejection, so it stays in milliseconds at hundreds of thousands of files.
   On Windows, if voidtools Everything's ``es.exe`` is installed, §D6's fast path can
   delegate the scan to the MFT — same interface, same provenance.
3. **Matching** — several independent signals, each of which fires on a different way a
   human's memory of a filename differs from the filename itself:

   ==================  ==========================================================
   signal              what it catches
   ==================  ==========================================================
   ``exact``           the query is literally in the name
   ``token``           query words appear as words (``kaba`` in ``Kaba by Kapeke``)
   ``title_artist``    ``X by Y`` / ``Y - X`` / ``X feat. Y`` splits
   ``subsequence``     abbreviations and dropped vowels (``kbd`` → ``keyboard``)
   ``trigram``         typos and reordering, position-independent
   ``edit``            Damerau-Levenshtein: transpositions and single-character slips
   ``stem``            plural/possessive/``-ing`` noise
   ==================  ==========================================================

   Normalisation runs first and does the boring work that makes those signals possible:
   case folding, diacritic stripping (``Kaába`` → ``kaaba``), separator folding
   (``kaba_by_kapeke`` → ``kaba by kapeke``), extension removal, and dropping the tokens
   that decorate a filename without identifying it (``official``, ``video``, ``hq``,
   bitrates, years, container names).

**Provenance is not optional here (§9.9 / §D6).** A ``Match`` carries the signals that
fired *with their values* and a ``why`` sentence built from them, so "why did you pick
this file?" has the same auditable answer as "why did you say that?". A result that
cannot explain itself is not returned as a confident answer.
"""

from __future__ import annotations

import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional, Sequence

# --------------------------------------------------------------------------- kinds

KIND_BY_EXT: dict[str, str] = {
    # audio
    "mp3": "audio", "m4a": "audio", "aac": "audio", "flac": "audio", "wav": "audio",
    "ogg": "audio", "opus": "audio", "wma": "audio", "aiff": "audio", "aif": "audio",
    "alac": "audio", "mka": "audio", "ape": "audio", "mid": "audio", "midi": "audio",
    "amr": "audio", "weba": "audio",
    # video
    "mp4": "video", "mkv": "video", "avi": "video", "mov": "video", "wmv": "video",
    "flv": "video", "webm": "video", "mpg": "video", "mpeg": "video", "m4v": "video",
    "3gp": "video", "ts": "video", "vob": "video", "mpv": "video", "m2ts": "video",
    # image
    "jpg": "image", "jpeg": "image", "png": "image", "gif": "image", "bmp": "image",
    "svg": "image", "heic": "image", "heif": "image", "tif": "image", "tiff": "image",
    "webp": "image", "raw": "image", "ico": "image",
    # document
    "pdf": "document", "doc": "document", "docx": "document", "txt": "document",
    "md": "document", "rtf": "document", "odt": "document", "xls": "document",
    "xlsx": "document", "ppt": "document", "pptx": "document", "csv": "document",
    "epub": "document", "mobi": "document", "pages": "document", "numbers": "document",
    # archive
    "zip": "archive", "rar": "archive", "7z": "archive", "tar": "archive",
    "gz": "archive", "bz2": "archive", "xz": "archive", "iso": "archive",
    # installable / executable
    "exe": "executable", "msi": "executable", "apk": "executable", "deb": "executable",
    "rpm": "executable", "dmg": "executable", "appimage": "executable", "bat": "executable",
    "cmd": "executable", "sh": "executable", "ps1": "executable", "jar": "executable",
    # code
    "py": "code", "js": "code", "ts": "code", "go": "code", "rs": "code", "c": "code",
    "cpp": "code", "h": "code", "java": "code", "rb": "code", "php": "code",
    "json": "code", "yaml": "code", "yml": "code", "toml": "code", "xml": "code",
    "html": "code", "css": "code", "sql": "code", "kt": "code", "swift": "code",
}

#: what "playable" means — the kinds a media request may resolve to
PLAYABLE = ("audio", "video")
MEDIA = ("audio", "video", "image")

#: directories skipped by default. Declared here and reported by every scan (§D6):
#: a skipped directory is a coverage hole the owner can see, not a silent one.
DEFAULT_EXCLUDES: frozenset[str] = frozenset({
    "$recycle.bin", "system volume information", "recovery", "perflogs",
    "$sysreset", "windows.old", "config.msi", "found.000",
    ".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".venv", "venv", ".tox", ".nox", ".gradle", ".idea",
    "node_modules", ".cache", ".npm", ".yarn", ".cargo", ".rustup",
    "appdata\\local\\temp", "tmp", "temp",
})

#: filename tokens that decorate rather than identify. Dropping them is what lets
#: ``KAABA (Official Video) [HQ] 2019.mp4`` match a query for ``kaaba``.
NOISE_TOKENS: frozenset[str] = frozenset({
    "official", "video", "audio", "full", "hq", "hd", "sd", "4k", "8k", "1080p", "720p",
    "480p", "remaster", "remastered", "remix", "cover", "lyrics", "lyric", "karaoke",
    "instrumental", "explicit", "clean", "live", "session", "premiere", "trailer",
    "youtube", "youtu", "music", "song", "track", "album", "single", "ep", "cd", "disc",
    "part", "chapter", "episode", "ep", "new", "latest", "final", "final2", "copy",
    "copy2", "original", "untitled", "unknown", "various", "artists", "artist",
    "kbps", "bitrate", "320", "256", "192", "128", "96", "64", "vbr", "cbr",
    "mp3", "m4a", "flac", "wav", "ogg", "mp4", "mkv", "avi", "mov", "webm", "wmv",
    "x264", "x265", "h264", "h265", "hevc", "avc", "ac3", "dts", "bluray", "webrip",
    "dvdrip", "hdrip", "repack", "proper", "extended", "deluxe", "bonus", "intro",
    "outro", "the", "a", "an",
    # Media is not labelled only in English. These are the same decorations in the
    # languages a real library actually contains — without them "Kaába (Áudio Oficial)"
    # keeps two junk tokens and ranks below its own plain-spelled twin.
    "oficial", "completo", "completa", "musica", "cancion", "canción", "letra", "vivo",
    "remasterizado", "remasterizada", "completa", "filme", "cine", "videoofficial",
    "audioofficial", "hdrip", "fullhd", "originalmix", "mix", "radio", "edit",
    "swahili", "luganda", "translation", "translated", "subtitles", "subs",
})

_SEPARATORS = re.compile(r"[_\-.+=\[\](){}|,;:!?'\"~@#$%^&*/\\\s]+")
_TRACK_PREFIX = re.compile(r"^\s*\d{1,3}\s*[-–—.]?\s*")          # "02 - kaba"
_BY_SPLIT = re.compile(r"\s+(?:by|vs|with|ft|feat|featuring)\.?\s+", re.IGNORECASE)
_DASH_SPLIT = re.compile(r"\s+[-–—]\s+")
_YEAR = re.compile(r"^(19|20)\d{2}$")
_DIGITS = re.compile(r"^\d+$")
_SUFFIXES = ("s", "es", "ing", "ed", "'s", "ly")

# signal → weight. Tunable in one place because "what counts as a good match" is a
# claim about the world, and claims belong where they can be read and changed.
WEIGHTS: dict[str, float] = {
    "exact": 1.00,
    "token": 0.86,
    "title_artist": 0.80,
    "edit": 0.62,
    "trigram": 0.55,
    "subsequence": 0.40,
    "stem": 0.34,
}

#: below this the index says "nothing matched" rather than returning a guess (§D6:
#: an unexplained result is worse than no result — the fallback path exists for that).
DEFAULT_THRESHOLD = 0.30


# ------------------------------------------------------------------- normalisation

def strip_diacritics(text: str) -> str:
    """``Kaába`` → ``kaaba``: fold to ASCII where folding loses nothing but accents."""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    # if folding ate real content (e.g. CJK, Cyrillic), keep the decomposed original
    return ascii_only if ascii_only.strip() else unicodedata.normalize("NFKC", text)


def normalize_name(name: str, drop_noise: bool = True) -> str:
    """The form every signal matches against: folded, separated, de-noised."""
    text = strip_diacritics(name).lower()
    text = _SEPARATORS.sub(" ", text)
    tokens = [t for t in text.split() if t]
    if drop_noise:
        kept = [t for t in tokens
                if t not in NOISE_TOKENS and not _YEAR.match(t) and not _DIGITS.match(t)]
        # never reduce a name to nothing — "official.mp4" still has to be findable
        tokens = kept or tokens
    return " ".join(tokens)


def stem(word: str) -> str:
    """Cheap suffix stemmer — enough for plural/possessive/gerund noise, no dependencies."""
    for suffix in sorted(_SUFFIXES, key=len, reverse=True):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def ext_of(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def kind_of(name: str) -> str:
    return KIND_BY_EXT.get(ext_of(name), "other")


def title_artist_variants(text: str) -> list[tuple[str, str]]:
    """Split a name into (title, artist) both ways it is commonly written.

    ``Kaba by Kapeke`` → title ``kaba``, artist ``kapeke``.
    ``Kapeke - Kaba`` → ambiguous, so *both* orders are returned and the caller scores
    both; guessing one convention would silently lose half of any real library.
    """
    variants: list[tuple[str, str]] = []
    match = _BY_SPLIT.search(text)
    if match:
        left, right = text[: match.start()].strip(), text[match.end():].strip()
        if left and right:
            variants.append((left, right))
    parts = _DASH_SPLIT.split(text)
    if len(parts) == 2 and all(p.strip() for p in parts):
        a, b = parts[0].strip(), parts[1].strip()
        variants.append((a, b))
        variants.append((b, a))
    return variants


# ------------------------------------------------------------------- match signals

def trigrams(text: str) -> set[str]:
    if len(text) < 3:
        return {text} if text else set()
    return {text[i:i + 3] for i in range(len(text) - 2)}


def dice(a: str, b: str) -> float:
    """Sørensen-Dice over trigrams: position-independent, typo-tolerant, 0..1."""
    left, right = trigrams(a), trigrams(b)
    if not left or not right:
        return 0.0
    return 2.0 * len(left & right) / (len(left) + len(right))


def is_subsequence(needle: str, haystack: str) -> bool:
    """``kbd`` in ``keyboard`` — letters in order, gaps allowed."""
    if not needle:
        return False
    it = iter(haystack)
    return all(any(ch == c for c in it) for ch in needle)


def edit_distance(a: str, b: str, max_distance: int = 3) -> int:
    """Damerau-Levenshtein, bounded — returns ``max_distance + 1`` when too far apart.

    The bound is the performance trick: comparing ``kaba`` against a 40-character path
    costs nothing once the length difference alone exceeds the budget.
    """
    la, lb = len(a), len(b)
    if abs(la - lb) > max_distance:
        return max_distance + 1
    previous2: Optional[list[int]] = None
    previous = list(range(lb + 1))
    for i in range(1, la + 1):
        current = [i] + [0] * lb
        best = current[0]
        ca = a[i - 1]
        for j in range(1, lb + 1):
            cost = 0 if ca == b[j - 1] else 1
            value = min(current[j - 1] + 1, previous[j] + 1, previous[j - 1] + cost)
            if (i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == b[j - 1]):
                value = min(value, previous2[j - 2] + 1)  # transposition
            current[j] = value
            if value < best:
                best = value
        if best > max_distance:
            return max_distance + 1
        previous2, previous = previous, current
    return previous[lb]


def edit_similarity(a: str, b: str, max_distance: int = 3) -> float:
    if not a or not b:
        return 0.0
    distance = edit_distance(a, b, max_distance)
    if distance > max_distance:
        return 0.0
    return 1.0 - distance / max(len(a), len(b))


# ------------------------------------------------------------------------- records

@dataclass(slots=True)
class FileRecord:
    """One indexed file. ``norm``/``tokens`` are derived once, at index time."""

    path: str
    name: str
    ext: str
    kind: str
    size: int
    mtime: float
    depth: int
    norm: str = ""
    tokens: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        stem_name = self.name[: -(len(self.ext) + 1)] if self.ext else self.name
        self.norm = normalize_name(stem_name)
        self.tokens = tuple(self.norm.split())

    def to_row(self) -> tuple[str, str, str, int, float, int]:
        return (self.path, self.name, self.ext, self.kind, self.size, self.mtime, self.depth)  # type: ignore[return-value]

    @property
    def age_days(self) -> float:
        return max(0.0, (time.time() - self.mtime) / 86400.0)


@dataclass(slots=True)
class Match:
    """A ranked hit — with the reasons it was ranked there (§D6 provenance)."""

    record: FileRecord
    score: float
    signals: dict[str, float]
    why: list[str]

    @property
    def path(self) -> str:
        return self.record.path

    @property
    def name(self) -> str:
        return self.record.name

    @property
    def kind(self) -> str:
        return self.record.kind

    def to_text(self) -> str:
        return f"{self.record.name} ({self.record.kind}, {self.score:.2f}) — {'; '.join(self.why)}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.record.path,
            "name": self.record.name,
            "kind": self.record.kind,
            "score": round(self.score, 4),
            "signals": {k: round(v, 4) for k, v in self.signals.items()},
            "why": list(self.why),
        }


@dataclass
class ScanReport:
    """What a scan actually covered — coverage holes are reported, never silent."""

    roots: list[str] = field(default_factory=list)
    files: int = 0
    directories: int = 0
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    seconds: float = 0.0
    reused_directories: int = 0

    @property
    def files_per_second(self) -> float:
        return self.files / self.seconds if self.seconds else 0.0

    def to_text(self) -> str:
        rate = f"{self.files_per_second:,.0f} files/s" if self.seconds else "instant"
        return (f"indexed {self.files:,} file(s) in {self.directories:,} dir(s) "
                f"from {len(self.roots)} root(s) in {self.seconds:.2f}s ({rate}); "
                f"skipped {len(self.skipped)} excluded dir(s), {len(self.errors)} error(s), "
                f"reused {self.reused_directories} unchanged dir(s)")


@dataclass(slots=True)
class Query:
    """A parsed search: the words, the normalised form, and the kind filter."""

    raw: str
    norm: str
    tokens: tuple[str, ...]
    kinds: tuple[str, ...] = ()
    limit: int = 10
    threshold: float = DEFAULT_THRESHOLD

    @property
    def longest(self) -> str:
        return max(self.tokens, key=len) if self.tokens else self.norm


def parse_query(text: str, kinds: Sequence[str] = (), limit: int = 10,
                threshold: float = DEFAULT_THRESHOLD) -> Query:
    norm = normalize_name(text, drop_noise=True) or normalize_name(text, drop_noise=False)
    tokens = tuple(t for t in norm.split() if t)
    return Query(raw=text.strip(), norm=norm, tokens=tokens, kinds=tuple(kinds),
                 limit=limit, threshold=threshold)


# --------------------------------------------------------------------------- index

class FileIndex:
    """The machine's memory of where things are (§D7 "memory of the body").

    Portable by construction: pure stdlib, no service to install, works on a filesystem
    the sandbox can see and on the owner's real drives alike. Scans are incremental, so
    the index can be refreshed often enough to be trusted.
    """

    def __init__(self, roots: Sequence[str] = (), exclude_dirs: Iterable[str] = DEFAULT_EXCLUDES,
                 max_depth: int = 64) -> None:
        self.roots: list[str] = [str(Path(r)) for r in roots]
        self.exclude_dirs: frozenset[str] = frozenset(exclude_dirs)
        self.max_depth = max_depth
        self.records: list[FileRecord] = []
        self._by_dir: dict[str, list[int]] = {}
        self._dir_signature: dict[str, tuple[float, int, int]] = {}
        self.last_scan: Optional[ScanReport] = None

    # ------------------------------------------------------------------ scanning

    def __len__(self) -> int:
        return len(self.records)

    def stats(self) -> dict[str, Any]:
        kinds: dict[str, int] = {}
        for record in self.records:
            kinds[record.kind] = kinds.get(record.kind, 0) + 1
        return {
            "files": len(self.records),
            "directories": len(self._by_dir),
            "kinds": dict(sorted(kinds.items(), key=lambda kv: -kv[1])),
            "roots": list(self.roots),
            "excluded": sorted(self.exclude_dirs),
        }

    def scan(self, roots: Optional[Sequence[str]] = None, incremental: bool = True) -> ScanReport:
        """Walk the given roots (or the configured ones) and (re)build the name table."""
        targets = [str(Path(r)) for r in (roots or self.roots)]
        report = ScanReport(roots=targets)
        started = time.perf_counter()

        seen_dirs: set[str] = set()
        stack: list[tuple[str, int]] = [(root, 0) for root in reversed(targets)]
        new_records: list[FileRecord] = []

        while stack:
            directory, depth = stack.pop()
            if depth > self.max_depth:
                report.skipped.append(f"{directory} (max depth {self.max_depth})")
                continue
            seen_dirs.add(directory)

            if incremental:
                signature = self._signature(directory)
                if signature is not None and self._dir_signature.get(directory) == signature:
                    report.reused_directories += 1
                    kept = self._by_dir.get(directory, [])
                    for position in kept:
                        new_records.append(self.records[position])
                    # children still need walking: a dir's own signature does not cover them
                    try:
                        with os.scandir(directory) as handle:
                            for entry in handle:
                                if entry.is_dir(follow_symlinks=False):
                                    stack.append((entry.path, depth + 1))
                    except OSError as error:
                        report.errors.append(f"{directory}: {error}")
                    continue
                if signature is not None:
                    self._dir_signature[directory] = signature

            report.directories += 1
            child_indices: list[int] = []
            try:
                with os.scandir(directory) as handle:
                    entries = list(handle)
            except OSError as error:
                report.errors.append(f"{directory}: {error}")
                continue

            for entry in entries:
                name = entry.name
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    is_dir = False
                if is_dir:
                    if name.lower() in self.exclude_dirs:
                        report.skipped.append(entry.path)
                        continue
                    stack.append((entry.path, depth + 1))
                    continue
                try:
                    stat = entry.stat(follow_symlinks=False)
                except OSError as error:
                    report.errors.append(f"{entry.path}: {error}")
                    continue
                record = FileRecord(
                    path=entry.path, name=name, ext=ext_of(name), kind=kind_of(name),
                    size=stat.st_size, mtime=stat.st_mtime, depth=depth,
                )
                child_indices.append(len(new_records))
                new_records.append(record)
                report.files += 1

            self._by_dir[directory] = child_indices

        # directory signature table is rebuilt from what we actually walked
        self.records = new_records
        for directory in list(self._dir_signature):
            if directory not in seen_dirs:
                del self._dir_signature[directory]
        # indices in _by_dir must point at the new list; rebuild cheaply
        rebuilt: dict[str, list[int]] = {}
        for position, record in enumerate(self.records):
            rebuilt.setdefault(str(Path(record.path).parent), []).append(position)
        self._by_dir = rebuilt

        report.seconds = time.perf_counter() - started
        self.last_scan = report
        return report

    @staticmethod
    def _signature(directory: str) -> Optional[tuple[float, int, int]]:
        """A directory's cheap change-detector: mtime + size + entry count."""
        try:
            stat = os.stat(directory)
            with os.scandir(directory) as handle:
                count = sum(1 for _ in handle)
        except OSError:
            return None
        return (stat.st_mtime, stat.st_size, count)

    # ------------------------------------------------------------------- querying

    def candidates(self, query: Query) -> Iterator[FileRecord]:
        """Cheap pre-filter: skip records that cannot possibly match, before scoring."""
        kinds = query.kinds
        needle = query.longest
        for record in self.records:
            if kinds and record.kind not in kinds:
                continue
            if needle and len(needle) > 3 and needle not in record.norm and needle not in record.path.lower():
                # still allowed through on edit/trigram similarity for short or typo'd queries
                if not any(edit_similarity(needle, token, 2) > 0 for token in record.tokens):
                    continue
            yield record

    def score(self, record: FileRecord, query: Query) -> Optional[Match]:
        """Combine the §D6 signals into one 0..1 score plus the reasons behind it."""
        if not query.tokens:
            return None
        signals: dict[str, float] = {}
        why: list[str] = []
        norm = record.norm
        lowered_path = record.path.lower()

        # exact substring — the strongest, least ambiguous evidence
        if query.norm and query.norm in norm:
            signals["exact"] = 1.0
            why.append(f"'{query.norm}' appears verbatim in the name")
        elif query.norm and query.norm in lowered_path:
            signals["exact"] = 0.72
            why.append(f"'{query.norm}' appears verbatim in the path (not the filename)")

        # token match — every query word present as a word
        if query.tokens and record.tokens:
            present = [t for t in query.tokens if t in record.tokens]
            if present:
                coverage = len(present) / len(query.tokens)
                signals["token"] = coverage
                why.append(f"{len(present)}/{len(query.tokens)} query word(s) match whole words: "
                           f"{', '.join(present)}")

        # title/artist splits — "Kaba by Kapeke", "Kapeke - Kaba"
        best_split = 0.0
        best_pair: Optional[tuple[str, str]] = None
        for title, artist in title_artist_variants(norm):
            hit = 0.0
            if query.norm and (query.norm in title or title in query.norm):
                hit = 1.0
            else:
                hit = max(dice(query.norm, title), edit_similarity(query.longest, title))
            if hit > best_split:
                best_split, best_pair = hit, (title, artist)
        if best_split > 0.55 and best_pair:
            signals["title_artist"] = best_split
            why.append(f"name splits into title '{best_pair[0]}' / other part '{best_pair[1]}' "
                       f"and the query matches the title at {best_split:.2f}")

        # subsequence — abbreviations, dropped vowels
        if query.longest and is_subsequence(query.longest, norm.replace(" ", "")):
            ratio = len(query.longest) / max(1, len(norm.replace(" ", "")))
            signals["subsequence"] = min(1.0, 0.5 + ratio)
            why.append(f"'{query.longest}' is a letter-subsequence of the name")

        # trigram Dice — typos and reordering
        trigram = dice(query.norm, norm)
        if not trigram:
            trigram = max((dice(query.longest, token) for token in record.tokens), default=0.0)
        if trigram > 0.25:
            signals["trigram"] = trigram
            why.append(f"trigram similarity {trigram:.2f}")

        # edit distance against the closest word — single-character slips
        closest = 0.0
        closest_word = ""
        for token in record.tokens:
            similarity = edit_similarity(query.longest, token, max_distance=3)
            if similarity > closest:
                closest, closest_word = similarity, token
        if closest > 0.5:
            signals["edit"] = closest
            why.append(f"'{query.longest}' is within edit distance of '{closest_word}' "
                       f"(similarity {closest:.2f})")

        # stemmed comparison — plurals, possessives, gerunds
        query_stems = {stem(t) for t in query.tokens if len(t) > 3}
        record_stems = {stem(t) for t in record.tokens if len(t) > 3}
        if query_stems and query_stems & record_stems:
            overlap = len(query_stems & record_stems) / len(query_stems)
            if "token" not in signals or overlap > signals["token"]:
                signals["stem"] = overlap
                why.append(f"stemmed match on {', '.join(sorted(query_stems & record_stems))}")

        if not signals:
            return None

        # Divide only by the evidence that *could* have existed for this name. A
        # one-word filename can never fire the title/artist signal, and a three-letter
        # query can never fire the stemmer — counting those against the score is what
        # made short, common names (kaba.mp3, KAABA.mpg) rank below their own decoys.
        applicable = ["exact", "token", "subsequence", "trigram", "edit"]
        if title_artist_variants(norm):
            applicable.append("title_artist")
        if any(len(t) > 3 for t in query.tokens):
            applicable.append("stem")
        total = sum(WEIGHTS[name] * value for name, value in signals.items())
        total /= sum(WEIGHTS[name] for name in applicable)

        # small, declared bonuses: shallower paths and fresher files are more likely to be
        # the one a human means. Bounded so they can never outrank the text signals.
        depth_bonus = max(0.0, 0.04 - 0.005 * record.depth)
        fresh_bonus = 0.02 if record.age_days < 30 else 0.0
        total = min(1.0, total + depth_bonus + fresh_bonus)
        if depth_bonus:
            why.append(f"shallow path (+{depth_bonus:.3f})")
        if fresh_bonus:
            why.append(f"modified {record.age_days:.0f} day(s) ago (+{fresh_bonus:.3f})")

        if total < query.threshold:
            return None
        return Match(record=record, score=round(total, 4), signals=signals, why=why)

    def search(self, text: str, kinds: Sequence[str] = (), limit: int = 10,
               threshold: float = DEFAULT_THRESHOLD) -> list[Match]:
        """Ranked results for a human-shaped query, each able to explain itself."""
        query = parse_query(text, kinds=kinds, limit=limit, threshold=threshold)
        if not query.tokens:
            return []
        matches: list[Match] = []
        for record in self.candidates(query):
            match = self.score(record, query)
            if match is not None:
                matches.append(match)
        matches.sort(key=lambda m: (-m.score, m.record.depth, m.record.path))
        return matches[:limit]

    def find_one(self, text: str, kinds: Sequence[str] = ()) -> Optional[Match]:
        hits = self.search(text, kinds=kinds, limit=2)
        if not hits:
            return None
        # a tie at the top is not a decision — say so instead of picking arbitrarily
        if len(hits) == 2 and abs(hits[0].score - hits[1].score) < 0.02:
            return None
        return hits[0]

    # -------------------------------------------------------------- persistence

    def save(self, path: str | Path) -> int:
        """Persist as JSONL: one signature header, then one row per file."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            handle.write("beanie-index\t1\n")
            for directory, signature in self._dir_signature.items():
                handle.write(f"D\t{directory}\t{signature[0]}\t{signature[1]}\t{signature[2]}\n")
            for record in self.records:
                handle.write(
                    f"F\t{record.path}\t{record.name}\t{record.ext}\t{record.kind}\t"
                    f"{record.size}\t{record.mtime:.6f}\t{record.depth}\n"
                )
        return len(self.records)

    def load(self, path: str | Path) -> int:
        source = Path(path)
        if not source.exists():
            return 0
        self.records = []
        self._dir_signature = {}
        with source.open("r", encoding="utf-8") as handle:
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if not parts or parts[0] not in ("F", "D"):
                    continue
                if parts[0] == "D":
                    self._dir_signature[parts[1]] = (float(parts[2]), int(parts[3]), int(parts[4]))
                    continue
                self.records.append(FileRecord(
                    path=parts[1], name=parts[2], ext=parts[3], kind=parts[4],
                    size=int(parts[5]), mtime=float(parts[6]), depth=int(parts[7]),
                ))
        rebuilt: dict[str, list[int]] = {}
        for position, record in enumerate(self.records):
            rebuilt.setdefault(str(Path(record.path).parent), []).append(position)
        self._by_dir = rebuilt
        return len(self.records)
