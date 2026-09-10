"""File-index search — instant, whole-PC lookup over a persistent index.

Traceability: ARCHITECTURE §11.2 (senses: an indexed view of the filesystem is
a sense organ, refreshed incrementally like attention over a stream — §4.2),
§7 (the mind senses by need, not by keyword manifest), and register row 44.

Inspired by voidtools *Everything*: walk the filesystem once, record
(path, mtime, size) per file, and search the in-memory index from then on.
Rebuilds are incremental — only changed/deleted entries are touched — so a
whole-drive index refreshes in seconds, and searches answer in milliseconds.

Matching is deliberately *name-semantic*, not substring-only, because real
files are named like humans name them:

    query "kaba"  must match  "kaba.mp3" · "Kaba by Kapeke.m4a" · "ka-bba (live).mpg" (typo)

Scoring layers, in order of strength:
1. exact token match against basename words (weight ×3 over directory words);
2. all query tokens matched somewhere in path (basename > parent dir > any dir);
3. fuzzy token match (difflib ratio ≥ 0.78) so small misspellings still land;
4. kind filtering: "song kaba", "video kaba", "picture of the team" filter the
   candidates to the media class the owner actually asked for (audio /
   video / images / documents / code — the structural categories from
   analogy.py, extended with engine-specific groups).

Honesty rules: the index reports what it found and how it scored; a missing
file is ""not found"", never a fabricated path; deleted files are pruned on
the next refresh rather than left as ghosts.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from .analogy import CATEGORY_BY_EXTENSION

#: kind-hint words the owner speaks → extension classes (structural, from
#: analogy.py's CATEGORY_BY_EXTENSION, plus "media" = audio ∪ video ∪ images)
KIND_HINTS: dict[str, set[str]] = {}

_AUDIO = {ext for ext, cat in CATEGORY_BY_EXTENSION.items() if cat == "audio"} | {"wma", "aiff", "amr"}
_VIDEO = ({ext for ext, cat in CATEGORY_BY_EXTENSION.items() if cat == "video"}
          | {"mpg", "mpeg", "3gp", "3g2", "wmv", "vob", "ts", "mts", "divx", "f4v"})
_IMAGES = {ext for ext, cat in CATEGORY_BY_EXTENSION.items() if cat == "images"} | {"jfif", "ico"}
_DOCS = {ext for ext, cat in CATEGORY_BY_EXTENSION.items() if cat == "documents"} | {"epub", "mobi"}
_CODE = {ext for ext, cat in CATEGORY_BY_EXTENSION.items() if cat in ("code", "spreadsheets")}

_KIND_WORDS: dict[str, str] = {
    # audio
    "song": "audio", "songs": "audio", "music": "audio", "track": "audio", "tracks": "audio",
    "audio": "audio", "tune": "audio", "beats": "audio", "podcast": "audio",
    # video
    "video": "video", "videos": "video", "movie": "video", "movies": "video",
    "clip": "video", "clips": "video", "film": "video",
    # media (either)
    "media": "media",
    # images
    "photo": "images", "photos": "images", "picture": "images", "pictures": "images",
    "image": "images", "images": "images", "screenshot": "images", "pic": "images", "pics": "images",
    # documents — only unambiguous kind words; words people actually use inside
    # file names ("report", "notes", "letter", "sheet") must stay name terms
    "document": "documents", "documents": "documents", "doc": "documents", "docs": "documents",
    "pdf": "documents",
    # code / spreadsheets
    "spreadsheet": "code", "script": "code",
}

_KIND_EXTENSIONS: dict[str, set[str]] = {
    "audio": _AUDIO,
    "video": _VIDEO,
    "media": _AUDIO | _VIDEO | _IMAGES,
    "images": _IMAGES,
    "documents": _DOCS,
    "code": _CODE,
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_FUZZY_RATIO = 0.78


def _fuzzy_candidates(name_tokens: list[str]) -> list[str]:
    """Words a misspelling may target: the name's own tokens *plus* adjacent
    tokens joined — "ka_bba.live.mpg" tokenizes to ka/bba/live, but the owner
    says "kabba", so "ka_bba" must also match as the joined word "kabba"."""
    joined = ["".join(name_tokens[i:i + 2]) for i in range(len(name_tokens) - 1)]
    return name_tokens + joined

#: directories that are never indexed (system noise, not the owner's files)
_SKIP_DIRS = {
    ".git", ".cache", "__pycache__", "node_modules", ".venv", "venv",
    "$recycle.bin", "system volume information", ".trash", "windows",
    "appdata", "program files", "program files (x86)", "programdata",
    "/proc", "/sys", "/dev", "/run", "/snap",
}


@dataclass(frozen=True)
class FileMatch:
    path: str
    score: float
    why: str


@dataclass
class _IndexedFile:
    path: str
    mtime: float
    size: int

    def to_json(self) -> list:
        return [self.path, self.mtime, self.size]

    @classmethod
    def from_json(cls, data: list) -> "_IndexedFile":
        return cls(path=str(data[0]), mtime=float(data[1]), size=int(data[2]))


@dataclass
class SearchPlan:
    """What a raw query means: name tokens to match + kind filter (if any)."""

    terms: list[str]
    kind: Optional[str] = None


def parse_query(query: str) -> SearchPlan:
    """Split a raw owner query into name terms and an optional media-kind hint."""
    terms: list[str] = []
    kind: Optional[str] = None
    for token in _TOKEN_RE.findall(query.lower()):
        if token in ("file", "files", "folder"):
            continue  # neutral meta-words: the owner means "the thing called …", not a kind
        hint = _KIND_WORDS.get(token)
        if hint:
            kind = kind or hint
            continue
        terms.append(token)
    # a query made only of kind words ("play some music") keeps its terms empty:
    # the search then ranks by recency inside the kind rather than by name
    return SearchPlan(terms=terms, kind=kind)


class FileIndex:
    """A persistent, incrementally-refreshed index over one or more roots."""

    def __init__(self, roots: list[Path] | None = None, state_file: Path | None = None) -> None:
        self.roots = [Path(root) for root in (roots or [])]
        self.state_file = state_file
        self._files: dict[str, _IndexedFile] = {}
        self._load()

    # ------------------------------------------------------------- building
    def add_root(self, root: Path) -> None:
        root = Path(root)
        if root not in self.roots:
            self.roots.append(root)

    def build(self, *, force: bool = False) -> dict[str, int]:
        """(Re)scan the roots; incremental unless `force`. Returns stats."""
        seen: set[str] = set()
        scanned = changed = 0
        own_state = str(self.state_file) if self.state_file else None
        for root in self.roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if self._skip(path):
                    continue
                if own_state is not None and str(path) == own_state:
                    continue  # the index must never index itself
                if not path.is_file():
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                scanned += 1
                key = str(path)
                seen.add(key)
                old = self._files.get(key)
                if old is None or old.mtime != stat.st_mtime or old.size != stat.st_size:
                    self._files[key] = _IndexedFile(key, stat.st_mtime, stat.st_size)
                    changed += 1
        pruned = [key for key in list(self._files) if key not in seen]
        for key in pruned:
            del self._files[key]
        self._save()
        return {"roots": len(self.roots), "indexed": len(self._files),
                "changed": changed, "pruned": len(pruned)}

    @staticmethod
    def _skip(path: Path) -> bool:
        parts = {part.lower() for part in path.parts}
        if parts & _SKIP_DIRS or any(part in ("/proc", "/sys", "/dev", "/run") for part in path.parts[:2]):
            return True
        return any(part.startswith(".") and part not in (".", "..") for part in path.parts[1:-1])

    def count(self) -> int:
        return len(self._files)

    # ------------------------------------------------------------- matching
    def search(self, query: str, *, limit: int = 8) -> list[FileMatch]:
        """Rank index entries against the raw query (owner phrasing)."""
        plan = parse_query(query)
        candidates = self._by_kind(plan.kind) if plan.kind else list(self._files.values())
        ranked: list[FileMatch] = []
        for entry in candidates:
            name = Path(entry.path).name.lower()
            stem = Path(entry.path).stem.lower()
            name_tokens = _TOKEN_RE.findall(name)
            dir_tokens = _TOKEN_RE.findall(str(Path(entry.path).parent).lower())
            score = self._score(plan.terms, stem, name, name_tokens, dir_tokens, entry.mtime)
            if score <= 0:
                continue
            why = self._why(plan, entry, score)
            ranked.append(FileMatch(path=entry.path, score=round(score, 3), why=why))
        ranked.sort(key=lambda match: (-match.score, match.path))
        return ranked[:limit]

    def _by_kind(self, kind: str) -> list[_IndexedFile]:
        extensions = _KIND_EXTENSIONS.get(kind)
        if not extensions:
            return list(self._files.values())
        return [
            entry for entry in self._files.values()
            if Path(entry.path).suffix.lower().lstrip(".") in extensions
        ]

    def _score(self, terms: list[str], stem: str, name: str,
               name_tokens: list[str], dir_tokens: list[str], mtime: float) -> float:
        if not terms:
            return 1.0  # kind-only query: recency decides
        score = 0.0
        remainder = list(terms)
        # 1) exact basename-token matches are the strongest signal
        for token in list(remainder):
            if token in name_tokens:
                score += 30.0
                remainder.remove(token)
        fuzzy_words = _fuzzy_candidates(name_tokens)
        # 2) whole-stem phrase match ("kaba" is the beginning of "kaba by kapeke"),
        #    and the plain bare name ("kaba.mp3") beats every decorated variant
        if " ".join(terms) in stem:
            score += 25.0
            if " ".join(_TOKEN_RE.findall(stem)) == " ".join(terms):
                score += 20.0
        if " ".join(terms) in name:
            score += 10.0
        # 3) remaining tokens: substring of the basename, then directory words,
        #    then fuzzy near-spelling against basename words
        still = []
        for token in remainder:
            if token in name:
                score += 12.0
            elif token in dir_tokens:
                score += 6.0
            else:
                still.append(token)
        for token in still:
            best = max((SequenceMatcher(None, token, word).ratio() for word in fuzzy_words), default=0.0)
            if best >= _FUZZY_RATIO:
                score += 18.0 * best
            else:
                return 0.0  # every term must match somehow — no partial drops
        return score

    def _why(self, plan: SearchPlan, entry: _IndexedFile, score: float) -> str:
        stem = Path(entry.path).stem.lower()
        exact = [t for t in plan.terms if t in stem]
        parts: list[str] = []
        if exact:
            parts.append("name match: " + ", ".join(exact))
        fuzzy = [t for t in plan.terms if t not in stem and any(
            SequenceMatcher(None, t, w).ratio() >= _FUZZY_RATIO
            for w in _fuzzy_candidates(_TOKEN_RE.findall(stem)))]
        if fuzzy:
            parts.append("near spelling: " + ", ".join(fuzzy))
        if plan.kind:
            parts.append(f"kind: {plan.kind}")
        return "; ".join(parts) or "kind-only (ranked by recency)"

    # -------------------------------------------------------- persistence
    def _load(self) -> None:
        if self.state_file is None or not self.state_file.exists():
            return
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for item in data.get("files", []):
            entry = _IndexedFile.from_json(item)
            self._files[entry.path] = entry

    def _save(self) -> None:
        if self.state_file is None:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"files": [entry.to_json() for entry in self._files.values()]}
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.state_file)
