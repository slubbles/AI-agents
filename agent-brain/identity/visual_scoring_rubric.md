# Visual Scoring Calibration Rubric

## Purpose
This document defines **what specific scores mean** so the visual evaluator
produces consistent, calibrated ratings. Claude Vision uses this rubric to
score screenshots of pages built by Agent Hands.

## Score Scale Definition

### Score 10 — Agency Quality
**What it looks like:** You'd pay $5,000+ for this page. Every pixel intentional.
- Typography: Perfect hierarchy — 3 levels max, weights contrast sharply
- Spacing: Consistent 4px/8px grid. Every margin/padding feels "right"
- Color: Cohesive palette, perfect contrast ratios (WCAG AA+), accent used sparingly
- Components: shadcn/ui used correctly — no raw HTML elements visible
- Animation: Framer Motion entrance animations, hover states on all interactive elements
- Empty space: Generous whitespace, nothing cramped
- Responsive: Looks designed separately for mobile (not just reflowed)
- Polish: Custom 404, loading states with skeleton, error boundaries styled

### Score 8-9 — Production Ready (Ship It)
**What it looks like:** Professional. You'd show this to investors or clients.
- Typography: Clear hierarchy, readable at all sizes
- Spacing: Consistent throughout, maybe 1-2 spots slightly off
- Color: Good palette, accessible contrast, dark mode works
- Components: shadcn/ui used everywhere, consistent styling
- Animation: At least section fade-ins, button hover states
- Empty space: Sufficient breathing room
- Responsive: Works on mobile, maybe not perfect but functional
- Polish: Loading states exist, errors handled gracefully

### Score 6-7 — Decent but Needs Polish
**What it looks like:** A developer built it, not a designer. Functional but forgettable.
- Typography: Font selected but hierarchy unclear (too many similar sizes/weights)
- Spacing: Some inconsistencies — uneven padding, cramped sections
- Color: Working palette but bland or slightly off (too much gray, weak accent)
- Components: Mix of shadcn/ui and custom — inconsistent styling
- Animation: Minimal or missing. No entrance animations. Basic hover only.
- Empty space: Either too much (sparse) or too little (cramped)
- Responsive: Mobile works but feels like an afterthought
- Missing: Loading states, error boundaries, or empty states not designed

### Score 4-5 — Below Average
**What it looks like:** Clearly unfinished. A prototype, not a product.
- Typography: Default system font or mismatched fonts
- Spacing: Visibly inconsistent — some elements touching, others floating
- Color: Default/generic colors, poor contrast, no intentional palette
- Components: Raw HTML or unstyled components visible
- Animation: None
- Empty space: Either a wall of content or barren emptiness
- Responsive: Broken on mobile — overflow, cut-off text, unusable layout
- Missing: No loading states, errors show raw messages

### Score 1-3 — Broken
**What it looks like:** White page with text, crashed UI, or major layout failure.
- Layout fundamentally broken (overlapping elements, no grid)
- Missing CSS (unstyled HTML)
- Blank/empty screens with no content
- JavaScript errors visible
- Images broken, fonts not loading
- Completely unusable on any device

## Dimension-Specific Calibration

### Layout & Spacing
| Score | Description |
|---|---|
| 10 | Perfect grid alignment, consistent padding, intentional whitespace |
| 8 | Grid-based, consistent, minor alignment issue (1 spot) |
| 6 | Mostly consistent but 2-3 spacing issues noticeable |
| 4 | Inconsistent throughout, cramped or overly sparse |
| 2 | No grid system, random spacing |

### Typography
| Score | Description |
|---|---|
| 10 | 3-level hierarchy, perfect weight contrast, Inter/system font, tracking-tight on headings |
| 8 | Clear hierarchy, good readability, consistent font usage |
| 6 | Font chosen but sizes too similar, weight contrast weak |
| 4 | Default fonts, no visible hierarchy |
| 2 | Multiple mismatched fonts, unreadable sizes |

### Color & Contrast
| Score | Description |
|---|---|
| 10 | Cohesive palette, WCAG AAA contrast, subtle gradients, perfect dark mode |
| 8 | Good palette, AA contrast, dark mode works |
| 6 | Working colors but bland, some contrast issues |
| 4 | Generic/default colors, poor contrast on some elements |
| 2 | No intentional palette, text unreadable against background |

### Components
| Score | Description |
|---|---|
| 10 | All shadcn/ui, consistent variants, custom touches, icons from one set |
| 8 | shadcn/ui throughout, consistent button/card/input styling |
| 6 | Mix of styled and unstyled components |
| 4 | Raw HTML elements visible, inconsistent styling |
| 2 | Unstyled form fields, default browser buttons |

### Responsiveness
| Score | Description |
|---|---|
| 10 | Looks designed for each breakpoint separately, mobile-first |
| 8 | Works well on mobile and desktop, few minor issues |
| 6 | Mobile usable but clearly desktop-first |
| 4 | Mobile partially broken (horizontal scroll, overflow) |
| 2 | Completely broken on mobile |

### Polish
| Score | Description |
|---|---|
| 10 | Entrance animations, hover/focus states, skeleton loading, styled errors, custom empty states |
| 8 | Hover states, loading indicators, error handling visible |
| 6 | Basic interactivity, some loading states |
| 4 | No hover states, no loading indicators |
| 2 | No interactive feedback whatsoever |

## Marketing Page Calibration Adjustments

Marketing pages are judged MORE harshly on:
- **Above-the-fold impact** (must pass 5-second test: can you tell what it does?)
- **Social proof presence** (testimonials, logos, stats)
- **CTA prominence** (button must be the most visible element)
- **Copy quality** (outcome-focused headlines, not feature descriptions)
- **Animation** (hero entrance, section reveals — expected in marketing)

Marketing pages are judged LESS harshly on:
- Complex component styling (fewer forms, tables, etc.)
- Error/loading states (mostly static content)

## Strategy Evolution Integration

Visual scores are stored alongside execution results. The meta-analyst can:
1. Read visual score trends across builds
2. Identify which design system rules are consistently violated
3. Propose updates to `design_system.md` or `marketing_design.md`
4. Track improvement: "average visual score went from 6.2 to 7.8 after v1.1 design system update"

The visual score target is **≥ 8.0** for production builds.

## Version History
- **v1.0** (2026-03-03): Initial calibration rubric — score definitions, dimension tables, marketing adjustments.
