from __future__ import annotations

from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
OFFICE_ZIP_EXTENSIONS = {".docx", ".xlsx"}
OLE_EXTENSIONS = {".doc", ".xls"}
OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


def safe_uploaded_basename(name: str | None) -> str:
    """Reject traversal-like and directory-style uploaded filenames."""
    raw_name = (name or "").strip()
    if not raw_name:
        return ""

    normalized = raw_name.replace("\\", "/")
    if normalized in {".", ".."}:
        raise ValidationError("اسم الملف غير آمن.")

    if (
        normalized.startswith("/")
        or normalized.startswith("./")
        or normalized.startswith("../")
        or normalized.endswith("/..")
        or "/../" in normalized
        or ".." in PurePosixPath(normalized).parts
    ):
        raise ValidationError("اسم الملف غير آمن.")

    if "/" in normalized or "\\" in raw_name:
        raise ValidationError("اسم الملف غير آمن.")

    basename = PurePosixPath(normalized).name
    if not basename or basename in {".", ".."}:
        raise ValidationError("اسم الملف غير آمن.")

    return basename


def _rewind(upload) -> None:
    try:
        upload.seek(0)
    except (AttributeError, OSError):
        pass


def validate_image_content(upload) -> None:
    """Verify that an uploaded image can be decoded safely by Pillow."""
    try:
        _rewind(upload)
        image = Image.open(upload)
        image.verify()
        if image.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValidationError("صيغة الصورة الفعلية غير مسموحة.")
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValidationError("الملف المرفوع ليس صورة صالحة.") from error
    finally:
        _rewind(upload)


def validate_business_attachment(upload) -> None:
    """Validate signatures for supported announcement attachment formats."""
    safe_name = safe_uploaded_basename(getattr(upload, "name", ""))
    extension = Path(safe_name).suffix.lower()
    _rewind(upload)
    header = upload.read(16)
    _rewind(upload)

    if extension == ".pdf" and not header.startswith(b"%PDF-"):
        raise ValidationError("محتوى ملف PDF غير صالح.")

    if extension in IMAGE_EXTENSIONS:
        validate_image_content(upload)
        return

    if extension in OFFICE_ZIP_EXTENSIONS:
        try:
            with ZipFile(upload) as archive:
                names = set(archive.namelist())
                required = "word/" if extension == ".docx" else "xl/"
                if "[Content_Types].xml" not in names or not any(
                    name.startswith(required) for name in names
                ):
                    raise ValidationError("محتوى ملف Office لا يطابق امتداده.")
        except (BadZipFile, OSError) as error:
            raise ValidationError("ملف Office تالف أو غير صالح.") from error
        finally:
            _rewind(upload)
        return

    if extension in OLE_EXTENSIONS and not header.startswith(OLE_SIGNATURE):
        raise ValidationError("محتوى ملف Office القديم غير صالح.")
