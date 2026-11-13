# Frontend Interactive Controls & UI Polish Specification (Issue #12)

**Tracking Issue**: [#12: Frontend: Add Interactive Chart Controls, Log/Linear Toggles, and Polished UI Micro-Interactions](https://github.com/noedrflsh/Data_Engg_projet/issues/12)  
**Target Branch**: `master`  
**Feature Branch**: `12-frontend-interactive-controls`  

---

## 📌 Implementation Checklist

### 1. Interactive Chart Toolbars
- [ ] Add header action icons on all 7 OLAP scenario panels:
  - `Export PNG`: Generates high-res image download using `chartInstance.toBase64Image()`.
  - `Copy CSV`: Formats active chart data points (labels + values) into CSV text and copies to clipboard.
- [ ] Add toast confirmation on CSV copy ("Data copied to clipboard!").

### 2. Logarithmic vs Linear Scale Toggles
- [ ] Scenario 3(d) Movie Rating Distribution: Segmented toggle between Linear count and Log10 scale.
- [ ] Scenario 3(e) Total Ratings Volume Distribution: Segmented toggle between Linear bucket count and Log10 scale to clearly display long-tail titles without skew distortion.

### 3. Enriched Tooltip Formatter
- [ ] Calculate total sum of data points for distributions.
- [ ] Show percentage contribution in tooltip: e.g., `4.5★: 12,400 votes (18.6%)`.

### 4. Interactive Rating Micro-Interactions (Problem 4)
- [ ] Star selector hover feedback displaying textual rating descriptor:
  - `0.5 - 1.0`: Poor / Avoid
  - `1.5 - 2.5`: Mediocre / Below Average
  - `3.0 - 3.5`: Good / Solid
  - `4.0 - 4.5`: Great / Highly Recommended
  - `5.0`: Masterpiece
- [ ] Smooth rating submission feedback with response latency badge.

### 5. Transition Feedback & Skeletons
- [ ] Loading pulse state on chart boxes during active AJAX data fetching.
- [ ] Maintain 100% strict Light Mode with solid flat colors (no gradients).
