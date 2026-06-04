from __future__ import annotations

import hashlib
import io
import json
import subprocess
import os
import tempfile
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import exifread
import fitz


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".webp"}
PDF_EXTENSIONS = {".pdf"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}


def _ratio_to_float(value: Any) -> Optional[float]:
    """Convert EXIF rational values to float when possible."""
    try:
        if hasattr(value, "num") and hasattr(value, "den"):
            return float(value.num) / float(value.den) if value.den else None
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _convert_gps_coord(coord: Any, ref: str) -> Optional[float]:
    """Convert EXIF GPS coordinates into decimal degrees."""
    try:
        degrees = _ratio_to_float(coord[0])
        minutes = _ratio_to_float(coord[1])
        seconds = _ratio_to_float(coord[2])
        if degrees is None or minutes is None or seconds is None:
            return None
        decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
        if ref in {"S", "W"}:
            decimal = -decimal
        return round(decimal, 6)
    except (TypeError, IndexError):
        return None


def _parse_iso6709(location: str) -> Tuple[Optional[float], Optional[float]]:
    """Parse ISO6709 GPS location strings if present in video metadata."""
    if not location:
        return None, None
    try:
        trimmed = location.strip().rstrip("/")
        if trimmed[0] not in {"+", "-"}:
            return None, None
        # Split on the second sign for longitude
        for idx in range(1, len(trimmed)):
            if trimmed[idx] in {"+", "-"}:
                lat = float(trimmed[:idx])
                lon = float(trimmed[idx:])
                return round(lat, 6), round(lon, 6)
    except (ValueError, IndexError):
        return None, None
    return None, None


def _hash_file(file_bytes: bytes) -> Dict[str, str]:
    """Compute file hashes for integrity verification."""
    return {
        "md5": hashlib.md5(file_bytes).hexdigest(),
        "sha256": hashlib.sha256(file_bytes).hexdigest(),
    }


def _detect_file_type(filename: str) -> str:
    """Detect file type based on extension."""
    extension = "." + filename.lower().split(".")[-1] if "." in filename else ""
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in PDF_EXTENSIONS:
        return "pdf"
    if extension in VIDEO_EXTENSIONS:
        return "video"
    return "unknown"


def _extract_image_metadata(file_bytes: bytes) -> Dict[str, Any]:
    """Extract metadata from image files using EXIF."""
    tags = exifread.process_file(io.BytesIO(file_bytes), details=False)
    gps_lat = None
    gps_lon = None
    if "GPS GPSLatitude" in tags and "GPS GPSLatitudeRef" in tags:
        gps_lat = _convert_gps_coord(tags["GPS GPSLatitude"].values, str(tags["GPS GPSLatitudeRef"]))
    if "GPS GPSLongitude" in tags and "GPS GPSLongitudeRef" in tags:
        gps_lon = _convert_gps_coord(
            tags["GPS GPSLongitude"].values, str(tags["GPS GPSLongitudeRef"])
        )

    data = {
        "gps_latitude": gps_lat,
        "gps_longitude": gps_lon,
        "camera_make": str(tags.get("Image Make", "")) or None,
        "camera_model": str(tags.get("Image Model", "")) or None,
        "datetime": str(tags.get("EXIF DateTimeOriginal", "")) or str(tags.get("Image DateTime", "")) or None,
        "software": str(tags.get("Image Software", "")) or None,
        "author": str(tags.get("Image Artist", "")) or None,
        "orientation": str(tags.get("Image Orientation", "")) or None,
    }
    return data


def _extract_pdf_metadata(file_bytes: bytes) -> Dict[str, Any]:
    """Extract metadata from PDF files using PyMuPDF."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    metadata = doc.metadata or {}
    data = {
        "author": metadata.get("author"),
        "creator": metadata.get("creator"),
        "producer": metadata.get("producer"),
        "creation_date": metadata.get("creationDate"),
        "modification_date": metadata.get("modDate"),
        "subject": metadata.get("subject"),
        "keywords": metadata.get("keywords"),
        "page_count": doc.page_count,
        "encrypted": doc.is_encrypted,
    }
    doc.close()
    return data


def _extract_video_metadata(file_bytes: bytes) -> Dict[str, Any]:
    """Extract metadata from videos using ffprobe."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".video") as temp_file:
        temp_file.write(file_bytes)
        temp_path = temp_file.name

    try:
        command = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            temp_path,
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "ffprobe failed")

        payload = json.loads(result.stdout or "{}")
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
    format_info = payload.get("format", {})
    streams = payload.get("streams", [])

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    tags = format_info.get("tags", {})
    location_tag = tags.get("location") or tags.get("com.apple.quicktime.location.ISO6709")
    gps_lat, gps_lon = _parse_iso6709(location_tag) if location_tag else (None, None)

    r_frame_rate = video_stream.get("r_frame_rate") or video_stream.get("avg_frame_rate")
    frame_rate = None
    if r_frame_rate and "/" in r_frame_rate:
        num, den = r_frame_rate.split("/")
        try:
            frame_rate = round(float(num) / float(den), 2) if float(den) else None
        except ValueError:
            frame_rate = None

    data = {
        "duration": float(format_info.get("duration")) if format_info.get("duration") else None,
        "bitrate": int(format_info.get("bit_rate")) if format_info.get("bit_rate") else None,
        "codec": video_stream.get("codec_name"),
        "resolution": f"{video_stream.get('width')}x{video_stream.get('height')}" if video_stream else None,
        "frame_rate": frame_rate,
        "creation_time": tags.get("creation_time"),
        "gps_latitude": gps_lat,
        "gps_longitude": gps_lon,
    }
    return data


def extract_metadata(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Extract metadata from images, PDFs, and videos."""
    file_type = _detect_file_type(filename)
    flags = {"gps_flag": False, "identity_flag": False}
    try:
        if file_type == "image":
            data = _extract_image_metadata(file_bytes)
        elif file_type == "pdf":
            data = _extract_pdf_metadata(file_bytes)
        elif file_type == "video":
            data = _extract_video_metadata(file_bytes)
        else:
            return {
                "success": False,
                "data": {},
                "file_type": file_type,
                "flags": flags,
                "error": "Unsupported file type",
            }

        data["hashes"] = _hash_file(file_bytes)

        if data.get("gps_latitude") is not None and data.get("gps_longitude") is not None:
            flags["gps_flag"] = True
        if data.get("author") or data.get("creator"):
            flags["identity_flag"] = True

        return {
            "success": True,
            "data": data,
            "file_type": file_type,
            "flags": flags,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - return structured error
        return {
            "success": False,
            "data": {},
            "file_type": file_type,
            "flags": flags,
            "error": str(exc),
        }
