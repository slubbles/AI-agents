"""
Shared Constants — Single source of truth for Agent Hands.

Consolidates skip dirs, key filenames, binary extensions, and other
constants that were previously duplicated across multiple modules.
"""

# Directories to skip when scanning/walking workspace trees.
# Used by: planner.py, search.py, workspace_diff.py
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".next", ".nuxt",
    "dist", "build", ".cache", ".turbo", "coverage",
    ".venv", "venv", "env", ".env",
    ".pytest_cache", ".mypy_cache", ".tox", "egg-info",
    ".parcel-cache", ".svelte-kit", ".output",
}

# Key config/manifest files whose content gets injected into planner context.
# Used by: planner.py
KEY_FILENAMES = {
    "package.json", "tsconfig.json", "pyproject.toml", "requirements.txt",
    "setup.py", "setup.cfg", "cargo.toml", "go.mod", "dockerfile",
    ".gitignore", "readme.md", "readme.rst", ".env.example",
    "next.config.js", "next.config.mjs", "next.config.ts",
    "vite.config.ts", "vite.config.js", "tailwind.config.js",
    "eslint.config.js", ".eslintrc.json", "jest.config.js",
    "vitest.config.ts", "vitest.config.js", "playwright.config.ts",
}

# Extensions that indicate binary files (skip reading content).
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".xz",
    ".exe", ".dll", ".so", ".dylib", ".o", ".a",
    ".pyc", ".pyo", ".class", ".jar",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".webm",
    ".sqlite", ".db",
}

# Extensions that get priority in file tree display (shown first).
PRIORITY_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".go",
    ".json", ".toml", ".yaml", ".yml", ".md",
    ".css", ".scss", ".html",
}

# Max chars for workspace context in planner prompt
MAX_TREE_CHARS = 3000
MAX_KEY_FILE_CHARS = 4000

# Max files to track in workspace scans
MAX_WORKSPACE_FILES = 2000
