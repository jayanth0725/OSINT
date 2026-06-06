from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from typing import Any, Dict, Iterable, Optional, Tuple

import exifread
import fitz
from PIL import Image, ImageChops, ImageCms, ImageStat


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".webp"}
PDF_EXTENSIONS = {".pdf"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}


# ---------------------------------------------------------------------------
# JSON serialisation helper
# ---------------------------------------------------------------------------

class _MetadataEncoder(json.JSONEncoder):
    """Custom encoder that handles exifread IfdTag objects and other
    non-standard types that appear in metadata payloads."""

    def default(self, obj: Any) -> Any:  # noqa: ANN001
        # exifread tags -------------------------------------------------------
        if hasattr(obj, "values"):          # IfdTag  (exifread)
            values = obj.values
            if isinstance(values, list):
                return [self._coerce(v) for v in values]
            return self._coerce(values)
        # PIL / fractions / ratios -------------------------------------------
        if hasattr(obj, "numerator") and hasattr(obj, "denominator"):
            try:
                return float(obj.numerator) / float(obj.denominator)
            except (TypeError, ZeroDivisionError):
                return str(obj)
        # bytes --------------------------------------------------------------
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        # datetime -----------------------------------------------------------
        if isinstance(obj, datetime):
            return obj.isoformat()
        # Generic fallback ---------------------------------------------------
        try:
            return str(obj)
        except Exception:
            return None

    @staticmethod
    def _coerce(value: Any) -> Any:
        """Coerce a single IfdTag value element to a plain Python type."""
        # exifread Ratio / IfdTag ratio
        if hasattr(value, "num") and hasattr(value, "den"):
            try:
                return float(value.num) / float(value.den) if value.den else None
            except (TypeError, ZeroDivisionError):
                return str(value)
        if hasattr(value, "numerator") and hasattr(value, "denominator"):
            try:
                return float(value.numerator) / float(value.denominator)
            except (TypeError, ZeroDivisionError):
                return str(value)
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if isinstance(value, (int, float, str, bool)) or value is None:
            return value
        return str(value)


def metadata_to_json(obj: Any, indent: int = 2) -> str:
    """Serialize metadata to JSON using the custom encoder."""
    return json.dumps(obj, cls=_MetadataEncoder, indent=indent)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

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


def _pick_first(source: Dict[str, Any], keys: Iterable[str]) -> Optional[Any]:
    """Return the first non-empty value for the provided keys."""
    for key in keys:
        value = source.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _ifdtag_to_python(value: Any) -> Any:
    """Recursively convert exifread IfdTag objects to plain Python types."""
    # IfdTag has a .values attribute
    if hasattr(value, "values") and not isinstance(value, (str, bytes, dict)):
        inner = value.values
        if isinstance(inner, list):
            converted = [_ifdtag_to_python(v) for v in inner]
            # Unwrap single-item lists for readability
            return converted[0] if len(converted) == 1 else converted
        return _ifdtag_to_python(inner)
    # Ratio types from exifread (Ratio / IfdTagRatio)
    if hasattr(value, "num") and hasattr(value, "den"):
        try:
            return float(value.num) / float(value.den) if value.den else None
        except (TypeError, ZeroDivisionError):
            return str(value)
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        try:
            return float(value.numerator) / float(value.denominator)
        except (TypeError, ZeroDivisionError):
            return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (list, tuple)):
        return [_ifdtag_to_python(v) for v in value]
    if isinstance(value, dict):
        return {k: _ifdtag_to_python(v) for k, v in value.items()}
    return value


def _normalize_value(value: Any) -> Optional[Any]:
    """Normalize metadata values for display and JSON serialisation."""
    if value is None:
        return None
    # Strip exifread IfdTag objects first
    value = _ifdtag_to_python(value)
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="ignore")
        except Exception:
            return None
    if isinstance(value, (list, tuple)):
        cleaned = [_normalize_value(item) for item in value if item not in (None, "")]
        return cleaned if cleaned else None
    if isinstance(value, dict):
        return {k: _normalize_value(v) for k, v in value.items()}
    return value


def _extract_emails(values: Iterable[Any]) -> list[str]:
    """Extract email addresses from metadata values."""
    pattern = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
    emails: set[str] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, dict):
            nested_values = list(value.values())
        elif isinstance(value, (list, tuple, set)):
            nested_values = list(value)
        else:
            nested_values = [value]
        for nested in nested_values:
            if nested is None:
                continue
            if not isinstance(nested, str):
                nested = str(nested)
            for match in pattern.findall(nested):
                emails.add(match.lower())
    return sorted(emails)


def _extract_exiftool_metadata(file_bytes: bytes, filename: str) -> Tuple[Dict[str, Any], Optional[str]]:
    """Extract metadata via exiftool if available."""
    if not shutil.which("exiftool"):
        return {}, "exiftool not installed"

    suffix = os.path.splitext(filename)[1] or ".img"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(file_bytes)
        temp_path = temp_file.name

    try:
        command = ["exiftool", "-json", "-struct", "-charset", "utf8", temp_path]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return {}, result.stderr.strip() or "exiftool failed"
        payload = json.loads(result.stdout or "[]")
        return (payload[0] if payload else {}), None
    except Exception as exc:  # noqa: BLE001
        return {}, str(exc)
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def _safe_open_image(file_bytes: bytes) -> Optional[Image.Image]:
    """Open image bytes safely with Pillow."""
    try:
        return Image.open(io.BytesIO(file_bytes))
    except Exception:
        return None


def _estimate_jpeg_percent(image: Image.Image, file_bytes: bytes) -> Optional[float]:
    """Estimate JPEG compression percentage relative to raw pixel data."""
    if image.format != "JPEG":
        return None
    width, height = image.size
    bands = len(image.getbands())
    raw_size = width * height * bands
    if raw_size <= 0:
        return None
    return round((len(file_bytes) / raw_size) * 100, 2)


def _compute_ela_score(image: Image.Image) -> Optional[float]:
    """Compute a basic ELA score for JPEG images."""
    if image.format != "JPEG":
        return None
    try:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, "JPEG", quality=95)
        buffer.seek(0)
        recompressed = Image.open(buffer)
        diff = ImageChops.difference(image.convert("RGB"), recompressed.convert("RGB"))
        stat = ImageStat.Stat(diff)
        return round(sum(stat.mean) / len(stat.mean), 3)
    except Exception:
        return None


def _count_hidden_pixels(image: Image.Image) -> Optional[int]:
    """Count fully transparent pixels when an alpha channel is present."""
    if "A" not in image.getbands():
        return None
    try:
        alpha = image.getchannel("A")
        return int(alpha.histogram()[0])
    except Exception:
        return None


def _get_icc_profile_name(image: Image.Image) -> Optional[str]:
    """Return ICC profile name if present."""
    profile_bytes = image.info.get("icc_profile")
    if not profile_bytes:
        return None
    try:
        profile = ImageCms.ImageCmsProfile(io.BytesIO(profile_bytes))
        return ImageCms.getProfileName(profile)
    except Exception:
        return "ICC profile present"


def _build_expanded_metadata(
    filename: str,
    file_bytes: bytes,
    tags: Dict[str, Any],
    exiftool_data: Dict[str, Any],
    image: Optional[Image.Image],
    file_type: Optional[str],
) -> Dict[str, Any]:
    """Build the expanded metadata payload requested by the UI."""
    expanded: Dict[str, Any] = {}

    mime_type, _ = mimetypes.guess_type(filename)

    ela_score = _compute_ela_score(image) if image else None
    hidden_pixels = _count_hidden_pixels(image) if image else None
    jpeg_percent = _estimate_jpeg_percent(image, file_bytes) if image else None
    icc_profile_name = _get_icc_profile_name(image) if image else None

    # --- Analysis fields ----------------------------------------------------
    expanded["ELA"] = ela_score
    expanded["Hidden Pixels"] = hidden_pixels
    expanded["ICC"] = bool(image and image.info.get("icc_profile"))
    expanded["JPEG %"] = jpeg_percent

    # --- File info ----------------------------------------------------------
    expanded["File"] = _pick_first(exiftool_data, ["FileName", "SourceFile"]) or filename
    expanded["File Type"] = _pick_first(exiftool_data, ["FileType"]) or (image.format if image else file_type)
    expanded["File Type Extension"] = _pick_first(exiftool_data, ["FileTypeExtension"]) or os.path.splitext(filename)[1].lstrip(".")
    expanded["MIME Type"] = _pick_first(exiftool_data, ["MIMEType"]) or (
        Image.MIME.get(image.format) if image else mime_type
    )

    # --- EXIF core ----------------------------------------------------------
    expanded["Exif Byte Order"] = _pick_first(exiftool_data, ["ExifByteOrder"]) or _ifdtag_to_python(_pick_first(tags, ["EXIF ExifByteOrder"]))
    expanded["Current IPTC Digest"] = _pick_first(exiftool_data, ["CurrentIPTCDigest"])
    expanded["Image Width"] = _pick_first(exiftool_data, ["ImageWidth", "ExifImageWidth"]) or (image.size[0] if image else None)
    expanded["Image Height"] = _pick_first(exiftool_data, ["ImageHeight", "ExifImageHeight"]) or (image.size[1] if image else None)
    expanded["Encoding Process"] = _pick_first(exiftool_data, ["EncodingProcess"])
    expanded["Bits Per Sample"] = _pick_first(exiftool_data, ["BitsPerSample"]) or _ifdtag_to_python(_pick_first(tags, ["Image BitsPerSample"]))
    expanded["Color Components"] = _pick_first(exiftool_data, ["ColorComponents"]) or (len(image.getbands()) if image else None)
    expanded["Y Cb Cr Sub Sampling"] = _pick_first(exiftool_data, ["YCbCrSubSampling"]) or _ifdtag_to_python(_pick_first(tags, ["Image YCbCrSubSampling"]))
    expanded["JFIF"] = _pick_first(exiftool_data, ["JFIF"]) or bool(image and image.info.get("jfif_version"))
    expanded["JFIF Version"] = _pick_first(exiftool_data, ["JFIFVersion"]) or (image.info.get("jfif_version") if image else None)
    expanded["EXIF"] = _pick_first(exiftool_data, ["EXIF", "EXIFVersion", "ExifVersion"]) or bool(tags)
    expanded["Image Description"] = _pick_first(exiftool_data, ["ImageDescription"]) or _ifdtag_to_python(_pick_first(tags, ["Image ImageDescription"]))
    expanded["Camera Model Name"] = _pick_first(exiftool_data, ["CameraModelName", "Model"]) or _ifdtag_to_python(_pick_first(tags, ["Image Model"]))
    expanded["Orientation"] = _pick_first(exiftool_data, ["Orientation"]) or _ifdtag_to_python(_pick_first(tags, ["Image Orientation"]))
    expanded["X Resolution"] = _pick_first(exiftool_data, ["XResolution"]) or _ifdtag_to_python(_pick_first(tags, ["Image XResolution"])) or (image.info.get("dpi")[0] if image and image.info.get("dpi") else None)
    expanded["Y Resolution"] = _pick_first(exiftool_data, ["YResolution"]) or _ifdtag_to_python(_pick_first(tags, ["Image YResolution"])) or (image.info.get("dpi")[1] if image and image.info.get("dpi") else None)
    expanded["Resolution Unit"] = _pick_first(exiftool_data, ["ResolutionUnit"]) or _ifdtag_to_python(_pick_first(tags, ["Image ResolutionUnit"]))
    expanded["Artist"] = _pick_first(exiftool_data, ["Artist"]) or _ifdtag_to_python(_pick_first(tags, ["Image Artist"]))
    expanded["Y Cb Cr Positioning"] = _pick_first(exiftool_data, ["YCbCrPositioning"]) or _ifdtag_to_python(_pick_first(tags, ["Image YCbCrPositioning"]))
    expanded["Copyright"] = _pick_first(exiftool_data, ["Copyright"]) or _ifdtag_to_python(_pick_first(tags, ["Image Copyright"]))

    # --- ICC Profile --------------------------------------------------------
    expanded["ICC_Profile"] = _pick_first(exiftool_data, ["ICCProfile", "ICCProfileName"]) or icc_profile_name
    expanded["Profile CMM Type"] = _pick_first(exiftool_data, ["ProfileCMMType"])
    expanded["Profile Version"] = _pick_first(exiftool_data, ["ProfileVersion"])
    expanded["Profile Class"] = _pick_first(exiftool_data, ["ProfileClass"])
    expanded["Color Space Data"] = _pick_first(exiftool_data, ["ColorSpaceData"])
    expanded["Profile Connection Space"] = _pick_first(exiftool_data, ["ProfileConnectionSpace"])
    expanded["Profile Date Time"] = _pick_first(exiftool_data, ["ProfileDateTime"])
    expanded["Drofile Date Time"] = expanded["Profile Date Time"]   # typo variant kept for compat
    expanded["Profile File Signature"] = _pick_first(exiftool_data, ["ProfileFileSignature"])
    expanded["Primary Platform"] = _pick_first(exiftool_data, ["PrimaryPlatform"])
    expanded["CMM Flags"] = _pick_first(exiftool_data, ["CMMFlags"])
    expanded["Device Manufacturer"] = _pick_first(exiftool_data, ["DeviceManufacturer"])
    expanded["Device Model"] = _pick_first(exiftool_data, ["DeviceModel"])
    expanded["Device Attributes"] = _pick_first(exiftool_data, ["DeviceAttributes"])
    expanded["Rendering Intent"] = _pick_first(exiftool_data, ["RenderingIntent"])
    expanded["Connection Space Illuminant"] = _pick_first(exiftool_data, ["ConnectionSpaceIlluminant"])
    expanded["Profile Creator"] = _pick_first(exiftool_data, ["ProfileCreator"])
    expanded["Profile ID"] = _pick_first(exiftool_data, ["ProfileID"])
    expanded["Profile Copyright"] = _pick_first(exiftool_data, ["ProfileCopyright"])
    expanded["Profile Description"] = _pick_first(exiftool_data, ["ProfileDescription"]) or icc_profile_name
    expanded["Media White Point"] = _pick_first(exiftool_data, ["MediaWhitePoint"])
    expanded["Media Black Point"] = _pick_first(exiftool_data, ["MediaBlackPoint"])
    expanded["Red Tone Reproduction Curve"] = _pick_first(exiftool_data, ["RedTRC", "RedToneReproductionCurve"])
    expanded["Green Tone Reproduction Curve"] = _pick_first(exiftool_data, ["GreenTRC", "GreenToneReproductionCurve"])
    expanded["Blue Tone Reproduction Curve"] = _pick_first(exiftool_data, ["BlueTRC", "BlueToneReproductionCurve"])
    expanded["Red Matrix Column"] = _pick_first(exiftool_data, ["RedMatrixColumn"])
    expanded["Green Matrix Column"] = _pick_first(exiftool_data, ["GreenMatrixColumn"])
    expanded["Blue Matrix Column"] = _pick_first(exiftool_data, ["BlueMatrixColumn"])

    # --- IPTC ---------------------------------------------------------------
    expanded["IPTC"] = _pick_first(exiftool_data, ["IPTC"])
    expanded["Application Record Version"] = _pick_first(exiftool_data, ["ApplicationRecordVersion"])
    expanded["Object Name"] = _pick_first(exiftool_data, ["ObjectName"])
    expanded["Supplemental Categories"] = _pick_first(exiftool_data, ["SupplementalCategories"])
    expanded["Keywords"] = _pick_first(exiftool_data, ["Keywords"])
    expanded["Special Instructions"] = _pick_first(exiftool_data, ["SpecialInstructions"])
    expanded["Date Created"] = _pick_first(exiftool_data, ["DateCreated"])
    expanded["Time Created"] = _pick_first(exiftool_data, ["TimeCreated"])
    expanded["By-line"] = _pick_first(exiftool_data, ["By-line", "Byline"])
    expanded["By-line Title"] = _pick_first(exiftool_data, ["By-lineTitle", "BylineTitle"])
    expanded["City"] = _pick_first(exiftool_data, ["City"])
    expanded["Province-State"] = _pick_first(exiftool_data, ["Province-State", "ProvinceState", "State"])
    expanded["Country-Primary Location Code"] = _pick_first(exiftool_data, ["Country-PrimaryLocationCode", "CountryPrimaryLocationCode"])
    expanded["Country-Primary Location Name"] = _pick_first(exiftool_data, ["Country-PrimaryLocationName", "CountryPrimaryLocationName", "Country"])
    expanded["Job Identifier"] = _pick_first(exiftool_data, ["JobIdentifier"])
    expanded["Headline"] = _pick_first(exiftool_data, ["Headline"])
    expanded["Credit"] = _pick_first(exiftool_data, ["Credit"])
    expanded["Source"] = _pick_first(exiftool_data, ["Source"])
    expanded["Copyright Notice"] = _pick_first(exiftool_data, ["CopyrightNotice"])
    expanded["Caption-Abstract"] = _pick_first(exiftool_data, ["Caption-Abstract", "CaptionAbstract"])

    # --- XMP ----------------------------------------------------------------
    expanded["XMP"] = _pick_first(exiftool_data, ["XMP"])
    expanded["XMP Toolkit"] = _pick_first(exiftool_data, ["XMPToolkit", "XMPToolkitVersion"])
    expanded["Creator"] = _pick_first(exiftool_data, ["Creator", "XMP-dc:Creator"])
    expanded["Description"] = _pick_first(exiftool_data, ["Description", "XMP-dc:Description"])
    expanded["Rights"] = _pick_first(exiftool_data, ["Rights", "XMP-dc:Rights"])
    expanded["Title"] = _pick_first(exiftool_data, ["Title", "XMP-dc:Title"])
    expanded["Authors Position"] = _pick_first(exiftool_data, ["AuthorsPosition", "AuthorPosition"])
    expanded["Marked"] = _pick_first(exiftool_data, ["Marked"])
    expanded["Composite"] = _pick_first(exiftool_data, ["Composite"])
    expanded["Date/Time Created"] = _pick_first(exiftool_data, ["DateTimeCreated", "CreateDate"])
    expanded["Date/Time Original"] = _pick_first(exiftool_data, ["DateTimeOriginal"])
    expanded["Image Size"] = _pick_first(exiftool_data, ["ImageSize"]) or (f"{image.size[0]}x{image.size[1]}" if image else None)
    expanded["Megapixels"] = _pick_first(exiftool_data, ["Megapixels"]) or (round((image.size[0] * image.size[1]) / 1_000_000, 2) if image else None)

    # --- Emails (scanned across all values) ---------------------------------
    emails = _extract_emails(value for value in expanded.values() if value is not None)
    expanded["Emails"] = emails if emails else None

    # Normalize every value (converts any remaining IfdTag → plain Python)
    for key, value in list(expanded.items()):
        expanded[key] = _normalize_value(value)

    return expanded


# ---------------------------------------------------------------------------
# Per-type extractors
# ---------------------------------------------------------------------------

def _extract_image_metadata(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Extract metadata from image files using EXIF."""
    tags = exifread.process_file(io.BytesIO(file_bytes), details=False)

    gps_lat = None
    gps_lon = None
    if "GPS GPSLatitude" in tags and "GPS GPSLatitudeRef" in tags:
        gps_lat = _convert_gps_coord(tags["GPS GPSLatitude"].values, str(tags["GPS GPSLatitudeRef"]))
    if "GPS GPSLongitude" in tags and "GPS GPSLongitudeRef" in tags:
        gps_lon = _convert_gps_coord(tags["GPS GPSLongitude"].values, str(tags["GPS GPSLongitudeRef"]))

    image = _safe_open_image(file_bytes)
    exiftool_data, exiftool_error = _extract_exiftool_metadata(file_bytes, filename)
    expanded_metadata = _build_expanded_metadata(
        filename=filename,
        file_bytes=file_bytes,
        tags=tags,
        exiftool_data=exiftool_data,
        image=image,
        file_type="image",
    )

    data: Dict[str, Any] = {
        "gps_latitude": gps_lat,
        "gps_longitude": gps_lon,
        "camera_make": _ifdtag_to_python(tags.get("Image Make")) or None,
        "camera_model": _ifdtag_to_python(tags.get("Image Model")) or None,
        "datetime": (
            _ifdtag_to_python(tags.get("EXIF DateTimeOriginal"))
            or _ifdtag_to_python(tags.get("Image DateTime"))
            or None
        ),
        "software": _ifdtag_to_python(tags.get("Image Software")) or None,
        "author": _ifdtag_to_python(tags.get("Image Artist")) or None,
        "orientation": _ifdtag_to_python(tags.get("Image Orientation")) or None,
        "creator": expanded_metadata.get("Creator"),
        "image_width": expanded_metadata.get("Image Width"),
        "image_height": expanded_metadata.get("Image Height"),
        "expanded_metadata": expanded_metadata,
    }
    if expanded_metadata.get("Emails"):
        data["emails"] = expanded_metadata["Emails"]
    if exiftool_error:
        data["exiftool_error"] = exiftool_error
    return data


def _extract_pdf_metadata(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Extract metadata from PDF files using PyMuPDF."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    metadata = doc.metadata or {}
    data: Dict[str, Any] = {
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
    expanded_metadata = _build_expanded_metadata(
        filename=filename,
        file_bytes=file_bytes,
        tags={},
        exiftool_data={},
        image=None,
        file_type="pdf",
    )
    data["expanded_metadata"] = expanded_metadata
    if expanded_metadata.get("Emails"):
        data["emails"] = expanded_metadata["Emails"]
    return data


def _extract_video_metadata(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Extract metadata from videos using ffprobe."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".video") as temp_file:
        temp_file.write(file_bytes)
        temp_path = temp_file.name

    try:
        command = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
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

    data: Dict[str, Any] = {
        "duration": float(format_info["duration"]) if format_info.get("duration") else None,
        "bitrate": int(format_info["bit_rate"]) if format_info.get("bit_rate") else None,
        "codec": video_stream.get("codec_name"),
        "resolution": f"{video_stream.get('width')}x{video_stream.get('height')}" if video_stream else None,
        "frame_rate": frame_rate,
        "creation_time": tags.get("creation_time"),
        "gps_latitude": gps_lat,
        "gps_longitude": gps_lon,
    }
    expanded_metadata = _build_expanded_metadata(
        filename=filename,
        file_bytes=file_bytes,
        tags={},
        exiftool_data={},
        image=None,
        file_type="video",
    )
    data["expanded_metadata"] = expanded_metadata
    if expanded_metadata.get("Emails"):
        data["emails"] = expanded_metadata["Emails"]
    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_metadata(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Extract metadata from images, PDFs, and videos."""
    file_type = _detect_file_type(filename)
    flags = {"gps_flag": False, "identity_flag": False}
    try:
        if file_type == "image":
            data = _extract_image_metadata(file_bytes, filename)
        elif file_type == "pdf":
            data = _extract_pdf_metadata(file_bytes, filename)
        elif file_type == "video":
            data = _extract_video_metadata(file_bytes, filename)
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
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "data": {},
            "file_type": file_type,
            "flags": flags,
            "error": str(exc),
        }