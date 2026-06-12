# Layout Review Checklist

## Scope
- `src/App.tsx` (Login, Audit flow, Results)
- `src/components/Sidebar.tsx`
- `src/components/Classifier.tsx`
- `src/components/Dashboard.tsx`

## Breakpoints
- Mobile: `360x800`
- Tablet: `768x1024`
- Desktop: `1366x768`
- Wide: `1920x1080`

## Severity
- `Critical`: blocks core task completion
- `Major`: high friction or repeated confusion
- `Minor`: polish/usability improvement

## Global Checks (Run On Every Screen)
- [ ] No horizontal scroll
- [ ] Primary CTA is obvious
- [ ] Spacing rhythm is consistent
- [ ] Text hierarchy is readable
- [ ] Empty/loading/error states stay stable
- [ ] Long labels and filenames behave safely
- [ ] Keyboard focus is visible
- [ ] Color contrast is acceptable

## Screen Matrix
### 1) Login (`App.tsx` unauthenticated)
- [ ] Mobile
- [ ] Tablet
- [ ] Desktop
- [ ] Wide
Notes:

### 2) Audit - Step 1 Config (`App.tsx`)
- [ ] Mobile
- [ ] Tablet
- [ ] Desktop
- [ ] Wide
Notes:

### 3) Audit - Step 2 Upload (`App.tsx`)
- [ ] Mobile
- [ ] Tablet
- [ ] Desktop
- [ ] Wide
Notes:

### 4) Audit - Step 3 Results (`App.tsx`)
- [ ] Mobile
- [ ] Tablet
- [ ] Desktop
- [ ] Wide
Notes:

### 5) Sidebar Navigation (`Sidebar.tsx`)
- [ ] Mobile
- [ ] Tablet
- [ ] Desktop
- [ ] Wide
Notes:

### 6) Classifier - Upload/Queue (`Classifier.tsx`)
- [ ] Mobile
- [ ] Tablet
- [ ] Desktop
- [ ] Wide
Notes:

### 7) Classifier - Results Table (`Classifier.tsx`)
- [ ] Mobile
- [ ] Tablet
- [ ] Desktop
- [ ] Wide
Notes:

### 8) Classifier - Operator Modal (`Classifier.tsx`)
- [ ] Mobile
- [ ] Tablet
- [ ] Desktop
- [ ] Wide
Notes:

### 9) Dashboard - Filters/KPIs/Charts (`Dashboard.tsx`)
- [ ] Mobile
- [ ] Tablet
- [ ] Desktop
- [ ] Wide
Notes:

## High-Risk Checks (Pre-populated)
- [ ] Sidebar width/behavior on small viewports (`src/components/Sidebar.tsx`)
- [ ] Stepper wrapping/compression on mobile (`src/App.tsx`)
- [ ] Upload cards and action rows overlap on tablet (`src/App.tsx`)
- [ ] Results grid/chart/transcription stacking on mobile (`src/App.tsx`)
- [ ] Results table overflow and action button access (`src/components/Classifier.tsx`)
- [ ] Modal body and buttons fit in short-height screens (`src/components/Classifier.tsx`)
- [ ] Dashboard chart + recent audits stacking and readability (`src/components/Dashboard.tsx`)
- [ ] Garbled PT-BR accented text rendering in UI (`src/App.tsx`, `src/components/Dashboard.tsx`, `src/components/Classifier.tsx`)

## Findings Log
| ID | Screen/State | Viewport | Severity | Evidence | Suggested Fix | Owner | Status |
|---|---|---|---|---|---|---|---|
| LR-001 | App Shell width constraint | All | Critical | Root container still has Vite defaults (`src/App.css:1`, `src/App.css:2`, `src/App.css:4`) while app uses full-screen shell (`src/App.tsx:235`) | Remove/neutralize `#root` max-width and padding for app shell pages | FE | Implemented (pending QA) |
| LR-002 | Sidebar on small devices | Mobile/Tablet | Critical | Sidebar is fixed-width `w-64` with no responsive collapse (`src/components/Sidebar.tsx:14`) inside `flex h-screen` shell (`src/App.tsx:235`) | Add mobile drawer/hamburger and hide persistent sidebar below `md` | FE | Implemented (pending QA) |
| LR-003 | Stepper overflow risk | Mobile | Major | Stepper connector uses fixed `w-24 mx-4` (`src/App.tsx:347`) with 3 items and labels | Use responsive connector widths and allow wrapping or compact mobile stepper | FE | Implemented (pending QA) |
| LR-004 | Results actions row compression | Mobile | Major | Step 3 actions are one horizontal row (`src/App.tsx:775`) with large button paddings (`src/App.tsx:791`, `src/App.tsx:802`) | Add `flex-wrap` and mobile full-width stacking for action buttons | FE | Implemented (pending QA) |
| LR-005 | Classifier table mobile usability | Mobile/Tablet | Major | Results table is scrollable (`src/components/Classifier.tsx:387`) with many columns and long filename blocks (`src/components/Classifier.tsx:467`, `src/components/Classifier.tsx:472`) | Add card/list mobile variant or priority column collapse | FE | Implemented (pending QA) |
| LR-006 | Modal height handling on short screens | Mobile (short height) | Major | Modal uses centered fixed overlay (`src/components/Classifier.tsx:576`) and panel with no max-height/inner scroll (`src/components/Classifier.tsx:577`) | Add `max-h-[90vh] overflow-y-auto` to modal panel | FE | Implemented (pending QA) |
| LR-007 | Dashboard density at medium widths | Tablet | Major | Multiple dense grids (`src/components/Dashboard.tsx:139`, `src/components/Dashboard.tsx:177`, `src/components/Dashboard.tsx:233`) plus chip filters can create long vertical blocks | Rebalance breakpoints (`sm/md/lg`) and reduce concurrent card density at `md` | FE | Implemented (pending QA) |
| LR-008 | Global light-theme force overrides | Light theme (all) | Major | Broad `!important` overrides on semantic classes (`src/index.css:108`, `src/index.css:113`, `src/index.css:117`, `src/index.css:121`) | Scope light-theme overrides to component classes/tokens instead of utility-wide overrides | FE | Implemented (pending QA) |
| LR-009 | Root text alignment inheritance risk | All | Minor | `#root` sets `text-align: center` (`src/App.css:5`) which can leak into nested content unexpectedly | Remove root text alignment and control alignment per component | FE | Implemented (pending QA) |
| LR-010 | Primary color token mismatch | All themes | Minor | `primary` is blue in Tailwind config (`tailwind.config.js:16`) but orange in CSS variables (`src/index.css:10`) | Consolidate single primary palette source and refactor token usage | FE | Implemented (pending QA) |

## Top-10 Remediation Queue
| Rank | Finding ID | Impact | Effort (S/M/L) | Decision |
|---|---|---|---|---|
| 1 | LR-001 | Very high | S | Done (pending QA) |
| 2 | LR-002 | Very high | M | Done (pending QA) |
| 3 | LR-004 | High | S | Done (pending QA) |
| 4 | LR-003 | High | S | Done (pending QA) |
| 5 | LR-005 | High | M | Done (pending QA) |
| 6 | LR-006 | Medium-high | S | Done (pending QA) |
| 7 | LR-007 | Medium | M | Done (pending QA) |
| 8 | LR-008 | Medium | M | Done (pending QA) |
| 9 | LR-009 | Medium | S | Done (pending QA) |
| 10 | LR-010 | Medium | M | Done (pending QA) |

## Session Metadata
- Revisao: passada code-first
- Date: 2026-02-18
- Build/commit:
- Browser(s):
- Notes: Findings were inferred from source structure and CSS rules. Confirm each item with viewport validation before implementation.
