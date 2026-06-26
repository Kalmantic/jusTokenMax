# jusTokenMax benchmark results

_Token counts: Markdown side via `tiktoken/cl100k`; PDF 'before' via Anthropic page-image model (~1500 tok/page)._


## PDF -> Markdown

| file | pages | tokens before | tokens after | reduction |
| --- | ---: | ---: | ---: | ---: |
| 1706.03762.pdf | 15 | 37,074 | 14,574 | **-60%** |
| fw9.pdf | 6 | 18,305 | 9,305 | **-49%** |
| **total** | | **55,379** | **23,879** | **-56%** |

## Image compression

| file | orig px | new px | bytes before | bytes after | bytes saved | base64 tokens before→after |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| sample-screenshot.png | 3000x2000 | 1568x1045 | 186,295 | 106,802 | **-42%** | 62,098 → 35,600 |

_Image note: native-vision models downscale to <=1568px anyway, so the byte savings translate to token savings only in pipelines that inline images as base64._


## Log compression

| file | lines before | lines after | tokens before | tokens after | reduction |
| --- | ---: | ---: | ---: | ---: | ---: |
| sample-build.log | 4,345 | 21 | 107,668 | 396 | **-99%** |

## JSON / structured-output compression

| file | tokens before | tokens after | reduction |
| --- | ---: | ---: | ---: |
| sample-response.json | 168,023 | 374 | **-99%** |

## Notebook / CSV / delta

| input | tokens before | tokens after | reduction |
| --- | ---: | ---: | ---: |
| notebook (20 cells, image outputs) | 401,170 | 610 | **-99%** |
| CSV (5,000 rows) | 57,340 | 237 | **-99%** |
| XLSX (5,000 rows) | 66,678 | 778 | **-98%** |
| delta re-read (1 edit in 600 lines) | 2,407 | 88 | **-96%** |

## Code index (read symbols, not files)

Indexed **263 symbols** across **34 files**. Cost to locate a symbol, summed over 34 lookups:

| approach | tokens |
| --- | ---: |
| read each whole file | 29,945 |
| one `justokenmax query` hit each | 854 |
| **reduction** | **-97%** |
