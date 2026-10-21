# Instagram connection and single-photo publishing

Implementation supports an explicit **single-image post with caption**. Carousel
and Reel publishing are not implemented by this flow. No live Instagram account
has been authorized or published to during development. Tests mock Meta responses.
The existing saved post and image can be reused with zero Mesh generation calls.

## Prerequisites

1. An Instagram Creator or Business account. The current official API does not
   expose this publishing flow for a consumer/personal account. Account conversion
   is the user's decision; CreatorOS does not change account type.
2. A Meta developer app configured for Instagram Login. Set `INSTAGRAM_CLIENT_ID`,
   `INSTAGRAM_CLIENT_SECRET` and an exact registered `INSTAGRAM_REDIRECT_URI` in the
   local gitignored `.env`; never send credentials through chat. Provider app roles,
   test-user requirements and advanced access/app review apply as appropriate.
3. Set `INSTAGRAM_ENABLE_PUBLISHING=1` locally and restart before authorizing. This
   explicitly adds `instagram_business_content_publish` to the existing basic and
   insights scopes. Existing analytics-only authorization must be repeated to
   obtain publishing consent. An opt-in flag alone does not grant Meta permission.
4. Host the reviewed JPEG at a publicly accessible HTTPS URL that Meta can fetch.
   CreatorOS provides a local JPEG export but does **not** upload it to another
   service, create a tunnel or expose the local server. The customer supplies the
   hosting destination. A localhost link or data URI is insufficient. The URL
   must stay available through ingestion. Do not host secrets or unrelated files.

## Review and publish

In **Accounts & analytics**, create the Instagram connection for the selected
brand and authorize it. In the approved Instagram post's **Final post**, open
**Publish a single image to Instagram**:

- Download the 1080-square JPEG and place it on the chosen public media host.
- Inspect the exact generated image and caption, then record the explicit visual
  review acknowledgement. Changing either makes that review stale. This is a
  human review gate, not an automated guarantee of visual correctness. Confirm
  that the separately hosted JPEG is the same reviewed asset.
- Select the matching Instagram connection, supply the JPEG URL and prepare the
  delivery. This step is local, stores the exact caption/image fingerprint, and
  makes no provider requests.
- Verify the account and create a container. This reads the authorized username
  and sends the caption/image URL to Meta. It does not call `media_publish` yet.
- Check readiness (manual, at most once per minute and five checks per delivery).
  Only a `FINISHED` container becomes ready for the final publication action.
- Review the exact account, caption and image URL. Type the verified username,
  check the confirmation box and press the explicit publish button.

Successful publication saves the real media ID/time, marks the post and handoff
job published, and links it to the existing analytics collector. Analytics
collection is independently paused until enabled; publishing does not enable it.

## Duplicate protection and failure boundaries

One persistent delivery is reserved per post/account connection. SQLite atomic
state transitions block simultaneous stage/publish requests. No HTTP mutation
is automatically retried. A timeout leaves `container_creation_unknown` or
`publication_unknown`; inspect Instagram before any manual reconciliation. A
restart during a request leaves an in-flight state blocked rather than blindly
resubmitting. The provider can have accepted a request whose response was lost.

Re-confirming a completed delivery returns its saved receipt without publishing
again. A changed caption/image or approval state blocks the existing delivery.
Meta permissions, quotas, expired containers, URL accessibility, image acceptance
and real-account behavior remain live validation requirements. Publishing is
disabled by default and has no background auto-publish scheduler.

Source: [Meta's Instagram API collection](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api)
and [Instagram Login content publishing](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing/).
