"""Explicit local human review of generated visuals, bound to caption and asset.

This is a review acknowledgement, not image recognition or an automated claim
that an illustration faithfully represents a real product. No AI or HTTP calls.
"""
import hashlib
import json
from uuid import uuid4

import storage


def signature(post):
    """The published single-image asset and caption must both stay unchanged."""
    return hashlib.sha256(json.dumps([post.get('text'), post.get('image')],
                                     ensure_ascii=False).encode()).hexdigest()


def required(post):
    visual = post.get('visual') if isinstance(post.get('visual'), dict) else {}
    return bool(post.get('image')) and (
        post.get('mode') in ('live_mesh', 'live') or
        post.get('image_origin') == 'mesh_generated' or
        post.get('image_review') == 'required' or
        visual.get('image_origin') == 'mesh_generated')


def review_id(post_id):
    return 'visual_review:' + post_id


def status(post):
    fingerprint = signature(post)
    review = storage.get(review_id(post['id']))
    needed = required(post)
    current = review is not None and review.get('fingerprint') == fingerprint
    if current:
        state = 'approved' if review.get('approved') is True else 'held'
    elif review:
        state = 'stale'
    else:
        state = 'required' if needed else 'not_required'
    messages = {
        'approved': 'Visual and caption reviewed. Changing either requires a fresh review.',
        'held': 'Visual held for correction: ' + str((review or {}).get('note', 'Review needed.')),
        'stale': 'The image or caption changed after review. Review the current version before Instagram preparation.',
        'required': 'Review the generated image and exact caption for garbled text, misleading details and brand fit before Instagram preparation.',
        'not_required': 'No generated-visual review requirement was identified for this imported or legacy asset.',
    }
    # No image or caption is copied into this response or its audit record.
    return dict(post_id=post['id'], required=needed, status=state,
                fingerprint=fingerprint, message=messages[state], review=review)


def ensure_reviewed(post):
    result = status(post)
    # An explicit hold remains effective even for a manually imported image.
    if result['status'] == 'held' or result['required'] and result['status'] != 'approved':
        raise ValueError(result['message'])
    return result


def record(post_id, fingerprint, approved, note='', confirm_review=False):
    if confirm_review is not True:
        raise ValueError('Explicitly confirm that you inspected the current image and caption.')
    if type(approved) is not bool:
        raise ValueError('The visual review decision must be approve or hold.')
    if not isinstance(note, str) or len(note) > 1000:
        raise ValueError('Visual review notes must contain at most 1000 characters.')
    note = note.strip()
    if not approved and not note:
        raise ValueError('Give a clear reason for holding the visual.')
    with storage.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT body FROM records WHERE id=? AND kind='post'", (post_id,)).fetchone()
        if not row:
            raise ValueError('post not found')
        post = json.loads(row[0])
        if not post.get('image'):
            raise ValueError('There is no saved image to review.')
        current = signature(post)
        if fingerprint != current:
            raise ValueError('The image or caption changed. Inspect the latest version and submit its current fingerprint.')
        review = dict(id=review_id(post_id), post_id=post_id, fingerprint=current,
                      approved=approved, note=note, reviewed_at=storage.now(),
                      method='explicit_local_human_acknowledgement')
        db.execute("INSERT INTO records VALUES (?, 'visual_review', ?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
                   (review['id'], json.dumps(review)))
        event = dict(id=str(uuid4()), post_id=post_id, agent='visual_reviewer',
                     at=storage.now(), detail=dict(fingerprint=current, approved=approved,
                     note=note, reason='Human acknowledged the exact saved image and caption; no automated visual correctness is claimed.'))
        db.execute("INSERT INTO records VALUES (?, 'audit', ?)", (event['id'], json.dumps(event)))
    return status(post)
