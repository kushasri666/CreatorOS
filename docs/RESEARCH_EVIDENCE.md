# Evidence used for product content

CreatorOS focuses each run on the brand's named product or service. A live generation can draw on three evidence sources: documents the brand uploaded, product facts and official product URL supplied in the brief, and real engagement observations collected from the connected social account for the selected platform.

## Connected social accounts

When account collection is authorized and enabled, the background collector uses the platform's official API to discover supported published posts and collect the available metrics. Existing platform restrictions still apply: for example, personal LinkedIn history discovery may require restricted access, so known post IDs must be linked manually; X reads remain behind the explicit paid-read setting. The app does not scrape logged-in web pages.

Only observations recorded with `source=api` from the single enabled connection selected for the brand and platform are passed as real account-performance evidence to the content agents. If there are multiple enabled accounts and no account is selected, CreatorOS withholds account metrics rather than mixing audiences. Each source record is linked to the generated post and includes provider, post ID, format, available metric counts, reporting window, collection time, external media ID, and the database ID of the originating observation. This lets the strategist see which formats or hooks have performed for that account. Small or incomparable samples are treated as directional; the learner does not claim causation. Simulated and manually entered numbers stay labeled separately and do not enter the live account-evidence context.

Metrics are collected only for content the authorized provider API exposes or for posts explicitly linked by the user. Availability, reporting delay, privacy rules, scopes, quotas, and account type differ by provider. If there are no API observations, the run records that limitation and does not invent account insights. Enabling collection may make provider API calls, but it adds no separate Mesh call.

## Uploaded brand documents and product details

A brand can store up to three `.txt` or `.md` files, each up to 12,000 characters. They are included automatically in every live generation for that brand; users do not have to select them each time. The app saves the full text locally in SQLite and sends a topic-relevant excerpt of up to 1,100 characters per file as untrusted evidence to the existing Mesh-backed strategist, writer, and editor. It never treats document content as instructions. The UI exposes filename/hash metadata rather than the full stored text. Offline scripted previews do not send uploaded text to a model.

Users can supply a product or service name, official product page, and approved facts on a brand or brief. If an official URL is provided and evidence retrieval is enabled, CreatorOS fetches only that HTTPS page and a small number of same-site product-related pages. It does not run generic topic searches. Fetched content is bounded, source-linked, and stored with the post. If details are missing, prompts direct agents to keep claims conservative rather than filling gaps with general-topic content.

## Source trace and Mesh cost

Every retrieved source is stored with a post-specific `S1`, `S2`, … identifier and retrieval timestamp. Strategist decisions and writer citations may refer only to these IDs; unsupported IDs are discarded. The final post shows source excerpts, metric provenance, and claim/source mappings. Audit events explain what evidence was available. Source existence does not prove a claim; users should verify factual claims before publishing.

Retrieval and deterministic metric selection do not use Mesh. Existing strategist, writer, and editor calls remain routed through Mesh and interpret the evidence in context, within the existing per-run call cap. No separate paid research model is added.
