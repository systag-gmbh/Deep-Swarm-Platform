# Presidio Frontend UX Improvements

## Changes

### 1. Response Time Display

Show total round-trip time (both `/analyze` + `/anonymize`) as a badge in the results header, next to the entity count.

- Add `responseTime` state (initially `null`)
- Record `performance.now()` before first fetch and after all calls complete in `handleAnalyze()`
- Render as a styled badge matching existing entity count badge style
- Format: ms for < 1000ms, seconds (1 decimal) for >= 1000ms
- Clear on `handleClear()`

### 2. Hide Settings Icon When Base URL Is Empty

When `ANALYZER_BASE` is empty (same-origin mode), hide the settings gear icon since there's nothing useful to configure.

- Conditionally render the settings button based on `ANALYZER_BASE` value
