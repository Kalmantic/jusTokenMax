# FAQ

## Why text extraction, not image parsing, for PDFs?

Almost every spec, design doc, README, and test document an agent reads is **born
digital with a real text layer**. Text is ~10× cheaper than a rendered
page-image (which is billed by pixel area, ~1,500 tokens/page), and it's
searchable, quotable, and diffable — none of which a page-image is. So
text-first extraction is the right default.

The only case it can't serve is a **scanned / image-only** PDF (no text layer),
which yields empty Markdown — and that's exactly where **OCR** comes in (on the
roadmap). Don't want PDFs touched at all? `justokenmax config disable pdf`.

## Is anything sent over the network?

No. jusTokenMax is **zero-dependency** beyond the codecs (pypdf/Pillow), makes
**no network calls**, and runs fully offline / air-gapped. The cache is local
and **owner-only (0700)**.

## Is it safe for secrets?

Yes — built-in **redaction** masks API keys/tokens/passwords and elides base64
blobs/data-URIs inside every text digest (and in the [MCP proxy](MCP-Proxy)). It
runs before anything is written to the cache.

## Is the compression reversible?

Yes. Originals are cached by content hash; `justokenmax retrieve <artifact>`
returns the original path. Nothing is lost.

## Does it work without Python?

Yes for the MCP tools — the `npx` launcher auto-provisions Python via `uv`. See
[Installation](Installation).

## How do I see how much it consumed and saved?

`justokenmax stats` — a lifetime ledger of optimized tokens consumed, original
tokens before optimization, and tokens saved by kind.

## How do I turn features off?

`justokenmax config disable <kind>` — see [Configuration](Configuration).

## How accurate are the percentages?

Text is counted with a real tokenizer (tiktoken) in the benchmarks; the PDF
"before" uses a conservative ~1,500 tokens/page image model — so figures are
well-grounded estimates, not billed numbers. Reproduce with `python
benchmarks/benchmark.py --fetch`.
