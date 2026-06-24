---
description: Show a source file's shape (signatures + line numbers, no bodies) instead of reading the whole file.
argument-hint: <path> [more paths...]
---

Get a file's structure cheaply before deciding what to read.

Run: `justokenmax outline $ARGUMENTS` (fallback `python3 -m justokenmax outline
$ARGUMENTS`). Each line is `line  signature  — docstring` for every
function/class/method, with no bodies — typically 10-20x cheaper than reading
the file. Then read only the line range of the symbol you actually need.

For "where is symbol X across the repo?", use `/justokenmax:query` instead.
