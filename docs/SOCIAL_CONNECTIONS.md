# Social accounts and the analytics loop

Updated 20 October 2026. Connectors are read-only. No accounts have been authorized
or converted by the development agent. No live connector validation or paid media
validation has been performed; tests use explicit HTTP/session doubles.

## Account choice and actual boundaries

| Platform | Account used | Authentication | Important restriction |
|---|---|---|---|
| Instagram | Free Creator/Business professional account | Instagram Login OAuth | Personal-account insights are not exposed by this API. App review and insights scope are required; converting account type does not grant an app permission. |
| YouTube | Normal channel-owning Google account | Google OAuth | Enable Data and Analytics APIs. No paid channel plan needed. Quotas, reporting lag and OAuth verification apply. |
| LinkedIn | Normal personal profile | LinkedIn OAuth | Requires approved `r_member_postAnalytics`. Personal post-history discovery requires restricted `r_member_social`; known published URNs can be linked. Premium does not solve permission access. |
| Telegram | Normal user administering a public channel | Local MTProto user session | Bot API cannot fetch historical post views. No Premium required. Session authorization must be completed by the human locally. |
| Threads | Normal profile | Threads OAuth | Requires `threads_basic` and `threads_manage_insights`, plus production app approval where applicable. |
| X | Normal account with a developer application | OAuth 2 PKCE | API reads are paid regardless of professional/Premium status. Both per-connection opt-in and `SOCIAL_ENABLE_PAID_X=1` are required. |

Official references: [Instagram API](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api),
[YouTube reports](https://developers.google.com/youtube/analytics/reference/reports/query),
[LinkedIn member analytics](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/members/post-statistics),
[LinkedIn access restrictions](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/community-management-overview),
[Telegram views](https://core.telegram.org/method/messages.getMessagesViews),
[Threads insights](https://www.postman.com/meta/threads/request/ndeeu6p/get-post-insights),
[X billing](https://docs.x.com/x-api/getting-started/pricing).

An Instagram professional account is not a Meta Verified subscription. No paid
account upgrades, provider purchases, or account conversion are performed here.
Review account privacy/tradeoffs in Instagram before converting your own account.

## Setup

1. Install `requirements.txt`, including cryptography and Telethon. Run
   `python scripts/setup_connections.py` to generate the encryption key in the
   gitignored `.env`. Keep a private backup: losing it makes saved OAuth tokens
   unreadable. The script preserves an existing key and never prints it.
2. Register your provider developer apps. Copy relevant `*_CLIENT_ID`,
   `*_CLIENT_SECRET`, and callback fields from `.env.example` to `.env`. Use the
   exact redirect URI registered with the provider. A provider can require a
   registered HTTPS callback even though local loopback is accepted by this app.
   Set `CREATOROS_HTTPS=1` when serving through HTTPS so the OAuth cookie is Secure.
   The application remains a local single-user tool: do not expose it publicly
   without application authentication and deployment hardening.
3. In **Accounts & analytics**, select a brand, create a connection, and follow
   **Authorize**. The app uses state, a browser-bound HttpOnly SameSite cookie,
   single-use state records, and PKCE where supported. OAuth tokens are encrypted
   with Fernet in SQLite; credentials are never returned by the status API.
   Scopes request reading/analytics, not public posting or account changes.
4. For Telegram, configure `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and run
   `python scripts/connect_telegram.py` yourself in a terminal. Enter your login
   information there, never in chat. Session files are credentials and gitignored.
   Use your channel's `@handle` in the connection setup.
5. Discover recent posts (at most ten; five on X), or link an existing post using
   its exact platform ID, actual publication time, text/title, and format.
   Linking content does not invent engagement. LinkedIn personal users must link
   known share/ugcPost URNs unless they separately hold restricted discovery access.
6. Enable collection. Discovery runs at most daily and metric collection rotates
   through three oldest/unobserved linked posts per connection per day. This is
   intentionally bounded, not real-time. The UI displays status, next eligible
   collection, and errors. A 401/403/429 preserves existing observations rather
   than replacing them with zeros or immediately retrying.

Environment access tokens are supported for local bring-your-own-token setup.
They are not copied into SQLite. Disconnect pauses collection and removes stored
OAuth tokens; it does not revoke permissions at the provider or erase an `.env`
token. Revoke the app in the provider settings for full remote revocation.

## What is captured

- Instagram: views/reach, likes/comments, saves/shares when the media API exposes
  them. Unsupported media metrics can reject a request; the connector surfaces
  that failure rather than inventing data. API version is configurable.
- YouTube: a rolling 28-day Analytics report (ending yesterday), including views,
  likes, comments, shares, watch minutes, and average view duration. Channel
  ownership is checked when a channel ID is configured. Provider reporting lag
  means the requested range is not a real-time completeness guarantee.
- LinkedIn: lifetime impressions, reactions, comments, reshares, using the member
  analytics endpoint. Reactions are labeled reactions, not silently renamed likes.
- Telegram: message views and forwards; reactions when available. View collection
  explicitly uses `increment=False` and never increases the view counter.
- Threads: views, likes, replies, reposts, quotes, shares when supplied.
- X: public post counters returned by the API, including impressions when present.
  Private metrics, demographics, and historical guarantees are not fabricated.

Missing counters stay absent. Rates sum the available interaction counters and
divide by one explicitly named denominator (impressions, views, or reach). These
are event ratios, not unique people; multiple events can come from the same user.
Different numerator sets produce different formula IDs and are not pooled.

## How it changes the next post

1. The collector writes a snapshot with provider/source, account, publication and
   collection timestamps, native counts, reporting window, age bucket and formula.
2. The dashboard compares only matching platform/account/source/window/age/formula
   cohorts. It requires two posts per format in at least two formats before
   proposing a preference. This minimum is exploratory, not statistical proof.
3. A deterministic learner saves a tentative rule and the exact evidence IDs.
   It makes no LLM call. Repeated identical observations do not multiply learning.
4. The next matching generation retrieves that rule. A unique matching account is
   inferred; if several accounts share a brand/platform, pass `connection_id` in
   the generation request to use account-specific rules. Otherwise those API
   rules are withheld. API-derived rules expire from generation after 14 days
   without an update. The strategist records only valid applied evidence IDs.
5. Writer/editor quality checks still run. New performance must be measured again;
   a changed draft or editor score does not demonstrate engagement uplift.

**Show fictional examples** loads four observations for each of six platforms in
an isolated temporary database. Example source labels and a suggested next-brief
experiment are visible. No examples are injected into real brands or live prompts.

YouTube imported metadata is refreshed on discovery. Stale imported titles/text
and API observations older than 30 days are cleared/removed when not refreshed,
and unsupported derived learning is removed. Other providers' retention rules
must also be reviewed before public deployment. Exports contain no access tokens;
CSV formula injection is neutralized.

## What this does not claim

No live account is connected just because code or credentials exist. `verified`
means an actual collection succeeded. No connector publishes posts, bypasses
provider review/fees, retrieves unavailable personal-account insights, or promises
unlimited history. Public SaaS tenancy, billing and deployment remain separate work.
