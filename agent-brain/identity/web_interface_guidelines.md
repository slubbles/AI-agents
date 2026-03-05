# Web Interface Guidelines

> Source: Vercel Engineering (vercel-labs/web-interface-guidelines). 100+ rules across 16 categories.
> Apply these to all web interfaces. These are non-negotiable quality standards.

## Accessibility

- Use semantic HTML elements (`button`, `a`, `input`, not div with onClick)
- Add `aria-label` when visual meaning isn't conveyed by text
- Support keyboard navigation for ALL interactive elements
- Never remove focus outlines without providing visible alternatives
- Use `prefers-reduced-motion` media query for animations
- Test with screen readers and keyboard-only navigation

## Focus Management

- Visible focus indicators on all interactive elements (min 2px outline)
- Logical tab order following visual layout
- Trap focus in modals/dialogs (return focus on close)
- Don't auto-focus unless user explicitly triggered the interaction
- Use `focus-visible` for keyboard-only focus styles

## Forms

- Always associate labels with inputs (htmlFor/id or wrapping)
- Show validation errors inline, near the field
- Preserve user input on validation failure (never clear the form)
- Use appropriate input types (`email`, `tel`, `url`, `number`)
- Support autocomplete attributes
- Disable submit button only while submitting (never before first attempt)
- Show loading state during submission

## Animation

- Keep durations 100-300ms for UI transitions
- Use `transform` and `opacity` for performant animations (GPU-accelerated)
- Respect `prefers-reduced-motion` — reduce or disable animations
- Exit animations should be faster than enter animations
- Never animate layout properties (width, height, top, left) — use transform

## Typography

- Use system font stack or properly loaded web fonts
- Set line-height 1.4-1.6 for body text
- Limit line length to 60-80 characters
- Use relative units (rem/em) for font sizes
- Ensure minimum 16px for body text on mobile

## Content Handling

- Show skeleton screens or shimmer effects during loading (not spinners)
- Handle empty states with helpful messaging and actions
- Truncate long text with ellipsis and tooltip/expand option
- Show optimistic updates, revert on failure
- Handle error states gracefully with retry options

## Images

- Always set width and height attributes (prevent layout shift)
- Use `next/image` for automatic optimization
- Provide meaningful alt text (or empty alt="" for decorative)
- Use modern formats (WebP, AVIF) with fallbacks
- Lazy load below-fold images

## Performance

- Target < 100ms for UI feedback on user actions
- Use `will-change` sparingly and only before animation
- Virtualize long lists (> 100 items)
- Debounce search inputs (200-300ms)
- Throttle scroll/resize handlers
- Prefetch routes on hover/focus

## Navigation & State

- Reflect application state in the URL (shareable, bookmarkable)
- Support browser back/forward correctly
- Show current location in navigation (active states)
- Preserve scroll position on back navigation
- Use shallow routing for filter/sort changes

## Touch & Interaction

- Minimum 44x44px touch targets (WCAG 2.5.8)
- Add hover AND focus states to interactive elements
- Support swipe gestures where appropriate (with fallback)
- Prevent accidental double-taps/clicks (debounce submissions)
- Provide haptic feedback patterns for mobile where supported

## Safe Areas

- Respect `env(safe-area-inset-*)` for notched devices
- Don't place interactive elements in system gesture zones
- Account for virtual keyboard on mobile (viewport changes)

## Dark Mode

- Support `prefers-color-scheme` media query
- Don't just invert colors — design intentional dark palette
- Reduce image brightness slightly in dark mode
- Ensure sufficient contrast ratios in BOTH modes (WCAG AA: 4.5:1)

## Locale & i18n

- Don't hardcode text strings — use i18n framework
- Support RTL layouts with logical CSS properties (margin-inline-start, not margin-left)
- Format dates, numbers, currencies with Intl API
- Don't assume text length — allow for 2x expansion in translations

## Hydration Safety

- Don't render client-only values (window, Date.now()) during SSR
- Use `useEffect` for client-only computations
- Suppress hydration warnings only as last resort (with comment explaining why)
- Use `suppressHydrationWarning` sparingly

## Anti-Patterns to AVOID

- ❌ Using `div` or `span` as buttons (use `<button>`)
- ❌ Removing focus outlines without replacement
- ❌ Autoplaying videos/audio without user consent
- ❌ Breaking back button behavior
- ❌ Layout shift from loading content (use skeleton/placeholder)
- ❌ Infinite scroll without "load more" fallback
- ❌ Custom scrollbars that break native behavior
- ❌ Hover-only interactions with no touch/keyboard alternative
- ❌ Fixed/sticky elements covering content without escape
- ❌ Disabling zoom on mobile (`user-scalable=no`)
- ❌ Using `alert()`, `confirm()`, `prompt()` — use custom modals
- ❌ Links that look like buttons and buttons that look like links
