# FAL.AI Catalog Verification (PR 0)

This document records the verified live schema for every FAL endpoint that ships in the
OpenSwarm `fal:` catalog. Per the implementation plan, **no catalog row ships in production
code without a verified entry here**; partial or guessed entries are dropped instead.

Sources, in order of trust:
1. FAL queue OpenAPI: `https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<endpoint>`
2. FAL model page (`https://fal.ai/models/<endpoint>` + `/api`)
3. One smoke call with `FAL_KEY` set (record response verbatim)

Verified-on date: 2026-05-15 (OpenAPI fetch only — no smoke calls performed in PR 0; smoke
calls run as part of PR 1's opt-in `tests/integration/tools/test_fal_live_image.py`).

Tool-side aspect-ratio Literal (from
`src/agency_swarm/_templates/openswarm/image_generation_agent/tools/GenerateImages.py`):
`{"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}`

## Conventions across all five PR 1 endpoints

| Aspect | Common behavior |
|---|---|
| Architecture | Queue-based. `fal.subscribe(endpoint, arguments=...)` handles the poll loop transparently. Each endpoint also accepts `sync_mode: true` (data URI in response) — we do NOT use sync_mode; the adapter always uses the queue path. |
| Response shape | Uniform: `result["images"]` is an array; each item has a `url` field. One parser handles all five. |
| Media reference contract | FAL's standard contract: any string URL (public HTTPS or `fal.upload_file()` result) is accepted by any field that takes a URL. The OpenAPI schemas do not document this restriction; it is the universal FAL platform behavior and matches what the existing `RemoveBackground.py` / `_generate_with_seedance` paths assume today. |
| Output URL TTL | Not documented; FAL convention is "download immediately." The adapter always downloads to PIL bytes before returning to the caller, matching existing tool contracts. |
| Required input | `prompt` (string) — only required field on every endpoint. |
| Variants | `num_images` field (1-4 or 1-8) on every endpoint **except Recraft V3**. For Recraft, the adapter fan-outs via `run_parallel_variants_sync` (one call per variant), matching how the Gemini path already handles variants. |

## Per-endpoint detail

### `fal:flux-schnell` → `fal-ai/flux/schnell`

- **Endpoint ID**: `fal-ai/flux/schnell`
- **Family**: `flux` (uses `image_size` preset, not `aspect_ratio`)
- **Cost tier**: `budget`
- **Required**: `prompt` (string)
- **AR field**: `image_size` (string preset). Enum: `square_hd`, `square`, `portrait_4_3`, `portrait_16_9`, `landscape_4_3`, `landscape_16_9`
- **Variant field**: `num_images` (1-4, default 1)
- **Other relevant fields**: `num_inference_steps` (1-12, default 4), `guidance_scale` (1-20, default 3.5), `output_format` (default `"jpeg"`), `enable_safety_checker` (default `true`), `seed` (optional)
- **Response**: `result["images"][i].url` (+ `width`, `height`, `content_type`); also `seed`, `prompt`, `timings`, `has_nsfw_concepts`.
- **Adapter AR mapping (tool → FAL)**:
  - `"1:1"` → `image_size="square_hd"`
  - `"4:3"` → `image_size="landscape_4_3"`
  - `"3:4"` → `image_size="portrait_4_3"`
  - `"16:9"` → `image_size="landscape_16_9"`
  - `"9:16"` → `image_size="portrait_16_9"`
  - **Unsupported by this endpoint**: `"2:3"`, `"3:2"`, `"4:5"`, `"5:4"`, `"21:9"` — the adapter's `validate_fal_aspect_ratio` rejects these for Flux Schnell with the sorted supported list.
- **supported_aspect_ratios** (in adapter): `frozenset({"1:1", "4:3", "3:4", "16:9", "9:16"})`

### `fal:flux-1.1-pro-ultra` → `fal-ai/flux-pro/v1.1-ultra`

- **Endpoint ID**: `fal-ai/flux-pro/v1.1-ultra`
- **Family**: `flux_ultra` (uses `aspect_ratio` ratio strings, not `image_size` preset — distinct from Flux Schnell)
- **Cost tier**: `premium` (premium-tier guard caps `num_variants` at 1)
- **Required**: `prompt` (string)
- **AR field**: `aspect_ratio` (string). Enum: `"21:9"`, `"16:9"`, `"4:3"`, `"3:2"`, `"1:1"`, `"2:3"`, `"3:4"`, `"9:16"`, `"9:21"`
- **Variant field**: `num_images` (1-4, default 1) — adapter forces 1 via premium guard
- **Other relevant fields**: `output_format` (`"jpeg"` or `"png"`, default `"jpeg"`), `safety_tolerance` (`"1"`-`"6"`, default `"2"`), `enhance_prompt` (default `false`), `raw` (default `false`), `image_url` (optional style ref), `image_prompt_strength` (0-1, default 0.1), `seed` (optional).
- **Response**: `result["images"][i].url` (+ `width`, `height`, `content_type`); also `seed`, `prompt`, `has_nsfw_concepts`, `timings`.
- **Adapter AR mapping (tool → FAL)**: passthrough (`"1:1"` → `aspect_ratio="1:1"`, etc.).
  - **Unsupported by this endpoint**: `"4:5"`, `"5:4"` — adapter rejects these for Flux Pro Ultra. (The endpoint accepts `"9:21"` but the tool's Literal doesn't have it; that's a one-way edge case the tool literal doesn't expose.)
- **supported_aspect_ratios** (in adapter): `frozenset({"1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"})`

### `fal:ideogram-v3` → `fal-ai/ideogram/v3`

- **Endpoint ID**: `fal-ai/ideogram/v3`
- **Family**: `ideogram` (uses `image_size` preset like Flux Schnell)
- **Cost tier**: `standard`
- **Required**: `prompt` (string)
- **AR field**: `image_size` (string preset). Enum: `square_hd`, `square`, `portrait_4_3`, `portrait_16_9`, `landscape_4_3`, `landscape_16_9`. Also accepts a custom `{width, height}` object — not used by the adapter.
- **Variant field**: `num_images` (1-8, default 1) — adapter caps at the tool's `num_variants` Literal max (4).
- **Other relevant fields**: `rendering_speed` (`"TURBO" | "BALANCED" | "QUALITY"`, default `"BALANCED"`), `expand_prompt` (default `true` — Ideogram's MagicPrompt), `style` (`"AUTO" | "GENERAL" | "REALISTIC" | "DESIGN"`, default `"AUTO"`), `style_preset`, `negative_prompt`, `seed`. We pass only the necessary minimum; rendering_speed stays at the BALANCED default.
- **Response**: `result["images"][i].url` (File objects; `content_type`, `file_size`, `file_name` optional).
- **Adapter AR mapping (tool → FAL)**: same as Flux Schnell — only the 5 supported ratios.
- **supported_aspect_ratios** (in adapter): `frozenset({"1:1", "4:3", "3:4", "16:9", "9:16"})`

### `fal:recraft-v3` → `fal-ai/recraft/v3/text-to-image`

- **Endpoint ID**: `fal-ai/recraft/v3/text-to-image`
- **Family**: `recraft` (uses `image_size` preset)
- **Cost tier**: `standard`
- **Required**: `prompt` (string, 1-1000 chars)
- **AR field**: `image_size` (string preset). Enum: `square_hd`, `square`, `portrait_4_3`, `portrait_16_9`, `landscape_4_3`, `landscape_16_9`. Custom `{width, height}` up to 14142 px — not used.
- **Variant field**: **NONE** — Recraft V3 has no `num_images` field. The adapter handles variants by parallel `fal.subscribe` calls via `run_parallel_variants_sync` (matching the existing Gemini variant pattern).
- **Other relevant fields**: `style` (default `"realistic_image"`; we leave it at default unless callers wire it through — out of scope for PR 1), `colors`, `style_id`, `enable_safety_checker`.
- **Response**: `result["images"][i].url` (File objects; no `width`/`height`/`seed` in schema).
- **Adapter AR mapping (tool → FAL)**: same as Flux Schnell — only the 5 supported ratios.
- **supported_aspect_ratios** (in adapter): `frozenset({"1:1", "4:3", "3:4", "16:9", "9:16"})`

### `fal:nano-banana-2` → `fal-ai/nano-banana-2`

- **Endpoint ID**: `fal-ai/nano-banana-2`
- **Family**: `nano_banana` (uses `aspect_ratio` ratio strings + optional `resolution`)
- **Cost tier**: `standard`
- **Required**: `prompt` (string, 3-50000 chars)
- **AR field**: `aspect_ratio` (string). Enum: `"auto"`, `"21:9"`, `"16:9"`, `"3:2"`, `"4:3"`, `"5:4"`, `"1:1"`, `"4:5"`, `"3:4"`, `"2:3"`, `"9:16"`, `"4:1"`, `"1:4"`, `"8:1"`, `"1:8"`. Default `"auto"`.
- **Variant field**: `num_images` (1-4, default 1).
- **Other relevant fields**: `resolution` (`"0.5K" | "1K" | "2K" | "4K"`, default `"1K"`), `output_format` (default `"png"`), `safety_tolerance` (`"1"`-`"6"`, default `"4"`), `seed`. Adapter passes the user's `aspect_ratio` directly and leaves `resolution` at its `"1K"` default (high-res support is a follow-up).
- **Response**: `result["images"][i].url` (ImageFile objects with optional `width`, `height`, `content_type`, `file_size`, `file_name`). Also a `description` field.
- **Adapter AR mapping (tool → FAL)**: passthrough for every value in the tool's Literal.
- **supported_aspect_ratios** (in adapter): `frozenset({"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"})`

## Adapter family grouping

Based on the verified schemas, three request-building families are sufficient for PR 1:

1. **`image_size` family** (Flux Schnell, Ideogram V3, Recraft V3) — share a common AR→preset mapper and request shape.
2. **`aspect_ratio` family** (Flux Pro Ultra, Nano Banana 2) — pass the tool AR through unchanged.
3. **Special-case fan-out** for Recraft (no `num_images` field).

One response parser handles all (every endpoint returns `result["images"][i].url`).

## Out of scope for PR 1 — recorded for later

- `fal:flux-pro-kontext` (image edit) — PR 2 will add its own verification entry.
- Recraft `style`/`colors`/`style_id` parameter wiring — leave defaults for PR 1; expose if real demand surfaces.
- Custom `{width, height}` image-size objects — not exposed (the tool's AR Literal is enough for the curated catalog).
- Numeric pricing — intentionally not recorded. The adapter emits `"Estimated cost tier: <budget|standard|premium>. Check FAL dashboard for exact pricing."` only.
