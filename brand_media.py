"""Bounded local brand-media uploads. No transcription, model or network calls."""
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4
import storage

MEDIA_ROOT = Path(__file__).resolve().parent / "data" / "brand-attachments"
MAX_MEDIA_BYTES = 50 * 1024 * 1024
FORMATS = {".mp4":("video","video/mp4"), ".mov":("video","video/quicktime"),
    ".webm":("video","video/webm"), ".mp3":("audio","audio/mpeg"),
    ".m4a":("audio","audio/mp4"), ".wav":("audio","audio/wav"),
    ".ogg":("audio","audio/ogg"), ".flac":("audio","audio/flac"), ".aac":("audio","audio/aac")}


class UploadError(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def _signature(extension, data):
    if extension in (".mp4", ".mov", ".m4a"):
        return len(data) >= 12 and data[4:8] == b"ftyp"
    if extension == ".webm": return data.startswith(b"\x1a\x45\xdf\xa3")
    if extension == ".wav": return data.startswith(b"RIFF") and data[8:12] == b"WAVE"
    if extension == ".ogg": return data.startswith(b"OggS")
    if extension == ".flac": return data.startswith(b"fLaC")
    if extension in (".mp3", ".aac"):
        return (extension == ".mp3" and data.startswith(b"ID3")) or (len(data) >= 2 and data[0] == 255 and data[1] & 224 == 224)
    return False


def _folder(brand_id):
    return MEDIA_ROOT / hashlib.sha256(brand_id.encode()).hexdigest()


async def save_media(brand_id, filename, chunks):
    from research import MAX_DOCUMENTS
    brand = storage.get(brand_id)
    if not brand or brand.get("kind") != "brand": raise UploadError("Brand not found", 404)
    name = filename.strip()
    if not name or len(name)>120 or any(c in name for c in '/\\:\x00') or any(ord(c)<32 for c in name):
        raise UploadError("Use a filename without directory paths or control characters")
    extension = Path(name).suffix.lower()
    if extension not in FORMATS: raise UploadError("Supported media: MP4, MOV, WEBM, MP3, M4A, WAV, OGG, FLAC or AAC")
    folder = _folder(brand_id)
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / (str(uuid4()) + ".part")
    created_path = None
    try:
        size = 0; digest = hashlib.sha256(); header = bytearray()
        with temporary.open("wb") as stream:
            async for chunk in chunks:
                size += len(chunk)
                if size > MAX_MEDIA_BYTES: raise UploadError("Media exceeds the 50 MiB upload limit", 413)
                if len(header)<32: header.extend(chunk[:32-len(header)])
                digest.update(chunk); stream.write(chunk)
        if not size or not _signature(extension, bytes(header)):
            raise UploadError("The file header does not match its supported media format")
        sha = digest.hexdigest()
        with storage.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = [json.loads(row[0]) for row in db.execute("SELECT body FROM records WHERE kind='research_document'")]
            existing = [d for d in existing if d.get("brand_id") == brand_id]
            prior = next((d for d in existing if d.get("media_type") and d.get("sha256") == sha), None)
            if prior: return prior, False
            if len(existing)>=MAX_DOCUMENTS: raise UploadError("This brand already has three attachments (documents, audio or video)")
            target = folder / (sha + extension)
            if not target.exists():
                temporary.replace(target); created_path = target
            kind, mime = FORMATS[extension]
            doc = dict(id=str(uuid4()),brand_id=brand_id,filename=name,sha256=sha,file_sha256=sha,
                extension=extension,media_type=kind,mime_type=mime,size_bytes=size,text="",
                evidence_status="transcript_needed",source_type="user_media_transcript",created_at=storage.now())
            db.execute("INSERT INTO records VALUES (?, 'research_document', ?)", (doc["id"], json.dumps(doc)))
        return doc, True
    except BaseException:
        if created_path: created_path.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)


def get_media(brand_id, document_id):
    doc = storage.get(document_id)
    if not doc or doc.get("brand_id") != brand_id or doc.get("media_type") not in ("audio","video"):
        raise UploadError("Brand media attachment not found", 404)
    return doc


def media_path(doc):
    if not re.fullmatch(r"[a-f0-9]{64}", doc.get("sha256","")) or doc.get("extension") not in FORMATS:
        raise UploadError("Invalid saved media reference", 404)
    path = _folder(doc["brand_id"]) / (doc["sha256"] + doc["extension"])
    if not path.is_file(): raise UploadError("The saved media file is unavailable", 404)
    return path


def save_transcript(brand_id, document_id, text):
    doc = get_media(brand_id, document_id)
    text = text.replace("\x00", "").strip()
    if len(text)>12000: raise UploadError("Transcript/notes must not exceed 12,000 characters")
    return storage.save("research_document", dict(doc,text=text,transcript_origin="user_supplied",
        transcript_sha256=hashlib.sha256(text.encode()).hexdigest(),transcript_updated_at=storage.now(),
        evidence_status="supplied_transcript" if text else "transcript_needed"),document_id)
