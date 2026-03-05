---
name: Security Reviewer Checklist
description: Security vulnerability detection and remediation checklist based on OWASP Top 10. Applied during code validation and execution.
tags: [coding, security, owasp, validation, review]
priority: 8
---

# Security Reviewer Checklist

Proactive security review checklist for web application code. Apply after writing code that handles user input, authentication, API endpoints, or sensitive data.

## OWASP Top 10 Check

1. **Injection** — Queries parameterized? User input sanitized? ORMs used safely?
2. **Broken Auth** — Passwords hashed (bcrypt/argon2)? JWT validated? Sessions secure?
3. **Sensitive Data** — HTTPS enforced? Secrets in env vars? PII encrypted? Logs sanitized?
4. **XXE** — XML parsers configured securely? External entities disabled?
5. **Broken Access** — Auth checked on every route? CORS properly configured?
6. **Misconfiguration** — Default creds changed? Debug mode off in prod? Security headers set?
7. **XSS** — Output escaped? CSP set? Framework auto-escaping?
8. **Insecure Deserialization** — User input deserialized safely?
9. **Known Vulnerabilities** — Dependencies up to date? npm audit clean?
10. **Insufficient Logging** — Security events logged? Alerts configured?

## Critical Code Patterns to Flag

| Pattern | Severity | Fix |
|---------|----------|-----|
| Hardcoded secrets | CRITICAL | Use environment variables |
| Shell command with user input | CRITICAL | Use safe APIs or execFile |
| String-concatenated SQL | CRITICAL | Parameterized queries |
| innerHTML = userInput | HIGH | Use textContent or DOMPurify |
| fetch(userProvidedUrl) | HIGH | Whitelist allowed domains |
| Plaintext password comparison | CRITICAL | Use bcrypt.compare() |
| No auth check on route | CRITICAL | Add authentication middleware |
| Balance check without lock | CRITICAL | Use FOR UPDATE in transaction |
| No rate limiting | HIGH | Add express-rate-limit or equivalent |
| Logging passwords/secrets | MEDIUM | Sanitize log output |

## Key Principles

1. **Defense in Depth** — Multiple layers of security
2. **Least Privilege** — Minimum permissions required
3. **Fail Securely** — Errors should not expose data
4. **Don't Trust Input** — Validate and sanitize everything
5. **Update Regularly** — Keep dependencies current

## Common False Positives

- Environment variables in .env.example (not actual secrets)
- Test credentials in test files (if clearly marked)
- Public API keys (if actually meant to be public)
- SHA256/MD5 used for checksums (not passwords)

Always verify context before flagging.

## When to Apply

- New API endpoints
- Authentication/authorization code changes
- User input handling
- Database query changes
- File uploads
- Payment code
- External API integrations
- Dependency updates
- Before production deployment
