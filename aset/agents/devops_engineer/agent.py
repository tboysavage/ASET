from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List
import time

from aset.agents.shared.base_agent import BaseAgent
from aset.llm.router.llm_router import LLMRouter
from aset.llm.router.llm_router import LLMRequest
from aset.project_state.state_store import ProjectState
from aset.utils.file_ops import ensure_dir
from aset.utils.file_bundle import parse_file_bundle, write_file_bundle, FileBundleParseError
from .config import DevOpsRepairConfig


class DevOpsEngineerAgent(BaseAgent):
    """
    DevOps repair loop:
    - creates/uses venv
    - pip install -r requirements.txt
    - runs check_backend.py (and optionally uvicorn)
    - on failure, asks LLM for fixes (in FILE_BUNDLE patch format)
    - applies patches
    - retries, up to max_iterations
    """

    def __init__(self, llm_router: LLMRouter, project_root: Path, cfg: DevOpsRepairConfig | None = None) -> None:
        super().__init__(llm_router)
        self.project_root = project_root
        self.cfg = cfg or DevOpsRepairConfig()
        self._prompt_path = Path(__file__).with_name("prompt.md")
        self._system_prompt = self._prompt_path.read_text()

    # ---------- public entrypoint ----------

    def run(self, state: ProjectState) -> ProjectState:
        """
        DevOps repair loop:
        - ensures venv
        - installs requirements
        - runs backend checks
        - on failure, asks LLM for patches and applies them
        - retries up to max_iterations
        """
        backend_root = ensure_dir(self.project_root / "project_state" / "codebase" / "backend")
        devops_dir = ensure_dir(self.project_root / "project_state" / "devops")
        venv_dir = backend_root / ".venv"

        # Grab spec / architecture / raw backend text once for use in repairs
        spec_text = ""
        arch_text = ""
        try:
            if getattr(state, "spec", None) is not None:
                spec_text = getattr(state.spec, "clarified_spec", "") or ""
        except Exception:
            pass

        try:
            if getattr(state, "architecture", None) is not None:
                arch_text = getattr(state.architecture, "content", "") or ""
        except Exception:
            pass

        raw_backend_path = self.project_root / "project_state" / "codebase" / "backend_generation.txt"
        raw_backend = raw_backend_path.read_text() if raw_backend_path.exists() else ""

        for iteration in range(1, self.cfg.max_iterations + 1):
            self.logger.info("DevOps iteration %d/%d", iteration, self.cfg.max_iterations)

            # ⏱️ Throttle between iterations to avoid hammering Gemini
            if iteration > 1 and self.cfg.sleep_between_iterations > 0:
                self.logger.info(
                    "Sleeping %d seconds before starting iteration %d",
                    self.cfg.sleep_between_iterations,
                    iteration,
                )
                time.sleep(self.cfg.sleep_between_iterations)

            # 1) Install deps
            install_ok, install_log = self._install_dependencies(backend_root, venv_dir)
            (devops_dir / f"install_{iteration}.log").write_text(install_log)

            if not install_ok:
                self.logger.warning("Install failed on iteration %d, attempting repair.", iteration)
                self._attempt_repair(
                    backend_root=backend_root,
                    devops_dir=devops_dir,
                    iteration=iteration,
                    phase="install",
                    logs=install_log,
                    spec_text=spec_text,
                    arch_text=arch_text,
                    raw_backend=raw_backend,
                )
                # go to next iteration AFTER repair
                continue

            # 2) Run checks (structure + import + optional uvicorn)
            checks_ok, checks_log = self._run_backend_checks(backend_root, venv_dir)
            (devops_dir / f"checks_{iteration}.log").write_text(checks_log)

            if checks_ok:
                self.logger.info("DevOps checks passed on iteration %d", iteration)
                (devops_dir / "status.txt").write_text(f"SUCCESS on iteration {iteration}\n")
                return state

            self.logger.warning("DevOps checks failed on iteration %d, attempting repair.", iteration)
            self._attempt_repair(
                backend_root=backend_root,
                devops_dir=devops_dir,
                iteration=iteration,
                phase="checks",
                logs=checks_log,
                spec_text=spec_text,
                arch_text=arch_text,
                raw_backend=raw_backend,
            )
            # loop continues; next iteration will re-install / re-check

        # If we exit the loop, all attempts failed
        self.logger.error("DevOps failed after %d iterations.", self.cfg.max_iterations)
        (devops_dir / "status.txt").write_text(f"FAILED after {self.cfg.max_iterations} iterations\n")
        return state


    # ---------- helpers ----------

    def _install_dependencies(self, backend_root: Path, venv_dir: Path) -> tuple[bool, str]:
        req_file = backend_root / "requirements.txt"
        lines: List[str] = []

        def run_cmd(cmd: List[str], cwd: Path) -> int:
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            stdout, _ = proc.communicate()
            lines.append(f"$ {' '.join(cmd)}\n{stdout}\n")
            return proc.returncode

        # create venv if needed
        if not venv_dir.exists():
            code = run_cmd([sys.executable, "-m", "venv", str(venv_dir)], backend_root)
            if code != 0:
                return False, "".join(lines)

        python_bin = venv_dir / "bin" / "python"
        pip_bin = venv_dir / "bin" / "pip"
        if sys.platform.startswith("win"):
            python_bin = venv_dir / "Scripts" / "python.exe"
            pip_bin = venv_dir / "Scripts" / "pip.exe"

        # install dependencies
        if req_file.exists():
            code = run_cmd([str(pip_bin), "install", "-r", str(req_file)], backend_root)
            return code == 0, "".join(lines)
        else:
            lines.append("No requirements.txt found; skipping pip install.\n")
            return True, "".join(lines)

        lines: List[str] = []

        def run_cmd(cmd: List[str]) -> int:
            proc = subprocess.Popen(
                cmd,
                cwd=str(backend_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            stdout, _ = proc.communicate()
            lines.append(f"$ {' '.join(cmd)}\n{stdout}\n")
            return proc.returncode

        python_bin = venv_dir / "bin" / "python"
        if sys.platform.startswith("win"):
            python_bin = venv_dir / "Scripts" / "python.exe"

        # 🔴 NEW: structural checks
        py_files = list(backend_root.rglob("*.py"))
        if not py_files:
            lines.append("No Python source files found in backend; backend not generated.\n")
            return False, "".join(lines)

        required = ["run_backend.py", "app/main.py", "check_backend.py"]
        missing = [p for p in required if not (backend_root / p).exists()]
        if missing:
            lines.append(f"Missing required files: {', '.join(missing)}\n")
            return False, "".join(lines)

        ok = True

        # 1) import check
        check_script = backend_root / "check_backend.py"
        if self.cfg.run_import_check and check_script.exists():
            code = run_cmd([str(python_bin), str(check_script)])
            ok = ok and (code == 0)

        # 2) (optional uvicorn dry-run later)

        return ok, "".join(lines)


    def _attempt_repair(
        self,
        backend_root: Path,
        devops_dir: Path,
        iteration: int,
        phase: str,
        logs: str,
        spec_text: str = "",
        arch_text: str = "",
        raw_backend: str = "",
    ) -> None:
        """
        Ask the LLM to generate a FILE_BUNDLE patch to fix the backend.
        This must NEVER crash the overall orchestration.
        """

        # Build file tree summary BEFORE calling the LLM
        tree_lines = []
        try:
            for path in sorted(backend_root.rglob("*")):
                rel = path.relative_to(backend_root)
                if path.is_dir():
                    tree_lines.append(f"[D] {rel}")
                else:
                    tree_lines.append(f"[F] {rel}")
        except Exception as e:
            # If the tree fails for some reason, still proceed with what we have
            self.logger.warning(
                "Failed to build backend tree for DevOps repair: %s", e
            )
        backend_tree = "\n".join(tree_lines)

        # Full user prompt with context
        user_prompt = f"""
You are the DevOps / platform engineer in an autonomous software engineering team.

We have a generated Python backend project that is currently failing DevOps checks.

Phase: {phase}  (either "install" or "checks")
Iteration: {iteration}

CLARIFIED SPEC:
---------------- SPEC START ----------------
{spec_text}
---------------- SPEC END ------------------

ARCHITECTURE:
---------------- ARCH START ----------------
{arch_text}
---------------- ARCH END ------------------

RAW BACKEND GENERATION (may be prose or partial code; treat as hints only):
---------------- BACKEND GEN START ---------
{raw_backend[:8000]}
---------------- BACKEND GEN END -----------

Current backend project tree (relative to backend/):
---------------- TREE START ----------------
{backend_tree}
---------------- TREE END ------------------

Logs from the failing step:
---------------- LOGS START -----------------
{logs}
---------------- LOGS END -------------------

Your job now:

- Diagnose why the backend cannot install or pass checks.
- Produce a minimal set of file changes that make the backend:
  - installable (pip install -r requirements.txt inside its venv), and
  - runnable, with a FastAPI app entrypoint for Uvicorn (e.g. app.main:app).

You MAY:
- Create or replace files such as:
  - backend/requirements.txt
  - backend/run_backend.py
  - backend/check_backend.py
  - backend/app/__init__.py
  - backend/app/main.py
  - backend/app/models.py
  - backend/app/schemas.py
  - backend/app/deps.py
  - backend/app/api/routes.py
- Adjust imports, module paths, DB URLs, etc.

Stack preference:
- Prefer FastAPI + SQLModel + SQLite by default, with support for DB_URL env var override.
- Only switch away from FastAPI if it is clearly unsalvageable.

OUTPUT FORMAT (STRICT):

1) Start with:
---FILE_MAP_START---
<one file path per line for files you want to CREATE or REPLACE, e.g.>
backend/requirements.txt
backend/run_backend.py
backend/app/main.py
...
---FILE_MAP_END---

2) For each file listed in the file map, emit:
---FILE_START backend/path/to/file.ext---
<full file content>
---FILE_END backend/path/to/file.ext---

Rules:
- Include ONLY files under backend/.
- Do NOT include any explanations or commentary outside the FILE_MAP and FILE_START/FILE_END blocks.
"""

        # 1) Call LLM to get a FILE_BUNDLE patch
        try:
            patch_text = self._call_llm(
                system_prompt=self._system_prompt,
                user_prompt=user_prompt,
                role="devops",
            )
        except Exception as exc:
            # Very important: do NOT crash the orchestrator on quota/overload/etc.
            error_path = devops_dir / f"patch_error_{phase}_{iteration}.log"
            try:
                error_path.write_text(
                    f"DevOps LLM call failed during phase='{phase}' on iteration {iteration}:\n{exc}\n"
                )
            except Exception:
                # best-effort logging
                pass
            self.logger.error(
                "DevOps LLM call failed during phase='%s' iteration %d; "
                "skipping further repair this iteration: %s",
                phase,
                iteration,
                exc,
            )
            return

        # Always save the raw patch text for debugging
        try:
            (devops_dir / f"patch_raw_{phase}_{iteration}.txt").write_text(patch_text)
        except Exception:
            pass

        # 2) Parse FILE_BUNDLE
        try:
            bundle = parse_file_bundle(patch_text)
        except FileBundleParseError as e:
            invalid_path = devops_dir / f"invalid_patch_{phase}_{iteration}.txt"
            try:
                invalid_path.write_text(patch_text)
            except Exception:
                pass
            self.logger.error(
                "DevOps patch was not in valid FILE_BUNDLE format during phase='%s' "
                "on iteration %d: %s",
                phase,
                iteration,
                e,
            )
            return
    def _run_backend_checks(self, backend_root: Path, venv_dir: Path) -> tuple[bool, str]:
        """
        DevOps validation step:
        1) ensure backend exists structurally
        2) import check via check_backend.py
        3) REAL runtime check: run `python run_backend.py --check`
        """

        lines: List[str] = []

        def run_cmd(cmd: List[str]) -> int:
            proc = subprocess.Popen(
                cmd,
                cwd=str(backend_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            stdout, _ = proc.communicate()
            lines.append(f"$ {' '.join(cmd)}\n{stdout}\n")
            return proc.returncode

        python_bin = venv_dir / ("Scripts/python.exe" if sys.platform.startswith("win") else "bin/python")

        # --- Structural checks ---
        py_files = list(backend_root.rglob("*.py"))
        if not py_files:
            return False, "No Python source files found in backend.\n"

        required = ["run_backend.py", "app/main.py", "check_backend.py"]
        missing = [p for p in required if not (backend_root / p).exists()]
        if missing:
            return False, f"Missing required files: {', '.join(missing)}\n"

        ok = True

        # --- 1) Import check ---
        check_script = backend_root / "check_backend.py"
        if self.cfg.run_import_check and check_script.exists():
            import_code = run_cmd([str(python_bin), str(check_script)])
            ok = ok and (import_code == 0)

        # --- 2) Runtime startup check ---
        if self.cfg.run_uvicorn_check:
            lines.append("=== Running backend startup check ===\n")
            run_code = run_cmd([str(python_bin), "run_backend.py", "--check"])
            ok = ok and (run_code == 0)

        return ok, "".join(lines)

