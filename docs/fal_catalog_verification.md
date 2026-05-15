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

## PR 2 — image-to-image (edit) entry

### `fal:flux-pro-kontext` → `fal-ai/flux-pro/kontext`

Verified-on date: 2026-05-15 (OpenAPI fetch).

- **Endpoint ID**: `fal-ai/flux-pro/kontext`
- **Modality**: I2I (instruction-driven edit of an input image)
- **Family**: `flux_kontext`
- **Cost tier**: `premium` (Flux Pro family — same tier as `fal:flux-1.1-pro-ultra`; the adapter rejects `num_variants > 1`)
- **Required**: `prompt` (string) AND `image_url` (string, min length 1) — the edit instruction plus the image to edit.
- **AR field**: `aspect_ratio` (string, nullable). Enum: `"21:9"`, `"16:9"`, `"4:3"`, `"3:2"`, `"1:1"`, `"2:3"`, `"3:4"`, `"9:16"`, `"9:21"`. Default: null (the model preserves the input's aspect ratio when unset).
- **Variant field**: `num_images` (1-4, default 1). Adapter caps at 1 via premium guard.
- **Other relevant fields**: `output_format` (`"jpeg"` or `"png"`, default `"jpeg"`), `safety_tolerance` (`"1"`-`"6"`, default `"2"`), `enhance_prompt` (default `false`), `guidance_scale` (1-20, default 3.5), `seed`. The adapter sends only `prompt`, `image_url`, `aspect_ratio`, and `num_images`; other params keep their FAL-side defaults.
- **Response**: `result["images"][i].url` (each entry also has optional `width`, `height`, `content_type`, `file_size`, `file_name`). Also `seed`, `prompt` (echoed), `has_nsfw_concepts`, `timings`.
- **Architecture**: Queue-based with `sync_mode` available. The adapter always uses the queue path via `fal.subscribe`, never `sync_mode`, matching every other endpoint in the catalog.
- **Media reference contract for `image_url`**: Not explicitly documented in the schema beyond `string, minLength: 1`. The FAL platform convention — confirmed by the existing Pixelcut and Seedance I2V paths in this codebase — accepts any string URL: public HTTPS or `fal.upload_file()` result. The adapter resolves user input (URL passthrough, absolute local path → `fal.upload_file`, generated-image-name lookup) into a single URL before calling `fal.subscribe`.
- **Output URL TTL/expiry**: Not specified. Adapter downloads immediately (matches every other endpoint).
- **Adapter AR mapping (tool → FAL)**: passthrough where supported. The tool's Literal includes `"4:5"` and `"5:4"`, which Flux Kontext does NOT accept — the adapter rejects those values for this spec.
- **supported_aspect_ratios** (in adapter): `frozenset({"1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"})` (same set as Flux Pro Ultra).

### PR 2 catalog placement

PR 2 introduces `FAL_I2I_CATALOG` as a separate dict keyed on the same `fal:` namespace as `FAL_T2I_CATALOG`, with disjoint keys. `is_fal_model` becomes an umbrella check across both; tool-specific dispatch uses `is_fal_t2i_model` / `is_fal_i2i_model` to route to the correct invocation helper. `GenerateImages.model` Literal stays unchanged (Flux Kontext is structurally rejected by Pydantic). `EditImages.model` Literal gains `fal:flux-pro-kontext`.

## Out of scope for this round — recorded for later

- Recraft `style`/`colors`/`style_id` parameter wiring — leave defaults; expose if real demand surfaces.
- Custom `{width, height}` image-size objects — not exposed (the tool's AR Literal is enough for the curated catalog).
- Multi-image FAL compositing (analogue to Gemini multi-image input) — no curated candidate yet.
- Flux Kontext `enhance_prompt` / `guidance_scale` / `seed` — keeping FAL defaults; expose if needed.
- Numeric pricing — intentionally not recorded. The adapter emits `"Estimated cost tier: <budget|standard|premium>. Check FAL dashboard for exact pricing."` only.

## PR 3 — video catalog

Verified-on date: 2026-05-15 (OpenAPI fetch + model page fetch; no smoke calls).

### Conventions across all PR 3 video endpoints

| Aspect | Common behavior |
|---|---|
| Architecture | Queue-based. `fal.subscribe(endpoint, arguments=...)` is appropriate for all endpoints. No sync_mode used. |
| Response shape | All endpoints return `result["video"]["url"]` (a single File object, not an array). This is structurally different from the image side (`result["images"][i].url`). One video parser handles all seven backing slugs. |
| Variant field | None of the verified video endpoints expose a `num_videos` or equivalent field. Each call produces exactly one video. Variants require parallel calls if needed. |
| Output URL TTL | Not documented; FAL convention is "download immediately." Adapter should download before returning. |
| Media reference contract | FAL platform convention applies: any string URL (public HTTPS or `fal.upload_file()` result) is accepted by image input fields. Not explicitly documented in schemas beyond `string` type. |
| Sync vs queue | `fal.subscribe(...)` confirmed appropriate for all endpoints (all use `https://queue.fal.run` base). |

---

### `fal:kling-v3-pro-t2v` → `fal-ai/kling-video/v3/pro/text-to-video`

- **Endpoint ID**: `fal-ai/kling-video/v3/pro/text-to-video`
- **Modality**: T2V
- **Family**: `kling_pro` (shares duration enum and AR set with the I2V variant)
- **Cost tier**: `premium`
- **Required**: `prompt` (string, max 2500 chars) OR `multi_prompt` (array) — exactly one must be provided; prompt is the normal path.
- **Duration enum**: `"3"`, `"4"`, `"5"`, `"6"`, `"7"`, `"8"`, `"9"`, `"10"`, `"11"`, `"12"`, `"13"`, `"14"`, `"15"` (seconds as strings). Default `"5"`. Finest-grained duration control in the catalog.
- **Resolution / size enum**: None — no resolution field. Output resolution is model-determined.
- **Aspect ratio enum**: `"16:9"`, `"9:16"`, `"1:1"`. Default `"16:9"`. Three values only (narrower than most video peers).
- **`audio_url` input field**: Not present.
- **First-frame ref field (I2V)**: N/A — T2V only.
- **Last-frame / end-frame ref**: Not present on this endpoint.
- **Variant field**: None (`num_videos` absent; one video per call).
- **Response shape**: `result["video"]["url"]` — a single File object with `url` (string), `content_type` (`"video/mp4"`), `file_name` (string), `file_size` (integer bytes).
- **Sync vs queue**: Queue (`fal.subscribe`). No sync_mode noted.
- **Output URL TTL**: Not documented; download immediately.
- **Media reference contract**: N/A (T2V; no image inputs).
- **Other relevant fields**: `generate_audio` (boolean, default `true` — native audio generation, supports Chinese and English), `negative_prompt` (string, default `"blur, distort, and low quality"`), `cfg_scale` (float 0–1, default `0.5`), `shot_type` (`"customize"` | `"intelligent"`, default `"customize"`).

---

### `fal:kling-v3-pro-i2v` → `fal-ai/kling-video/v3/pro/image-to-video`

- **Endpoint ID**: `fal-ai/kling-video/v3/pro/image-to-video`
- **Modality**: I2V
- **Family**: `kling_pro`
- **Cost tier**: `premium`
- **Required**: `start_image_url` (string) — the primary first-frame image. Constraints: max 10 MB, min 300 px on shortest side, max 2.5:1 aspect ratio. Note: the field name is `start_image_url`, NOT `image_url` or `first_frame_image_url`.
- **Optional prompt**: `prompt` (string, max 2500 chars) OR `multi_prompt` (array) — prompt is optional here (image drives generation).
- **Duration enum**: `"3"` through `"15"` (same discrete per-second strings as T2V variant). Default `"5"`.
- **Resolution / size enum**: None.
- **Aspect ratio enum**: **Not present** — the I2V endpoint does not accept `aspect_ratio`; output aspect ratio is derived from `start_image_url` dimensions.
- **`audio_url` input field**: Not present.
- **First-frame ref field**: `start_image_url` (string, required). Image constraints: max 10 MB, min 300 px, max 2.5:1 AR.
- **Last-frame / end-frame ref**: `end_image_url` (string, optional) — Kling Pro I2V explicitly supports a concluding frame image. This is a differentiator from most peers.
- **Variant field**: None.
- **Response shape**: `result["video"]["url"]` (same File object as T2V).
- **Sync vs queue**: Queue (`fal.subscribe`).
- **Output URL TTL**: Not documented; download immediately.
- **Media reference contract**: `start_image_url` and `end_image_url` accept any string URL per FAL platform convention.
- **Other relevant fields**: `generate_audio` (boolean, default `true`), `negative_prompt` (string), `cfg_scale` (float 0–2, default `0.5`), `shot_type` (`"customize"` | `"intelligent"`), `elements` (array — character/object reference images for consistency).

---

### `fal:hailuo-02-standard-t2v` → `fal-ai/minimax/hailuo-02/standard/text-to-video`

- **Endpoint ID**: `fal-ai/minimax/hailuo-02/standard/text-to-video`
- **Modality**: T2V
- **Family**: `hailuo` (shares response shape with Pro I2V variant)
- **Cost tier**: `budget`
- **Required**: `prompt` (string, 1–2000 chars).
- **Duration enum**: `"6"`, `"10"` (seconds as strings). Default `"6"`. Only two options — simplest duration surface in the catalog.
- **Resolution / size enum**: Fixed at `768p` (not user-configurable; no resolution field in schema).
- **Aspect ratio enum**: Not present — no aspect_ratio field in schema. Output aspect ratio is model-determined.
- **`audio_url` input field**: Not present.
- **First-frame ref field**: N/A — T2V only.
- **Last-frame / end-frame ref**: Not present.
- **Variant field**: None.
- **Response shape**: `result["video"]["url"]` (File object with optional `file_name`, `content_type`, `file_size`).
- **Sync vs queue**: Queue (`fal.subscribe`).
- **Output URL TTL**: Not documented; download immediately.
- **Media reference contract**: N/A (T2V).
- **Other relevant fields**: `prompt_optimizer` (boolean, default `true` — MiniMax's automatic prompt enhancement).

---

### `fal:hailuo-02-pro-i2v` → `fal-ai/minimax/hailuo-02/pro/image-to-video`

- **Endpoint ID**: `fal-ai/minimax/hailuo-02/pro/image-to-video`
- **Modality**: I2V
- **Family**: `hailuo`
- **Cost tier**: `premium` (1080p output, Pro tier — comparable positioning to Kling Pro)
- **Required**: `prompt` (string, max 2000 chars) AND `image_url` (string) — both required.
- **Duration enum**: Not present — no duration field in schema. Video length is model-determined.
- **Resolution / size enum**: Fixed at `1080p` (not user-configurable; no resolution field).
- **Aspect ratio enum**: Not present — no aspect_ratio field. Output AR is derived from `image_url` dimensions.
- **`audio_url` input field**: Not present.
- **First-frame ref field**: `image_url` (string, required). Standard field name (matches FAL image convention, unlike Kling's `start_image_url`).
- **Last-frame / end-frame ref**: `end_image_url` (string, optional) — endpoint supports a concluding frame image.
- **Variant field**: None.
- **Response shape**: `result["video"]["url"]` (File object).
- **Sync vs queue**: Queue (`fal.subscribe`).
- **Output URL TTL**: Not documented; download immediately.
- **Media reference contract**: `image_url` and `end_image_url` accept any string URL per FAL platform convention.
- **Other relevant fields**: `prompt_optimizer` (boolean, default `true`).

---

### `fal:luma-ray-2-t2v` → `fal-ai/luma-dream-machine/ray-2`

**Slug note**: The plan candidate `fal-ai/luma-dream-machine/ray-2` is the correct canonical slug. The variant `fal-ai/luma-dream-machine/ray-2/text-to-video` returns HTTP 404 and does not exist. The bare slug is a unified T2V+I2V endpoint (image inputs are optional).

- **Endpoint ID**: `fal-ai/luma-dream-machine/ray-2`
- **Modality**: T2V (primary) — also accepts optional `image_url` / `end_image_url` for image-anchored generation; this adapter key covers the T2V use case.
- **Family**: `luma_ray2` (unified slug; distinct from Kling/Seedance which have separate T2V and I2V slugs)
- **Cost tier**: `standard`
- **Required**: `prompt` (string, 3–5000 chars).
- **Duration enum**: `"5s"`, `"9s"`. Default `"5s"`. Note: values include the `s` suffix (unlike all other video endpoints in this catalog which use bare integers or bare integer strings).
- **Resolution / size enum**: `"540p"` (default), `"720p"`, `"1080p"`. Resolution is user-selectable with tiered cost (720p costs 2x, 1080p costs 4x relative to 540p).
- **Aspect ratio enum**: `"16:9"` (default), `"9:16"`, `"4:3"`, `"3:4"`, `"21:9"`, `"9:21"`. Six values.
- **`audio_url` input field**: Not present.
- **First-frame ref field**: `image_url` (string, optional) — "Initial image to start the video from." Present on the same endpoint as T2V; the adapter for `fal:luma-ray-2-t2v` omits it.
- **Last-frame / end-frame ref**: `end_image_url` (string, optional) — "Image to blend video conclusion with."
- **Variant field**: None.
- **Response shape**: `result["video"]["url"]` (File object; optional `file_name`, `content_type`, `file_size`).
- **Sync vs queue**: Queue (`fal.subscribe`).
- **Output URL TTL**: Not documented; download immediately.
- **Media reference contract**: Any string URL per FAL platform convention.
- **Other relevant fields**: `loop` (boolean, default `false` — blends end with beginning for seamless looping).

---

### `fal:wan-2.5-t2v` → `fal-ai/wan-25-preview/text-to-video`

**Slug note**: The plan candidate `fal-ai/wan-25-preview/text-to-video` is the correct canonical slug. The alternative slugs `fal-ai/wan/v2.5/text-to-video` and similar were not verified to exist; the `wan-25-preview` slug resolves correctly.

- **Endpoint ID**: `fal-ai/wan-25-preview/text-to-video`
- **Modality**: T2V
- **Family**: `wan` (sole Wan entry; distinct family due to audio_url support)
- **Cost tier**: `standard`
- **Required**: `prompt` (string, max 800 chars — shortest prompt limit in the catalog; supports Chinese and English).
- **Duration enum**: `"5"`, `"10"` (seconds as bare integer strings). Default `"5"`.
- **Resolution / size enum**: `"480p"`, `"720p"`, `"1080p"`. Default `"1080p"` (highest default resolution in catalog).
- **Aspect ratio enum**: `"16:9"`, `"9:16"`, `"1:1"`. Default `"16:9"`. Three values (same set as Kling Pro T2V).
- **`audio_url` input field**: Present and optional. Accepts WAV or MP3, 3–30 seconds, max 15 MB. Audio is truncated if it exceeds video duration; silent generation if omitted. This is the only video endpoint in the catalog with audio input support — a key differentiator confirmed by schema.
- **First-frame ref field**: Not present — this is a T2V-only endpoint; no `image_url` field.
- **Last-frame / end-frame ref**: Not present.
- **Variant field**: None.
- **Response shape**: `result["video"]["url"]`. The video File object is richer than other endpoints: includes `url`, `content_type`, `file_name`, `file_size`, plus `width`, `height`, `fps`, `duration`, `num_frames`. Also returns top-level `seed` (integer) and `actual_prompt` (string, optional — the rewritten prompt when expansion is active).
- **Sync vs queue**: Queue (`fal.subscribe`).
- **Output URL TTL**: Not documented; download immediately.
- **Media reference contract**: N/A (T2V; no image inputs).
- **Other relevant fields**: `negative_prompt` (string, max 500 chars), `enable_prompt_expansion` (boolean, default `true`), `enable_safety_checker` (boolean, default `true`), `seed` (integer, optional).

---

### `fal:seedance-1.5-pro` — two backing endpoints

The `fal:seedance-1.5-pro` user-facing ID auto-routes between T2V and I2V based on whether `image_url` is provided. Both backing slugs are verified below.

#### Backing endpoint A: `fal-ai/bytedance/seedance/v1.5/pro/text-to-video`

- **Endpoint ID**: `fal-ai/bytedance/seedance/v1.5/pro/text-to-video`
- **Modality**: T2V
- **Family**: `seedance`
- **Cost tier**: `standard`
- **Required**: `prompt` (string).
- **Duration enum**: `"4"`, `"5"`, `"6"`, `"7"`, `"8"`, `"9"`, `"10"`, `"11"`, `"12"` (seconds as strings). Default `"5"`. Nine discrete values.
- **Resolution / size enum**: `"480p"`, `"720p"`, `"1080p"`. Default `"720p"`.
- **Aspect ratio enum**: `"21:9"`, `"16:9"`, `"4:3"`, `"1:1"`, `"3:4"`, `"9:16"`, `"auto"`. Default `"16:9"`. Widest AR support among video endpoints; includes `"auto"`.
- **`audio_url` input field**: Not present.
- **First-frame ref field**: N/A (T2V).
- **Last-frame / end-frame ref**: Not present.
- **Variant field**: None.
- **Response shape**: `result["video"]["url"]` (File object). Also returns top-level `seed` (integer).
- **Sync vs queue**: Queue (`fal.subscribe`).
- **Output URL TTL**: Not documented; download immediately.
- **Media reference contract**: N/A (T2V).
- **Other relevant fields**: `camera_fixed` (boolean, default `false` — lock camera position), `seed` (integer, optional), `generate_audio` (boolean, default `true`), `enable_safety_checker` (boolean, default `true`).

#### Backing endpoint B: `fal-ai/bytedance/seedance/v1.5/pro/image-to-video`

- **Endpoint ID**: `fal-ai/bytedance/seedance/v1.5/pro/image-to-video`
- **Modality**: I2V
- **Family**: `seedance`
- **Cost tier**: `standard`
- **Required**: `prompt` (string) AND `image_url` (string) — both required. Field name is `image_url` (consistent with Hailuo Pro I2V; differs from Kling's `start_image_url`).
- **Duration enum**: `"4"` through `"12"` — same nine discrete values as T2V variant. Default `"5"`.
- **Resolution / size enum**: `"480p"`, `"720p"`, `"1080p"`. Default `"720p"`. Same as T2V.
- **Aspect ratio enum**: `"21:9"`, `"16:9"`, `"4:3"`, `"1:1"`, `"3:4"`, `"9:16"`, `"auto"`. Default `"16:9"`. Same set as T2V — unusual: most I2V endpoints omit AR (deriving it from the image).
- **`audio_url` input field**: Not present.
- **First-frame ref field**: `image_url` (string, required).
- **Last-frame / end-frame ref**: `end_image_url` (string, optional) — "The URL of the image the video ends with."
- **Variant field**: None.
- **Response shape**: `result["video"]["url"]` (File object). Also returns top-level `seed` (integer).
- **Sync vs queue**: Queue (`fal.subscribe`).
- **Output URL TTL**: Not documented; download immediately.
- **Media reference contract**: `image_url` and `end_image_url` accept any string URL per FAL platform convention.
- **Other relevant fields**: `camera_fixed` (boolean, default `false`), `seed` (integer), `generate_audio` (boolean, default `true`), `enable_safety_checker` (boolean, default `true`).

---

## PR 3 — adapter family grouping

Based on verified schemas, the video catalog needs **three** distinct request-builder families plus routing logic for the dual-slug Seedance case:

1. **`kling_pro` family** (T2V and I2V variants) — distinct because: (a) I2V uses `start_image_url` (not `image_url`), (b) no `aspect_ratio` on I2V, (c) supports `end_image_url` and `elements`, (d) per-second duration enum `"3"`–`"15"`.

2. **`hailuo` family** (Standard T2V and Pro I2V) — distinct because: (a) fixed resolution (not user-configurable), (b) no `aspect_ratio` field, (c) no `duration` on I2V variant, (d) Pro I2V uses `image_url` (standard name). Standard T2V is the only `budget`-tier video endpoint.

3. **`standard_video` family** (Luma Ray 2, Wan 2.5, Seedance T2V + I2V) — share the same response shape and broadly similar field names. Sub-differences handled by per-entry field maps:
   - Luma Ray 2: duration values include `s` suffix (`"5s"`, `"9s"`); unified slug for T2V+I2V.
   - Wan 2.5: only endpoint with `audio_url`; richest response metadata (fps, width, height, num_frames).
   - Seedance: dual-slug routing on `image_url` presence; AR field present on both T2V and I2V (unlike peers); `camera_fixed` field.

One response parser handles all video endpoints: `result["video"]["url"]`.

## PR 3 — cost tier mapping (verified against schema positioning)

| User-facing ID | Backing endpoint(s) | Cost tier | Basis |
|---|---|---|---|
| `fal:hailuo-02-standard-t2v` | `fal-ai/minimax/hailuo-02/standard/text-to-video` | `budget` | Standard tier, 768p fixed output, limited duration options |
| `fal:luma-ray-2-t2v` | `fal-ai/luma-dream-machine/ray-2` | `standard` | Tiered resolution (default 540p), mid-range positioning |
| `fal:wan-2.5-t2v` | `fal-ai/wan-25-preview/text-to-video` | `standard` | Preview tier, 1080p default, audio differentiator |
| `fal:seedance-1.5-pro` | `fal-ai/bytedance/seedance/v1.5/pro/*` | `standard` | Pro tier but ByteDance preview pricing |
| `fal:kling-v3-pro-t2v` | `fal-ai/kling-video/v3/pro/text-to-video` | `premium` | Kling Pro; finest-grained duration control; generate_audio default on |
| `fal:kling-v3-pro-i2v` | `fal-ai/kling-video/v3/pro/image-to-video` | `premium` | Kling Pro; start_image_url + end_image_url + elements |
| `fal:hailuo-02-pro-i2v` | `fal-ai/minimax/hailuo-02/pro/image-to-video` | `premium` | 1080p fixed output, Pro I2V tier — comparable to Kling Pro |

Note: Hailuo Pro I2V is placed `premium` (matching the plan's stated mapping) because the 1080p fixed output and Pro tier designation align it with Kling Pro rather than Standard tier. This differs from Hailuo Standard (`budget`) despite sharing the same `hailuo` adapter family.
