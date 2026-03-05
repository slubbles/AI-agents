---
name: Feature Dev Methodology
description: 7-phase structured workflow for building features - from discovery through quality review
tags: [workflow, feature-dev, planning, architecture, quality]
priority: 4
---

# Feature Development Methodology

A structured 7-phase approach to building features. Prevents jumping straight into code without understanding the problem.

## The 7 Phases

### Phase 1: Discovery
- Clarify what needs to be built
- Identify the problem being solved
- List constraints and requirements
- Confirm understanding before proceeding

### Phase 2: Codebase Exploration
- Explore existing code for similar patterns
- Map relevant architecture and abstractions
- Identify key files and integration points
- Read and understand all related code before designing

### Phase 3: Clarifying Questions
- Generate questions based on codebase findings
- Address edge cases, error handling, performance
- Resolve ambiguity in requirements
- Get explicit answers before architecture design

### Phase 4: Architecture Design
- Design the solution with components, data flow, and interfaces
- Follow existing patterns in the codebase
- Create file-level plan: new files, modified files, dependencies
- Address identified edge cases and error states
- Include rollback strategy for complex changes

### Phase 5: Implementation Planning
- Convert architecture into ordered, concrete steps
- Each step should be independently verifiable
- Dependencies between steps are explicit
- Critical path identified (what blocks what)

### Phase 6: Implementation
- Execute steps in order
- Write complete, working code (no placeholders)
- Follow existing code conventions and patterns
- Include error handling and edge cases from Phase 3
- Test each component as it's built

### Phase 7: Quality Review
- Verify all requirements met
- Check edge case handling
- Validate code follows existing patterns
- Run tests, fix failures
- Review for security, performance, accessibility

## When to Use This Methodology

Apply the full 7-phase workflow for:
- New features with >3 steps
- Features touching multiple files or modules
- Changes requiring architectural decisions
- Unfamiliar codebases or domains

For simple fixes (1-2 files, clear change), skip to Phase 5-6.

## Key Principles

1. **Understand before you build.** Phase 1-3 prevent wasted effort.
2. **Design before you code.** Phase 4 catches integration issues early.
3. **Follow existing patterns.** Don't introduce new patterns unless the existing ones are clearly inadequate.
4. **Complete implementations only.** Every function body, every component, every edge case.
5. **Quality is not optional.** Phase 7 is not a suggestion.
