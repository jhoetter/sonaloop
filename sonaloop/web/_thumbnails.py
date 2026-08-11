"""Bounded, tenant-partitioned raster thumbnails for the Inspector.

Browser thumbnails are a presentation derivative, never a new content capability:
the avatar/asset routes resolve the authenticated record and original bytes first,
then call this module.  Cached derivatives live under the *active* runtime partition
and are addressed only by a digest of already-authorized bytes plus a fixed variant.
No user-controlled path is accepted here.
"""
from __future__ import annotations

import hashlib
import io
import tempfile
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .. import config


AVATAR_THUMBNAIL_PX = 96
ASSET_THUMBNAIL_PX = 640

_ALGORITHM_VERSION = "v1"
_ALLOWED_VARIANTS = {"avatar", "asset"}
_ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP", "GIF", "BMP"}
_MAX_SOURCE_BYTES = 25 * 1024 * 1024
_MAX_DIMENSION = 12_000
_MAX_PIXELS = 20_000_000
_MAX_CACHED_BYTES = 4 * 1024 * 1024


def _thumbnail_cache_path(data: bytes, *, variant: str, max_side: int) -> Path:
    """A contained content-addressed path inside the current workspace partition."""
    if variant not in _ALLOWED_VARIANTS:
        raise ValueError("unknown thumbnail variant")
    if not 32 <= int(max_side) <= 1024:
        raise ValueError("thumbnail size is outside the supported range")
    digest = hashlib.sha256(data).hexdigest()
    root = (config.partition_dir() / "thumbnails" / _ALGORITHM_VERSION).resolve()
    target = (root / f"{variant}-{max_side}-{digest}.webp").resolve()
    if not target.is_relative_to(root):  # defence in depth; every component is server-owned.
        raise ValueError("thumbnail path escapes the active partition")
    return target


def _valid_cached_webp(target: Path) -> bytes | None:
    try:
        if not target.is_file() or target.stat().st_size > _MAX_CACHED_BYTES:
            return None
        data = target.read_bytes()
    except OSError:
        return None
    return data if data.startswith(b"RIFF") and data[8:12] == b"WEBP" else None


def _render_webp(data: bytes, *, max_side: int) -> bytes:
    if not data or len(data) > _MAX_SOURCE_BYTES:
        raise ValueError("thumbnail source is empty or too large")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                fmt = str(probe.format or "").upper()
                width, height = probe.size
                if fmt not in _ALLOWED_FORMATS:
                    raise ValueError("thumbnail source is not a supported inert raster")
                if (width < 1 or height < 1 or width > _MAX_DIMENSION
                        or height > _MAX_DIMENSION or width * height > _MAX_PIXELS):
                    raise ValueError("thumbnail source exceeds the decode budget")
                probe.seek(0)  # Animated inputs deliberately use their first frame only.
                image = ImageOps.exif_transpose(probe)
                image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS,
                                reducing_gap=2.0)
                if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                    image = image.convert("RGBA")
                else:
                    image = image.convert("RGB")
                out = io.BytesIO()
                image.save(out, format="WEBP", quality=82, method=4, exact=True)
                rendered = out.getvalue()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning,
            UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ValueError("thumbnail source could not be decoded safely") from exc
    if not rendered.startswith(b"RIFF") or rendered[8:12] != b"WEBP":
        raise ValueError("thumbnail encoder returned an invalid image")
    return rendered


def thumbnail_webp(data: bytes, *, variant: str, max_side: int) -> bytes:
    """Return a bounded WebP thumbnail, cached only in the active tenant partition.

    Authorization intentionally stays with the calling opaque-id route.  Even a cache
    hit is reached only after that route has re-resolved the record and original bytes.
    """
    target = _thumbnail_cache_path(data, variant=variant, max_side=max_side)
    if cached := _valid_cached_webp(target):
        return cached
    rendered = _render_webp(data, max_side=max_side)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Concurrent requests may derive the same file.  Each writes its own temp file;
    # atomic replace makes either identical result safe to win.
    tmp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
                dir=target.parent, prefix=f".{target.name}.", suffix=".tmp",
                delete=False) as tmp:
            tmp.write(rendered)
            tmp_name = tmp.name
        Path(tmp_name).replace(target)
    finally:
        if tmp_name:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except OSError:
                pass
    return rendered


def thumbnail_headers(filename: str) -> dict[str, str]:
    """Security/privacy headers shared by both authenticated thumbnail routes."""
    from urllib.parse import quote

    safe_name = f"{Path(filename).stem or 'thumbnail'}.webp"
    return {
        # URLs intentionally omit the workspace id.  Never let a browser or proxy
        # replay one workspace's pixels after the user switches active workspace.
        "Cache-Control": "private, no-store",
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(safe_name, safe='')}",
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Cross-Origin-Resource-Policy": "same-origin",
        "X-Content-Type-Options": "nosniff",
    }
