# Cortex Design System

## Purpose
This file defines the visual and interaction standards for everything Agent Hands builds.
Every landing page, SaaS product, and web application MUST follow these guidelines.
The goal: output that looks like it was built by a $150/hr design agency, not a template.

## Tech Stack (non-negotiable)
- **Framework**: Next.js 15+ (App Router)
- **Styling**: Tailwind CSS 4+
- **Components**: shadcn/ui (installed via `npx shadcn@latest add [component]`)
- **Animations**: Framer Motion (subtle, purposeful — never decorative)
- **Icons**: Lucide React (`lucide-react`)
- **Fonts**: Inter (body) + Cal Sans or Instrument Serif (headings) via `next/font`
- **Package Manager**: npm (NOT yarn, NOT pnpm)

## Color System

### Base Palette (dark mode first, light mode support)
Use CSS custom properties via Tailwind for theming:
```css
:root {
  --background: 0 0% 100%;
  --foreground: 222.2 84% 4.9%;
  --primary: 222.2 47.4% 11.2%;
  --primary-foreground: 210 40% 98%;
  --secondary: 210 40% 96.1%;
  --accent: 210 40% 96.1%;
  --muted: 210 40% 96.1%;
  --muted-foreground: 215.4 16.3% 46.9%;
  --destructive: 0 84.2% 60.2%;
  --border: 214.3 31.8% 91.4%;
  --ring: 222.2 84% 4.9%;
}
```

### Brand Color Strategy
- For each niche, derive a PRIMARY brand color from the domain context
- Use that color at 3 tints: strong (buttons, CTAs), medium (accents, borders), light (backgrounds)
- Neutral grays for text: `text-foreground` (headings), `text-muted-foreground` (body)
- NEVER use more than 3 colors + neutrals. Constraint = elegance.

## Typography

### Scale (Tailwind classes)
- Hero headline: `text-5xl md:text-7xl font-bold tracking-tight`
- Section headline: `text-3xl md:text-5xl font-bold tracking-tight`
- Subheadline: `text-xl md:text-2xl text-muted-foreground`
- Body: `text-base md:text-lg leading-relaxed`
- Small/caption: `text-sm text-muted-foreground`

### Rules
- Max line width: `max-w-prose` (~65ch) for body text
- Headings ALWAYS use `tracking-tight`
- Body text ALWAYS uses `leading-relaxed` or `leading-7`
- No orphan words in headlines (use `text-balance` or `<br className="hidden md:block" />`)

## Spacing System

### Section Spacing
- Between major sections: `py-20 md:py-32`
- Between sub-sections: `py-12 md:py-20`
- Container: `max-w-7xl mx-auto px-4 sm:px-6 lg:px-8`

### Component Spacing
- Card padding: `p-6 md:p-8`
- Stack gap: `space-y-4` (tight) / `space-y-8` (normal) / `space-y-12` (loose)
- Grid gap: `gap-6 md:gap-8`

### Rules
- NEVER use arbitrary values (`p-[37px]`). Use Tailwind scale.
- Consistent rhythm: 4, 6, 8, 12, 16, 20, 24, 32 (Tailwind units)
- More whitespace = more premium. When in doubt, add space.

## Layout Patterns

### Hero Section
```
Full-width gradient or subtle pattern background
├── Badge/pill ("New" / "Beta" / social proof)
├── Headline (5xl-7xl, bold, tracking-tight)
├── Subheadline (xl-2xl, muted, max-w-2xl mx-auto)
├── CTA group (primary button + secondary/ghost button)
└── Social proof strip (logos, avatars, or stats)
```

### Feature Grid
```
Section headline + description (centered, max-w-2xl mx-auto)
└── Grid (3 columns on lg, 2 on md, 1 on sm)
    └── Feature card
        ├── Icon (in colored circle or with accent background)
        ├── Title (lg font, semibold)
        └── Description (muted, 2-3 lines max)
```

### Pricing Section
```
Section headline + description
└── Grid (3 tiers, middle one highlighted with ring/scale)
    └── Pricing card
        ├── Plan name + badge ("Popular")
        ├── Price ($X/mo, with annual toggle if applicable)
        ├── Feature list (checkmarks, NOT bullets)
        └── CTA button (primary on featured, outline on others)
```

### Testimonial Section
```
Section headline
└── 3-column grid or horizontal scroll
    └── Testimonial card
        ├── Quote text (italic or with quote marks)
        ├── Avatar + Name + Role
        └── Star rating (optional)
```

### CTA Section (bottom)
```
Full-width gradient background
├── Headline ("Ready to get started?")
├── Subheadline (value recap)
└── CTA button (large, with arrow icon)
```

## Component Standards

### Buttons
- Primary: `bg-primary text-primary-foreground hover:bg-primary/90` with subtle scale animation
- Use shadcn `<Button>` component, NOT custom buttons
- Sizes: `size="lg"` for hero CTAs, `size="default"` elsewhere
- Always include hover and focus states
- CTA buttons should have directional icon (ArrowRight, ChevronRight)

### Cards
- Use shadcn `<Card>` with `<CardHeader>`, `<CardContent>`, `<CardFooter>`
- Subtle border + shadow: `border shadow-sm hover:shadow-md transition-shadow`
- Featured cards: add `ring-2 ring-primary` or `scale-105`

### Forms
- Use shadcn `<Input>`, `<Label>`, `<Select>`, `<Textarea>`
- Always show validation states (destructive border + message)
- Label above input, NOT floating labels
- Submit button full-width on mobile, auto on desktop

### Navigation
- Sticky header: `sticky top-0 z-50 bg-background/80 backdrop-blur-md border-b`
- Logo left, nav links center, CTA right
- Mobile: hamburger → sheet/drawer (shadcn `<Sheet>`)

## Animation Guidelines (Framer Motion)

### Entrance Animations (use sparingly)
```tsx
// Fade up on scroll (for sections)
initial={{ opacity: 0, y: 20 }}
whileInView={{ opacity: 1, y: 0 }}
viewport={{ once: true }}
transition={{ duration: 0.5 }}

// Stagger children (for grids)
transition={{ staggerChildren: 0.1 }}
```

### Interactive Animations
```tsx
// Button hover scale
whileHover={{ scale: 1.02 }}
whileTap={{ scale: 0.98 }}

// Card hover lift
whileHover={{ y: -4 }}
transition={{ type: "spring", stiffness: 300 }}
```

### Rules
- Duration: 0.3-0.5s for entrances, 0.15-0.2s for interactions
- Easing: `ease-out` for entrances, `spring` for interactions
- NEVER animate layout shifts that cause content jumping
- `viewport={{ once: true }}` — animate ONCE, not every scroll
- If motion could cause nausea, wrap in `prefers-reduced-motion` check

## Responsive Design

### Breakpoints (Tailwind defaults)
- `sm`: 640px (large phones landscape)
- `md`: 768px (tablets)
- `lg`: 1024px (small laptops)
- `xl`: 1280px (desktops)

### Mobile-First Rules
- Default styles = mobile. Layer up with `md:` and `lg:` prefixes.
- Touch targets: minimum 44x44px (use `min-h-[44px]` on buttons/links)
- No horizontal scroll — EVER
- Hero text: `text-3xl` mobile → `text-5xl md:text-7xl` desktop
- Grids: 1 column mobile → 2 md → 3 lg
- Images: `w-full` on mobile, constrained on desktop
- Navigation: always test hamburger menu on mobile

## Image & Media

- Use `next/image` component (NEVER raw `<img>`)
- Always set `width`, `height`, and `alt`
- For hero images: `priority` prop for LCP optimization
- Placeholder: `placeholder="blur"` with `blurDataURL`
- Aspect ratios: use `aspect-video` (16:9) or `aspect-square` for consistency
- If no real images available, use gradient backgrounds or abstract SVG patterns
  NEVER use placeholder image services (placeholder.com, via.placeholder.com)

## SEO & Performance

- Every page needs: `<title>`, `<meta name="description">`, OG tags
- Use Next.js `generateMetadata()` in page.tsx
- Semantic HTML: `<header>`, `<main>`, `<section>`, `<footer>`, `<nav>`
- Heading hierarchy: exactly one `<h1>` per page, then `<h2>`, `<h3>` in order
- Core Web Vitals targets: LCP < 2.5s, CLS < 0.1, INP < 200ms

## Anti-Patterns (NEVER do these)

- ❌ Rainbow gradients or neon colors (unless the niche explicitly calls for it)
- ❌ More than 2 fonts on one page
- ❌ Centered body text longer than 3 lines
- ❌ Generic stock photos of "diverse team looking at laptop"
- ❌ Autoplay video or audio
- ❌ Parallax scrolling (performance killer, often janky)
- ❌ Carousel/slider for important content (nobody clicks slide 2)
- ❌ Fixed-position elements that block content on mobile
- ❌ "Lorem ipsum" or any placeholder text — always write real copy
- ❌ Links that say "Click here" or "Learn more" without context
- ❌ Walls of text without visual breaks (icons, images, whitespace)

## Quality Bar

A Cortex-built page should:
1. Look professional within 0.5 seconds of loading (first impression)
2. Have clear visual hierarchy (you know where to look)
3. Work flawlessly on mobile (not just "not broken" — actually good)
4. Load fast (< 3s on 3G)
5. Have real, compelling copy (not filler)
6. Have one clear CTA that stands out
7. Feel like a $5,000 custom build, not a $50 template

If the output doesn't meet this bar, it needs another iteration.

## Application State Patterns

### Loading States
Every data-fetching region needs a skeleton or spinner. NEVER show a blank screen.

```tsx
// Route-level loading (src/app/dashboard/loading.tsx)
import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div className="space-y-6 p-6">
      <Skeleton className="h-8 w-48" />
      <div className="grid gap-4 md:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-32 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-64 rounded-xl" />
    </div>
  );
}

// Inline data loading (inside components)
{isLoading ? (
  <div className="flex items-center justify-center py-12">
    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
  </div>
) : (
  <DataTable data={data} />
)}
```

### Empty States
Every list/table/feed needs a designed empty state. It should guide the user to take action.

```tsx
// Empty state pattern
<div className="flex flex-col items-center justify-center py-16 text-center">
  <div className="rounded-full bg-muted p-4 mb-4">
    <InboxIcon className="h-8 w-8 text-muted-foreground" />
  </div>
  <h3 className="text-lg font-semibold">No projects yet</h3>
  <p className="text-sm text-muted-foreground mt-1 max-w-sm">
    Get started by creating your first project. It only takes a minute.
  </p>
  <Button className="mt-4" size="sm">
    <PlusIcon className="h-4 w-4 mr-2" />
    Create Project
  </Button>
</div>
```

### Error States
Route-level errors use Next.js error.tsx. Inline errors use Alert component.

```tsx
// Route-level error (src/app/dashboard/error.tsx)
"use client";

import { Button } from "@/components/ui/button";
import { AlertCircle } from "lucide-react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <AlertCircle className="h-10 w-10 text-destructive mb-4" />
      <h2 className="text-xl font-semibold">Something went wrong</h2>
      <p className="text-sm text-muted-foreground mt-1 max-w-md">
        {error.message || "An unexpected error occurred. Please try again."}
      </p>
      <Button onClick={reset} variant="outline" className="mt-4">
        Try Again
      </Button>
    </div>
  );
}

// Inline form/API error
<Alert variant="destructive">
  <AlertCircle className="h-4 w-4" />
  <AlertTitle>Error</AlertTitle>
  <AlertDescription>{errorMessage}</AlertDescription>
</Alert>
```

### Success/Confirmation States
```tsx
// Toast notification (use shadcn toast)
import { toast } from "sonner";
toast.success("Project created successfully");

// Inline success
<Alert className="border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-200">
  <CheckCircle2 className="h-4 w-4" />
  <AlertTitle>Success</AlertTitle>
  <AlertDescription>Your changes have been saved.</AlertDescription>
</Alert>
```

## Dark Mode

### Implementation
Use `next-themes` with Tailwind's `darkMode: "class"` strategy.

```tsx
// Theme provider (wrap in layout.tsx)
import { ThemeProvider } from "next-themes";

<ThemeProvider attribute="class" defaultTheme="system" enableSystem>
  {children}
</ThemeProvider>

// Theme toggle button
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

function ThemeToggle() {
  const { setTheme, theme } = useTheme();
  return (
    <Button variant="ghost" size="icon" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
      <Sun className="h-5 w-5 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
      <Moon className="absolute h-5 w-5 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
    </Button>
  );
}
```

### Rules
- ALWAYS test both light and dark mode. Both must look intentional.
- Use semantic color tokens (`bg-background`, `text-foreground`, `border`) not raw colors.
- Dark mode is NOT just "invert colors." Reduce contrast slightly, darken backgrounds, soften borders.
- Card surfaces: `bg-card` should be slightly lighter than `bg-background` in dark mode.

## Focus & Accessibility States

### Focus Rings
```css
/* All interactive elements must have visible focus rings */
focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2
```

### Keyboard Navigation
- All interactive elements must be reachable via Tab key
- Modals trap focus (shadcn Dialog does this automatically)
- Dropdown menus support arrow key navigation
- Escape key closes modals, dropdowns, drawers

### Screen Reader Support
- All images have descriptive `alt` text (not "image" or "photo")
- Icon-only buttons have `aria-label`
- Form inputs are associated with `<Label>` via `htmlFor`
- Status messages use `role="status"` or `aria-live="polite"`

## Version History

- **v1.0** (2026-03-03): Initial design system — tech stack, colors, typography, spacing, layout patterns, components, animations, responsive, anti-patterns, quality bar.
- **v1.1** (2026-03-03): Added application state patterns (loading/empty/error/success), dark mode, focus/accessibility states.
