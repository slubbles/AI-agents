# React & Next.js Best Practices

> Source: Vercel Engineering (vercel-labs/agent-skills). 58 rules across 8 categories.
> Apply these when writing any React/Next.js code.

## Rule Categories by Priority

| Priority | Category | Impact |
|----------|----------|--------|
| 1 | Eliminating Waterfalls | CRITICAL |
| 2 | Bundle Size Optimization | CRITICAL |
| 3 | Server-Side Performance | HIGH |
| 4 | Client-Side Data Fetching | MEDIUM-HIGH |
| 5 | Re-render Optimization | MEDIUM |
| 6 | Rendering Performance | MEDIUM |
| 7 | JavaScript Performance | LOW-MEDIUM |

## 1. Eliminating Waterfalls (CRITICAL)

- Move `await` into branches where actually used (defer await)
- Use `Promise.all()` for independent async operations
- Start promises early, await late in API routes
- Use `<Suspense>` boundaries to stream content progressively

## 2. Bundle Size Optimization (CRITICAL)

- Import directly from modules, avoid barrel files (index.ts re-exports)
- Use `next/dynamic` for heavy components (code splitting)
- Load analytics/logging AFTER hydration (defer third-party)
- Load modules only when feature is activated (conditional imports)
- Preload on hover/focus for perceived speed

## 3. Server-Side Performance (HIGH)

- Authenticate server actions like API routes (don't skip auth)
- Use `React.cache()` for per-request deduplication
- Avoid duplicate serialization in RSC props
- Hoist static I/O (fonts, logos) to module level
- Minimize data passed from server to client components
- Restructure components to parallelize fetches
- Use `after()` for non-blocking post-response operations

## 4. Client-Side Data Fetching (MEDIUM-HIGH)

- Use SWR for automatic request deduplication
- Deduplicate global event listeners
- Use passive listeners for scroll events
- Version and minimize localStorage data

## 5. Re-render Optimization (MEDIUM)

- Don't subscribe to state only used in callbacks
- Extract expensive work into memoized components
- Hoist default non-primitive props outside render
- Use primitive dependencies in effects
- Subscribe to derived booleans, not raw values
- Derive state during render, not in effects
- Use functional setState for stable callbacks
- Pass function to useState for expensive initial values
- Use `startTransition` for non-urgent updates
- Use refs for transient frequent values

## 6. Rendering Performance (MEDIUM)

- Animate div wrapper, not SVG element directly
- Use `content-visibility: auto` for long lists
- Extract static JSX outside components
- Use ternary, not `&&` for conditional rendering
- Prefer `useTransition` for loading states

## 7. JavaScript Performance (LOW-MEDIUM)

- Group CSS changes via classes or cssText
- Build Map for repeated lookups (O(1) instead of O(n))
- Cache object properties in loops
- Combine multiple filter/map into one loop
- Check array length before expensive comparison
- Return early from functions
- Use Set/Map for O(1) lookups
