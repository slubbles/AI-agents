---
name: Architecture Decisions
description: Software architecture decision framework for system design, scalability, and technical trade-offs. Applied during planning of complex multi-service features.
tags: [workflow, architecture, design, scalability, planning]
priority: 7
---

# Architecture Decision Framework

Guide for making and documenting architectural decisions when building complex features or systems.

## Architecture Review Process

### 1. Current State Analysis
- Review existing architecture and patterns
- Identify technical debt
- Assess scalability limitations

### 2. Requirements Gathering
- Functional requirements (user stories)
- Non-functional requirements (performance, security, scalability)
- Integration points and data flow

### 3. Design Proposal
- High-level architecture diagram
- Component responsibilities
- Data models and API contracts
- Integration patterns

### 4. Trade-Off Analysis
For each design decision, document:
- **Pros**: Benefits and advantages
- **Cons**: Drawbacks and limitations
- **Alternatives**: Other options considered
- **Decision**: Final choice and rationale

## Architectural Principles

### Modularity & Separation of Concerns
- Single Responsibility Principle
- High cohesion, low coupling
- Clear interfaces between components

### Scalability
- Horizontal scaling capability
- Stateless design where possible
- Efficient database queries
- Caching strategies

### Maintainability
- Clear code organization
- Consistent patterns
- Easy to test and understand

### Security
- Defense in depth
- Principle of least privilege
- Input validation at boundaries
- Secure by default

### Performance
- Efficient algorithms
- Minimal network requests
- Appropriate caching and lazy loading

## Common Patterns

### Frontend
- **Component Composition**: Complex UI from simple components
- **Container/Presenter**: Separate data logic from presentation
- **Custom Hooks**: Reusable stateful logic
- **Code Splitting**: Lazy load routes and heavy components

### Backend
- **Repository Pattern**: Abstract data access
- **Service Layer**: Business logic separation
- **Middleware Pattern**: Request/response processing
- **Event-Driven Architecture**: Async operations

### Data
- **Normalized Database**: Reduce redundancy
- **Denormalized for Reads**: Optimize query performance
- **Caching Layers**: Redis, CDN
- **Eventual Consistency**: For distributed systems

## System Design Checklist

### Functional
- [ ] User stories documented
- [ ] API contracts defined
- [ ] Data models specified
- [ ] UI/UX flows mapped

### Non-Functional
- [ ] Performance targets (latency, throughput)
- [ ] Scalability requirements
- [ ] Security requirements
- [ ] Availability targets (uptime %)

### Technical
- [ ] Architecture diagram created
- [ ] Component responsibilities defined
- [ ] Data flow documented
- [ ] Error handling strategy
- [ ] Testing strategy planned

### Operations
- [ ] Deployment strategy
- [ ] Monitoring and alerting
- [ ] Backup and recovery
- [ ] Rollback plan

## Anti-Patterns to Avoid

- **Big Ball of Mud**: No clear structure
- **Golden Hammer**: Using same solution for everything
- **Premature Optimization**: Optimizing before measuring
- **Not Invented Here**: Rejecting proven solutions
- **Analysis Paralysis**: Over-planning, under-building
- **Tight Coupling**: Components too dependent
- **God Object**: One class does everything

## Scalability Planning

- **10K users**: Monolith + good DB indexing sufficient
- **100K users**: Add caching (Redis), CDN for static assets
- **1M users**: Service decomposition, separate read/write DBs
- **10M users**: Event-driven architecture, distributed caching, multi-region
