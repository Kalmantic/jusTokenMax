---
description: Compress a git diff — keep real code hunks, collapse lockfile/generated/minified file diffs to one line.
argument-hint: "[diff-file]  (or pipe: git diff | …)"
---

Shrink a large diff before reviewing it or generating a commit message.

Run `justokenmax diff $ARGUMENTS` for a file, or pipe a live diff:
`git diff | justokenmax diff -` (fallback `python3 -m justokenmax diff`). Real
code changes are kept verbatim; lockfile / generated / minified / vendored file
diffs collapse to a one-line `+adds/-dels` summary. `.diff`/`.patch` files are
also handled automatically by the Read hook.
