"""
Execution Strategy Templates — Default strategies for common domain types.

Provides sensible starting strategies so the first execution isn't strategy-less.
Templates are used as seeds when no evolved strategy exists for a domain.
They can also be used as cross-domain transfer seeds.
"""

# Default strategy for any domain with no specific template
DEFAULT_TEMPLATE = """# Execution Strategy — Default

## Planning Principles
- Break tasks into small, verifiable steps (max 3-5 steps for simple tasks)
- Always start with a project structure step: create directories, init package manager
- Each step should produce a verifiable artifact (file, output, etc.)
- Mark dependency installation and project setup as "required" criticality
- Mark linting, formatting, and documentation as "optional" criticality

## Code Quality
- Write clean, readable code with descriptive variable names
- Include error handling for I/O operations and external calls
- Add comments for non-obvious logic
- Follow the conventions of the target language/framework

## Tool Usage
- Use the 'code' tool for file creation and editing, not 'terminal' with echo/cat
- Use 'terminal' for package installation, builds, and running tests
- Use 'search' before creating files to check what already exists
- Use 'git' to commit completed work at the end

## Validation
- After creating code files, run them or their tests to verify they work
- Check for syntax errors before moving to the next step
- If a step fails, fix the issue before proceeding
"""

# Domain-specific templates
DOMAIN_TEMPLATES = {
    "nextjs-react": """# Execution Strategy — Next.js / React

## Planning Principles
- Always check for existing package.json before running npm init
- Initialize project with `npx create-next-app@latest` when starting fresh
- Break frontend work into: setup → components → pages → styling → testing
- Mark component creation as "required", styling as "optional"

## Code Patterns
- Use functional components with hooks (no class components)
- Prefer TypeScript over JavaScript for new Next.js projects
- Use CSS Modules or Tailwind — avoid inline styles
- Place components in src/components/, pages in src/app/ (App Router)
- Export components as default exports for page files, named for utilities

## Dependency Management
- Always install dependencies BEFORE importing them in code
- Use `npm install` not `yarn` unless the project already uses yarn
- Pin major versions: `npm install next@14 react@18 react-dom@18`
- Dev dependencies: `npm install -D typescript @types/react @types/node`

## Validation
- Run `npx tsc --noEmit` to check TypeScript errors
- Run `npm run build` to verify the project compiles
- Test individual components with simple renders before integration
""",

    "python": """# Execution Strategy — Python

## Planning Principles
- Check for existing requirements.txt or pyproject.toml first
- Create virtual environment if building a standalone project
- Break work into: setup → core logic → tests → documentation
- Structure: src/ for code, tests/ for tests, or flat for small projects

## Code Patterns
- Use type hints for function signatures
- Use dataclasses or Pydantic for structured data
- Follow PEP 8 naming: snake_case functions, PascalCase classes
- Use pathlib for file paths, not os.path where practical
- Use context managers for file I/O: `with open(...) as f:`

## Dependency Management
- Use `pip install` with requirements.txt or pyproject.toml
- Pin versions in requirements.txt
- Prefer stdlib solutions before adding dependencies

## Validation
- Run `python -m py_compile <file>` to check syntax
- Run tests with `python -m pytest` (install pytest first)
- Use `python -c "import <module>"` to verify imports work
""",

    "saas-building": """# Execution Strategy — SaaS Building

## Planning Principles
- Architecture first: define data models, API routes, then UI
- Break into layers: database → API → business logic → frontend → integration
- Always set up environment variables for secrets (never hardcode)
- Plan for authentication early — it touches everything

## Code Patterns
- RESTful API design: proper HTTP methods, status codes, JSON responses
- Separate concerns: routes, controllers, services, models
- Input validation on all API endpoints
- Error responses with consistent structure: {error: string, code: number}

## Security
- Hash passwords (bcrypt), never store plaintext
- Validate and sanitize all user input
- Use parameterized queries, never string interpolation for SQL
- Set CORS headers appropriately

## Validation
- Test API endpoints with curl or the http tool
- Verify database operations with simple CRUD tests
- Check that error cases return proper status codes
""",

    "growth-hacking": """# Execution Strategy — Growth / Marketing Tools

## Planning Principles
- Focus on data collection → analysis → visualization pipeline
- Prefer simple scripts over complex frameworks
- Output should be human-readable (CSVs, charts, reports)
- Mark data collection as "required", visualization as "optional"

## Code Patterns
- Use pandas for data manipulation
- Use matplotlib/plotly for visualization
- Structure as standalone scripts with clear input → output
- Log all API calls and data transformations

## Validation
- Verify data output isn't empty
- Check calculations with known test inputs
- Ensure output files are written correctly
""",
}


def get_template(domain: str) -> str:
    """
    Get the best strategy template for a domain.
    
    Returns domain-specific template if available, otherwise default.
    Also checks for partial matches (e.g., 'nextjs-saas' matches 'saas-building').
    """
    # Exact match
    if domain in DOMAIN_TEMPLATES:
        return DOMAIN_TEMPLATES[domain]
    
    # Partial match: check if any template key is contained in domain or vice versa
    domain_lower = domain.lower()
    for key, template in DOMAIN_TEMPLATES.items():
        key_parts = key.replace("-", " ").replace("_", " ").split()
        if any(part in domain_lower for part in key_parts):
            return template
    
    return DEFAULT_TEMPLATE


def list_templates() -> list[str]:
    """List available template domain names."""
    return ["default"] + sorted(DOMAIN_TEMPLATES.keys())
