# Brand documents, audio and video

In **Your brief → Attach brand documents, audio or video**, select a file and
choose **Save attachment to this brand**. Audio/video files remain under the
selected brand across reloads, with browser playback, original-file download and
an **Add / edit transcript or notes** editor. Saving shows an explicit status.
Repeated identical media uploads reuse the existing attachment, including when
the brand has reached its limit.

- Text: `.txt`, `.md`, up to 12,000 characters.
- Video: `.mp4`, `.mov`, `.webm`.
- Audio: `.mp3`, `.m4a`, `.wav`, `.ogg`, `.flac`, `.aac`.
- Media: at most 50 MiB per file; three attachments total per brand, including
  text documents. Media transcripts/notes are limited to 12,000 characters.

Playback depends on browser codec support. File headers are checked against the
selected container format; this does not certify that an entire clip is valid
or decodable. The original can be downloaded when browser playback is unavailable.

## How content creation uses media

**Uploads make no Mesh calls.** No automatic transcription, frame extraction or
AI analysis runs on uploaded media. If a transcript or notes are supplied, the
researcher includes a relevant excerpt as `user_media_transcript` evidence.
It retains the attachment ID, original-file SHA-256, transcript SHA-256 and
excerpt position. The source is explicitly labeled user-supplied transcript/notes,
not a claim that the AI watched or heard the file. The normal verifier still
checks claims against that text.

Files without supplied text remain available for reference/playback and show
**Transcript/notes needed for content evidence**. Research skips them with a
visible limitation and audit event, rather than inventing descriptions of the
media. Existing source snapshots remain historical when notes are edited; new
runs use the current text.

## Storage and API

Binary files live beneath the gitignored `data/brand-attachments/` directory in
brand-scoped, content-addressed folders; SQLite stores metadata and transcript
text. The file path never derives from an uploaded directory name. Uploads are
streamed with a server-side size limit and signature checks. Interrupted or
rejected uploads clean up their temporary files. File and transcript routes check
the requested brand, and playback supports HTTP byte ranges.

- `POST /brands/{brand_id}/research-media?filename=clip.mp4`: raw file bytes.
- `GET /brands/{brand_id}/research-media/{document_id}/file`: playback/download.
- `GET /brands/{brand_id}/research-media/{document_id}/transcript`: supplied text.
- `PUT /brands/{brand_id}/research-media/{document_id}/transcript`: JSON `{"text":"..."}`.

## Validation

On 20 October 2026, **29/29 focused tests passed**, including seven media tests
covering real WAV-byte preservation, MP4 container metadata, duplicate uploads,
brand isolation, oversize/interrupted/mismatched-file rejection, shared quota,
transcript provenance and actual in-process ASGI upload/playback/range/notes
requests. The MP4 fixture tests container acceptance only; browser decoding of
real videos was not validated. Mesh and social APIs were not called. Spend: **$0**.

```powershell
python -m unittest tests.test_brand_media tests.test_run_audit tests.test_grounding tests.test_verification_loop tests.test_improvement -v
```
