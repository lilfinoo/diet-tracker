# Workout catalog compaction — 2026-10-13

Internal Gemini catalog uses columns and rows. No candidate, metadata, slot, rule, response schema or validator removed. Roundtrip test verifies identical catalog. Public app response unchanged.

Five-day ABCDE / 90-minute case, 30 exercises, one provider attempt per case:
- Baseline: one valid result, 16.051 seconds; four provider 503 failures.
- Compact catalog: three valid results, 10.791 / 12.525 / 12.259 seconds; two provider 503 failures.
- Input tokens: 7759 to 6904 (11% reduction).

Small uneven sample does not establish causal latency improvement or guaranteed success. All completed results passed exercise selection and normalization. Provider failures remain possible.

Rejected output-alias experiment slowed five-day cases from 12.617 / 11.204 to 16.555 / 18.415 seconds; removed.

122 tests passed, three unrelated existing expectations deselected; targeted Ruff passed. No iOS build.
