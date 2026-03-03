# Cortex Marketing Design System

## Purpose
This file defines the visual and conversion standards for marketing/landing pages built by Agent Hands.
These pages are **conversion-optimized** — every element exists to move a visitor toward a CTA.
Different from the app design system: marketing pages prioritize first impression, emotional response, and clarity of value proposition over app UX patterns.

## Tech Stack
Same as core design system:
- **Framework**: Next.js 15+ (App Router, static export or ISR)
- **Styling**: Tailwind CSS 4+
- **Components**: shadcn/ui
- **Animations**: Framer Motion (more aggressive than in-app — marketing pages need wow factor)
- **Icons**: Lucide React
- **Fonts**: Inter (body) + Cal Sans or Instrument Serif (headings) via `next/font`

## Page Structure (top to bottom)

### 1. Navigation Bar
```
Sticky header: sticky top-0 z-50 bg-background/80 backdrop-blur-md border-b
├── Logo (left) — SVG or text mark, links to /
├── Nav links (center) — 3-5 max: Features, Pricing, Testimonials, FAQ
├── CTA button (right) — "Get Started" or "Try Free"
└── Mobile: hamburger → Sheet drawer
```

**Rules:**
- Max 5 navigation links. Fewer = better.
- Navigation CTA uses `size="sm"` variant, matches the main CTA text.
- On scroll past hero: nav becomes slightly more opaque with shadow.
- Logo and CTA are the ONLY things that should be visible at a glance.

### 2. Hero Section (above the fold — most important section)
```
Full-width section with gradient/pattern background
├── Optional: Badge/pill ("New Feature" / "Used by 500+ teams")
├── Headline: 5xl-7xl, bold, tracking-tight
│   └── One line that states the OUTCOME, not the feature
│       Good: "Ship client projects 3x faster"
│       Bad: "Project management tool for agencies"
├── Subheadline: xl-2xl, text-muted-foreground, max-w-2xl mx-auto
│   └── Expand the headline — who is this for, what pain does it solve
├── CTA group:
│   ├── Primary: large button, strong color, with ArrowRight icon
│   └── Secondary: ghost/outline button ("See Demo" / "View Pricing")
├── Social proof strip:
│   └── Avatar stack + "Trusted by 500+ teams" OR logo row OR star rating
└── Optional: Hero image/screenshot (below CTAs, with subtle shadow)
```

**Rules:**
- Headline is THE most important element on the page. Agonize over it.
- Headline must state a specific OUTCOME with a number when possible.
- Hero section padding: `pt-20 pb-24 md:pt-32 md:pb-40` — generous top/bottom.
- Background: subtle gradient from primary to background, or dot pattern, or radial gradient.
- CTA buttons must have padding: `px-8 py-3` minimum. They should feel "big."
- Social proof MUST appear in the hero. No trust = no scroll.
- NEVER put a form in the hero unless it's the entire product (e.g., email capture).

### 3. Logo Strip / Social Proof Bar
```
"Trusted by teams at" + row of 4-6 grayscale logos
```

**Rules:**
- Logos should be grayscale (`opacity-50 hover:opacity-100 transition-opacity`).
- If no real logos: use placeholder company names styled as text logos.
- Spacing: `py-12 md:py-16` with subtle top border.
- This section exists purely for trust. Keep it minimal.

### 4. Features Section
```
Section headline ("Everything you need to _____")
+ Subtitle (text-muted-foreground, max-w-2xl mx-auto, text-center)
└── 3-column grid (lg:grid-cols-3, gap-8)
    └── Feature card:
        ├── Icon in colored circle (bg-primary/10, p-3, rounded-xl)
        ├── Title (text-lg font-semibold, mt-4)
        └── Description (text-muted-foreground, 2-3 lines)
```

**Alternative: Bento Grid**
```
Section headline
└── Asymmetric grid (2 large + 3 small cards, or 1 hero + 4 standard)
    └── Each card:
        ├── Visual (screenshot, illustration, or animated demo)
        ├── Title + description
        └── Subtle hover effect (shadow-md → shadow-lg, or slight y-lift)
```

**Rules:**
- 3-6 features. Not 2 (looks sparse). Not 8 (overwhelming).
- Every feature title starts with a verb or outcome, not the feature name.
  Good: "Automate client updates"
  Bad: "Notification System"
- Icons use a consistent set from Lucide. All same size (h-6 w-6 or h-8 w-8).
- Card backgrounds: `bg-card border rounded-xl p-6`.

### 5. Problem → Solution Section
```
Two-column layout (text left, visual right OR alternating)
├── Pain point headline ("Tired of _____?")
├── Description of the problem (2-3 sentences, empathy-driven)
├── Arrow or transition
├── Solution headline ("With [Product], you _____")
└── Screenshot or illustration showing the solution
```

**Rules:**
- This section makes the visitor feel understood BEFORE you sell.
- Use real pain language from the research data (Brain's outputs).
- Alternating layout: odd sections text-left/image-right, even sections reversed.

### 6. How It Works (optional but effective)
```
Section headline ("How it works")
└── 3 numbered steps:
    1. [Icon + Number] Sign up → description
    2. [Icon + Number] Configure → description
    3. [Icon + Number] Ship → description
```

**Rules:**
- Always exactly 3 steps. The human brain likes 3.
- Each step: number in a circle + icon + title + 1-sentence description.
- Use connectors (arrows or lines) between steps on desktop.

### 7. Testimonials Section
```
Section headline ("What our users say")
└── 3-column grid OR horizontal scroll
    └── Testimonial card:
        ├── Quote text (text-base, italic or with oversized quote marks)
        ├── Author: Avatar + Name + Title + Company
        └── Optional: star rating (5 filled stars)
```

**Rules:**
- Minimum 3 testimonials. Use specific quotes, not generic praise.
- Good: "We reduced onboarding time from 2 weeks to 3 days."
- Bad: "Great product! Would recommend."
- Avatar is essential — faceless testimonials have near-zero trust value.
- If writing placeholder testimonials: make them specific and believable.

### 8. Pricing Section
```
Section headline ("Simple, transparent pricing")
+ Subtitle ("No hidden fees. Cancel anytime.")
+ Annual/Monthly toggle (saves X%)
└── Pricing grid (2-3 tiers, center tier highlighted)
    └── Pricing card:
        ├── Plan name (Starter / Pro / Enterprise)
        ├── Price: $X/mo (with /year shown if annual)
        ├── Description (1 line, who this tier is for)
        ├── Feature list (checkmarks ✓, NOT bullets)
        │   └── Key differentiator features BOLD
        ├── CTA button
        └── Optional: "Most Popular" badge on featured tier
```

**Rules:**
- Featured tier uses `ring-2 ring-primary scale-[1.02]` to visually pop.
- Non-featured tiers use `border` only.
- Feature lists aligned vertically across all tiers.
- Enterprise tier: "Contact Sales" instead of price.
- Annual pricing shows BOTH prices: "$29/mo → $24/mo billed annually."
- Show savings percentage on annual toggle.

### 9. FAQ Section
```
Section headline ("Frequently asked questions")
└── Accordion (shadcn Accordion component)
    └── 5-8 questions with answers
```

**Rules:**
- Use the real questions a potential customer would ask.
- Put "money" questions first: pricing, refunds, free trial.
- Keep answers concise: 2-3 sentences max per answer.
- Accordion, NOT show-all. Reduces visual overwhelm.

### 10. Final CTA Section
```
Full-width section with gradient or colored background
├── Headline ("Ready to [achieve outcome]?")
├── Subtitle (recap the #1 value proposition)
└── Large CTA button (same as hero CTA)
```

**Rules:**
- This section must feel conclusive, like a closing argument.
- Same button text as the hero CTA (consistency = trust).
- Background: gradient from primary to a darker shade, OR the inverse of the hero bg.
- No additional links or navigation. Just one CTA.

### 11. Footer
```
Grid layout:
├── Column 1: Logo + tagline + social icons
├── Column 2: Product links (Features, Pricing, Changelog)
├── Column 3: Company links (About, Blog, Careers)
├── Column 4: Legal links (Privacy, Terms, Contact)
└── Bottom bar: © 2026 Company Name. All rights reserved.
```

**Rules:**
- Footer is NOT a dumping ground. Max 4 columns.
- Social icons: small, muted color, in a row.
- Footer background: slightly different from body (`bg-muted/50` or `bg-card`).

## Conversion Optimization Rules

### Above the Fold (Critical)
1. Visitor must understand **what you do** within 5 seconds of landing.
2. Headline, subheadline, and CTA must be visible without scrolling on desktop.
3. No generic imagery. Use screenshots, illustrations, or meaningful graphics.
4. Social proof must appear above the fold.

### CTA Strategy
1. Primary CTA text: Use action + outcome. "Start Free Trial" > "Sign Up."
2. CTA appears in: nav bar, hero, mid-page (after features), final section. Minimum 3 times.
3. CTA color must contrast with everything around it. Usually `bg-primary` with nothing else on the page using that color at that intensity.
4. Secondary CTA: always less prominent. Use `variant="outline"` or `variant="ghost"`.

### Copy Guidelines
1. Headlines: Outcome-first. Must be understandable in isolation.
2. Subheadlines: Expand the headline. Add specificity and audience.
3. Body text: Short paragraphs (2-3 lines max). Use bullet points for lists.
4. Voice: Confident, clear, specific. Not salesy, not corporate.
5. Numbers are trust signals: "3x faster," "500+ teams," "$2M saved."
6. Address objections proactively (FAQ, "no credit card required," "cancel anytime").

### Visual Hierarchy
1. Eyes should travel: Headline → Subheadline → CTA → Social Proof → Scroll.
2. Only ONE primary visual focus per section (the thing you want them to see).
3. Whitespace around CTAs — don't crowd them. They need breathing room.
4. Color contrast: CTA buttons should be the brightest/most saturated element.

## Marketing Animation Patterns (Framer Motion)

```tsx
// Hero entrance — staggered fade up
const heroVariants = {
  hidden: { opacity: 0, y: 30 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.15, duration: 0.6, ease: "easeOut" },
  }),
};

// Use on hero elements:
<motion.h1 custom={0} variants={heroVariants} initial="hidden" animate="visible">
<motion.p custom={1} variants={heroVariants} initial="hidden" animate="visible">
<motion.div custom={2} variants={heroVariants} initial="hidden" animate="visible">

// Section entrance — fade up on scroll
<motion.section
  initial={{ opacity: 0, y: 40 }}
  whileInView={{ opacity: 1, y: 0 }}
  viewport={{ once: true, margin: "-100px" }}
  transition={{ duration: 0.6 }}
>

// Feature cards — staggered grid
<motion.div
  variants={{ visible: { transition: { staggerChildren: 0.1 } } }}
  initial="hidden"
  whileInView="visible"
  viewport={{ once: true }}
>
  {features.map((f) => (
    <motion.div key={f.id} variants={{ hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0 } }}>
      <FeatureCard {...f} />
    </motion.div>
  ))}
</motion.div>

// Counter animation (for stats: "500+ teams", "$2M saved")
// Use framer-motion's useMotionValue + useTransform or a counting library
```

**Marketing animation rules (more aggressive than app):**
- Hero animations run immediately on load (no scroll trigger).
- Section animations trigger at `margin: "-100px"` (slightly before visible).
- Stagger delay: 0.1-0.15s between children (faster than app animations).
- Duration: 0.5-0.7s for sections, 0.3s for cards.
- Stats/numbers should count up (animate from 0 to final value).
- `viewport={{ once: true }}` — ALWAYS. Never re-animate on scroll back.

## Marketing Anti-Patterns

- ❌ Generic hero ("Welcome to our platform") — must be specific
- ❌ No social proof above the fold — kills trust immediately
- ❌ CTA that says "Learn More" — it's a landing page, not Wikipedia
- ❌ More than one primary CTA per section — confusion = bounce
- ❌ Feature lists without benefits — "Real-time sync" → "Never miss a client update"
- ❌ Pricing without a featured tier — guide the decision, don't leave it open
- ❌ Testimonials without names/faces — anonymous praise = zero credibility
- ❌ Walls of text — marketing pages are scanned, not read
- ❌ Horizontal scroll on any device — instant unprofessional signal
- ❌ Missing mobile optimization — 60%+ traffic is mobile

## Responsive Marketing Rules

### Mobile-First Priorities
- Hero headline: `text-3xl` → `md:text-5xl` → `lg:text-7xl`
- Hero CTA buttons: full width on mobile (`w-full sm:w-auto`)
- Pricing cards: stack vertically (1 column), featured card first
- Feature grid: 1 column on mobile, 2 on md, 3 on lg
- Testimonials: horizontal scroll on mobile (`flex overflow-x-auto snap-x`)
- Navigation: hamburger on mobile, full nav on lg+
- Social proof logos: 3 visible on mobile (rest hidden), all visible on md+
- Section padding: `py-16 md:py-24 lg:py-32` — less on mobile, more on desktop

### Touch Optimization
- CTA buttons: `min-h-[48px]` on mobile (larger than the 44px app minimum)
- Nav hamburger: `p-2` minimum touch target
- Pricing toggle: large enough to tap without precision (`p-1 rounded-full`)

## Version History

- **v1.0** (2026-03-03): Initial marketing design system — page structure, conversion rules, CTA strategy, copy guidelines, animation patterns, responsive rules.
