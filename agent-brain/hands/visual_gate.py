"""
Visual Gate — Mid-build visual quality checks during execution.

Hooks into the executor's existing mid-gate system to add visual evaluation
at strategic points during frontend builds. When a dev server is running and
frontend files have been written, the visual gate:

1. Screenshots the running page (localhost)
2. Sends to Claude Vision for evaluation
3. Injects fix instructions if quality is below threshold

This is zero-cost when no frontend files exist (the gate auto-skips).
When it does run, it costs ~$0.01-0.02 per evaluation.

Used by: executor.py (called alongside mid_validator gates)
Depends on: hands/tools/browser.py, hands/visual_evaluator.py
"""

import os
import subprocess
import time

from hands.visual_evaluator import (
    VISUAL_ACCEPT_THRESHOLD,
    VISUAL_FIX_THRESHOLD,
    evaluate_screenshot,
    generate_fix_instructions,
    save_screenshot_log,
)

# File extensions that indicate a frontend project
_FRONTEND_EXTENSIONS = {".tsx", ".jsx", ".html", ".vue", ".svelte", ".css", ".scss"}

# Files that indicate a dev server can be started
_DEV_SERVER_INDICATORS = {"package.json", "vite.config.ts", "vite.config.js",
                          "next.config.js", "next.config.ts", "next.config.mjs",
                          "webpack.config.js", "nuxt.config.ts"}

# Minimum number of frontend files before triggering visual gate
_MIN_FRONTEND_FILES = 2

# How long to wait for dev server to start (seconds)
_DEV_SERVER_STARTUP_WAIT = 8

# Common dev server ports to check
_DEV_SERVER_PORTS = [3000, 5173, 8080, 4321, 3001]


class VisualGate:
    """
    Mid-build visual quality gate for frontend builds.
    
    Integrates with the executor's gate system. Call `should_check()`
    after each step to determine if a visual check is warranted,
    then `run_check()` to perform it.
    
    Usage in executor:
        visual_gate = VisualGate(workspace_dir, domain)
        
        # After each step:
        if visual_gate.should_check(step_num, all_artifacts):
            visual_correction = visual_gate.run_check(task_id="build_xyz")
            if visual_correction:
                # Inject into executor conversation
                result_text += visual_correction
    """
    
    def __init__(
        self,
        workspace_dir: str,
        domain: str = "general",
        context: str = "",
        page_type: str = "app",
        enable: bool = True,
    ):
        self.workspace_dir = workspace_dir
        self.domain = domain
        self.context = context
        self.page_type = page_type
        self.enabled = enable
        
        self._check_count = 0           # How many visual checks we've done
        self._max_checks = 3            # Max visual checks per execution
        self._last_check_step = 0       # Last step we checked at
        self._min_step_gap = 3          # Min steps between visual checks
        self._dev_server_proc = None    # Dev server subprocess (if we started one)
        self._dev_server_url = None     # URL of running dev server
        self._frontend_files_seen = 0   # Count of frontend files in artifacts
    
    def should_check(self, step_num: int, artifacts: list[str]) -> bool:
        """
        Determine if a visual check should run after this step.
        
        Returns True when:
        - Visual checks are enabled and we haven't hit the max
        - Enough frontend files exist in the artifacts
        - Sufficient steps have passed since last check
        """
        if not self.enabled:
            return False
        
        if self._check_count >= self._max_checks:
            return False
        
        if step_num - self._last_check_step < self._min_step_gap:
            return False
        
        # Count frontend files in artifacts
        frontend_count = sum(
            1 for a in artifacts
            if os.path.splitext(a)[1].lower() in _FRONTEND_EXTENSIONS
        )
        
        # Only trigger if we have new frontend files since last check
        if frontend_count <= self._frontend_files_seen:
            return False
        
        if frontend_count < _MIN_FRONTEND_FILES:
            return False
        
        self._frontend_files_seen = frontend_count
        return True
    
    def run_check(
        self,
        task_id: str = "build",
        iteration: int = 0,
    ) -> str:
        """
        Run a visual check: screenshot → evaluate → return fix instructions.
        
        Returns:
            Empty string if passed or evaluation failed.
            Fix instruction string if issues were found.
        """
        self._check_count += 1
        
        # Find or start a dev server
        url = self._find_dev_server()
        if not url:
            url = self._start_dev_server()
        
        if not url:
            # No dev server available — skip silently
            return ""
        
        # Take screenshot
        try:
            from hands.tools.browser import BrowserTool
            browser = BrowserTool()
            result = browser.execute(
                action="screenshot",
                url=url,
                viewport="desktop",
                full_page=False,
            )
            
            if not result.success or not result.metadata.get("base64_image"):
                print(f"           [VISUAL] Screenshot failed: {result.error}")
                return ""
            
            base64_image = result.metadata["base64_image"]
        except Exception as e:
            print(f"           [VISUAL] Browser error: {e}")
            return ""
        
        # Evaluate with Claude Vision
        try:
            eval_result = evaluate_screenshot(
                base64_image=base64_image,
                context=self.context,
                page_type=self.page_type,
                viewport="desktop",
            )
        except Exception as e:
            print(f"           [VISUAL] Evaluation error: {e}")
            return ""
        
        score = eval_result.get("score", 0)
        issues = eval_result.get("issues", [])
        cost = eval_result.get("cost", 0)
        
        # Save screenshot + evaluation for audit trail
        try:
            save_screenshot_log(
                domain=self.domain,
                task_id=task_id,
                phase=f"step_{self._last_check_step}",
                base64_image=base64_image,
                evaluation=eval_result,
                iteration=iteration,
            )
        except Exception:
            pass
        
        print(f"           [VISUAL] Score: {score}/10 (${cost:.4f})")
        
        if score >= VISUAL_ACCEPT_THRESHOLD:
            print(f"           [VISUAL] ✓ Passed visual check")
            return ""
        
        if score >= VISUAL_FIX_THRESHOLD:
            # Needs fixes — generate instructions
            fix_text = generate_fix_instructions(issues)
            if fix_text:
                print(f"           [VISUAL] {len(issues)} issue(s) — injecting fix instructions")
                return f"\n\n🎨 VISUAL QUALITY CHECK (score {score}/10):\n{fix_text}"
        else:
            # Below fix threshold — critical issues
            fix_text = generate_fix_instructions(issues)
            impression = eval_result.get("overall_impression", "")
            print(f"           [VISUAL] ⚠ Low score ({score}/10) — {impression[:80]}")
            return (
                f"\n\n🚨 VISUAL QUALITY ALERT (score {score}/10):\n"
                f"{impression}\n\n{fix_text}\n"
                f"IMPORTANT: Fix critical visual issues before proceeding."
            )
        
        return ""
    
    def _find_dev_server(self) -> str | None:
        """Check if a dev server is already running on common ports."""
        if self._dev_server_url:
            # Verify it's still alive
            try:
                import urllib.request
                urllib.request.urlopen(self._dev_server_url, timeout=3)
                return self._dev_server_url
            except Exception:
                self._dev_server_url = None
        
        for port in _DEV_SERVER_PORTS:
            url = f"http://localhost:{port}"
            try:
                import urllib.request
                urllib.request.urlopen(url, timeout=2)
                self._dev_server_url = url
                return url
            except Exception:
                continue
        
        return None
    
    def _start_dev_server(self) -> str | None:
        """
        Try to start a dev server in the workspace directory.
        
        Looks for package.json with a "dev" script. If found, runs `npm run dev`
        and waits briefly for it to start.
        """
        if not self.workspace_dir or not os.path.isdir(self.workspace_dir):
            return None
        
        # Check for package.json with dev script
        pkg_path = os.path.join(self.workspace_dir, "package.json")
        if not os.path.exists(pkg_path):
            # Check subdirectories (Next.js projects may be in a subfolder)
            for sub in os.listdir(self.workspace_dir):
                sub_pkg = os.path.join(self.workspace_dir, sub, "package.json")
                if os.path.exists(sub_pkg):
                    pkg_path = sub_pkg
                    break
            else:
                return None
        
        try:
            import json as json_mod
            with open(pkg_path) as f:
                pkg = json_mod.load(f)
        except Exception:
            return None
        
        scripts = pkg.get("scripts", {})
        if "dev" not in scripts:
            return None
        
        # Start the dev server
        pkg_dir = os.path.dirname(pkg_path)
        try:
            self._dev_server_proc = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=pkg_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            return None
        
        # Wait for it to start
        time.sleep(_DEV_SERVER_STARTUP_WAIT)
        
        # Check which port it landed on
        return self._find_dev_server()
    
    def cleanup(self):
        """Kill dev server if we started one."""
        if self._dev_server_proc:
            try:
                import signal
                os.killpg(os.getpgid(self._dev_server_proc.pid), signal.SIGTERM)
            except Exception:
                try:
                    self._dev_server_proc.kill()
                except Exception:
                    pass
            self._dev_server_proc = None
        
        # Close browser session
        try:
            from hands.tools.browser import BrowserSession
            BrowserSession.close()
        except Exception:
            pass
    
    def get_summary(self) -> dict:
        """Return summary of visual gate activity for the execution report."""
        return {
            "visual_checks_run": self._check_count,
            "max_checks": self._max_checks,
            "frontend_files_seen": self._frontend_files_seen,
            "dev_server_url": self._dev_server_url,
        }
