# jusTokenMax (core)

The Python core + `justokenmax` CLI for **jusTokenMax**, a token-reduction toolkit for
coding agents. Modules: attachment compression (PDF → Markdown, images), log
compression, and a code symbol index.

```bash
pip install pypdf Pillow      # required codecs (pdfplumber optional, better tables)
pip install -e .              # installs the `justokenmax` CLI

justokenmax optimize spec.pdf build.log    # attachments + logs
justokenmax index && justokenmax query foo      # code symbol lookup
justokenmax stats                          # lifetime savings
```

The import package is named `justokenmax` (the original attachments module);
`python -m justokenmax <args>` is equivalent to `justokenmax <args>`.

See the project root README for the full story and the Claude Code plugin.
MIT licensed — Kashi & Rajan, founders of Kalmantic (jusCode.co).
Contributors: Arbaz (https://www.linkedin.com/in/arb5z/), CTO of LineupX.
