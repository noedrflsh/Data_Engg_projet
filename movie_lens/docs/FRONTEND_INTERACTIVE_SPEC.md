# Frontend Interactive Controls & UI Polish Specification (Issue #12)

**Tracking Issue**: [#12: Frontend: Add Interactive Chart Controls, Log/Linear Toggles, and Polished UI Micro-Interactions](https://github.com/noedrflsh/Data_Engg_projet/issues/12)  
**Target Branch**: `master`  
**Feature Branch**: `12-frontend-interactive-controls`  
**Pull Request**: [#13: feat(ui): add interactive chart controls, log/linear scale toggles, and UI micro-interactions (Closes #12)](https://github.com/noedrflsh/Data_Engg_projet/pull/13)  

---

## 📌 Implementation Checklist

### 1. Interactive Chart Toolbars
- [x] Add header action icons on analytical scenario panels:
  - `Export PNG`: Generates high-res image download using `chartInstance.toBase64Image()`.
  - `Copy CSV`: Formats active chart data points (labels + values) into CSV text and copies to clipboard.
- [x] Add Swiss brutalist toast confirmation on CSV copy ("CLIPBOARD: DATA COPIED AS CSV").

### 2. Logarithmic vs Linear Scale Toggles
- [x] Scenario 3(d) Movie Rating Distribution: Segmented toggle between Linear count (`LIN`) and Logarithmic (`LOG`) scale.
- [x] Scenario 3(e) Total Ratings Volume Distribution: Segmented toggle between Linear bucket count (`LIN`) and Logarithmic (`LOG`) scale to clearly display long-tail titles without skew distortion.

### 3. Enriched Tooltip Formatter
- [x] Calculate total sum of data points for distributions.
- [x] Show percentage contribution in tooltip: e.g., `VOTES: 24,800 (28.4%)`.

### 4. Interactive Rating Micro-Interactions (Problem 4)
- [x] Dual-control Star selector & discrete range slider with live text descriptors:
  - `0.5`: "0.5 / 5.0 — DEFICIENT"
  - `1.0`: "1.0 / 5.0 — POOR"
  - `1.5`: "1.5 / 5.0 — MEDIOCRE"
  - `2.0`: "2.0 / 5.0 — BELOW AVERAGE"
  - `2.5`: "2.5 / 5.0 — MEDIAN"
  - `3.0`: "3.0 / 5.0 — DECENT"
  - `3.5`: "3.5 / 5.0 — SOLID"
  - `4.0`: "4.0 / 5.0 — PRAISEWORTHY"
  - `4.5`: "4.5 / 5.0 — EXCELLENT"
  - `5.0`: "5.0 / 5.0 — CANONICAL MASTERPIECE"
- [x] Smooth rating submission feedback with response latency badge and instant KPI updates.

### 5. Architectural Brutalism / Swiss International Minimalist Design Language
- [x] High-contrast black outlines (`1.5px solid #000000`), stark white canvases (`#fafafa` / `#ffffff`), deep cobalt accents (`#1d4ed8`), zero gradients.
- [x] Distinct typography: Inter (sans-serif), Newsreader (editorial numerals), JetBrains Mono (precision tabular metrics).
- [x] Maintained 100% test passage (14/14 tests in `test_suite.py`).
