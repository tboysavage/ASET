from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from core.llm import RoutedLLM, VertexLLM, VertexConfig, OllamaLLM, OllamaConfig
from core.protocol import ProjectBlueprint
from agents.architect import ArchitectAgent
from agents.logic_coder import LogicCoderAgent
from agents.ui_composer import UIComposerAgent
from agents.librarian import LibrarianAgent
from agents.scribe import ScribeAgent


ROOT = Path(__file__).parent
WORKSPACE = ROOT / "workspace"


def load_config() -> dict:
    cfg_path = ROOT / "config.yaml"
    if cfg_path.exists():
        return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return {}


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def build_llm_from_config(cfg: dict) -> RoutedLLM:
    llm_cfg = (cfg.get("llm") or {})
    router_cfg = (llm_cfg.get("router") or {})
    vertex_cfg = (llm_cfg.get("vertex") or {})
    ollama_cfg = (llm_cfg.get("ollama") or {})

    vertex_project = vertex_cfg.get("project")
    if not vertex_project or not isinstance(vertex_project, str):
        raise ValueError("config.yaml missing llm.vertex.project (set to your GCP project id)")

    vertex = VertexLLM(
        VertexConfig(
            project=vertex_project,
            location=vertex_cfg.get("location", "us-central1"),
            model=vertex_cfg.get("model", "gemini-2.5-pro"),
            temperature=float(vertex_cfg.get("temperature", 0.2)),
        )
    )

    ollama = OllamaLLM(
        OllamaConfig(
            base_url=ollama_cfg.get("base_url", "http://127.0.0.1:11434"),
            model=ollama_cfg.get("model", "qwen2.5-coder:3b"),
            temperature=float(ollama_cfg.get("temperature", 0.2)),
            timeout_seconds=int(ollama_cfg.get("timeout_seconds", 300)),
        )
    )

    llm = RoutedLLM(
        providers={"vertex": vertex, "ollama": ollama},
        routes=router_cfg.get("routes", {}),
        default=router_cfg.get("default", "ollama"),
    )
    return llm


def validate_generated_logic(project_dir: Path, blueprint: ProjectBlueprint) -> None:
    """
    Hard gate: ensure logic.py imports AND contains all fragment functions.

    This prevents the common failure mode where logic.py is incomplete or crashes
    during import, causing Streamlit ImportError later.
    """
    expected = [f.id for f in (blueprint.logic_fragments or [])]
    expected_json = json.dumps(expected)

    # Run a separate Python process so we get clean import semantics.
    # cwd=project_dir ensures "import logic" imports the generated logic.py.
    script = f"""
import json
import sys

expected = json.loads({expected_json!r})

try:
    import logic
except Exception as e:
    print("FAILED_TO_IMPORT_LOGIC")
    print(type(e).__name__ + ":", str(e))
    raise

missing = [name for name in expected if not hasattr(logic, name)]
if missing:
    print("MISSING_FRAGMENT_FUNCTIONS")
    for m in missing:
        print(m)
    raise SystemExit(2)

print("LOGIC_OK")
"""

    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()

        msg_lines = [
            "❌ Generated logic.py failed validation.",
            f"Project: {project_dir}",
            "",
            "STDOUT:",
            stdout or "(empty)",
            "",
            "STDERR:",
            stderr or "(empty)",
            "",
            "What this means:",
            "- Either logic.py failed to import (syntax error, missing dependency, runtime error), OR",
            "- logic.py imported but is missing one or more fragment functions declared in blueprint.json.",
            "",
            "Fix path:",
            "1) Inspect logic.py in the generated folder.",
            "2) Ensure dependencies are correct (requirements.txt) and code generation produced the expected defs.",
        ]
        raise RuntimeError("\n".join(msg_lines))


def build_project(prompt: str) -> Path:
    cfg = load_config()
    verbose = bool(cfg.get("verbose", True))

    llm = build_llm_from_config(cfg)

    architect = ArchitectAgent(llm, verbose=verbose)
    coder = LogicCoderAgent(llm, verbose=verbose)
    ui = UIComposerAgent(llm, verbose=verbose)
    librarian = LibrarianAgent(llm, verbose=verbose)
    scribe = ScribeAgent(llm, verbose=verbose)

    # Phase 1: Architecture
    blueprint: ProjectBlueprint = architect.execute(prompt)

    project_dir = WORKSPACE / blueprint.app_name.replace(" ", "_").lower()
    ensure_dir(project_dir)

    write_json(project_dir / "blueprint.json", blueprint.model_dump())

    # Phase 2: Logic Fabrication
    logic_parts = ["# Generated by ASET\n\n"]
    for frag in blueprint.logic_fragments:
        code = coder.execute(frag)
        logic_parts.append(code)
        logic_parts.append("\n\n")

    write_text(project_dir / "logic.py", "".join(logic_parts))

    # 🔒 Hard gate: validate logic.py imports and contains all fragment functions
    validate_generated_logic(project_dir, blueprint)

    # Phase 3: UI Assembly
    app_py = ui.execute(blueprint)
    write_text(project_dir / "app.py", app_py)

    # Phase 4: Packaging
    reqs = librarian.execute({"project_dir": str(project_dir)})
    write_text(project_dir / "requirements.txt", reqs)

    readme = scribe.execute(blueprint)
    write_text(project_dir / "README.md", readme)

    return project_dir


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python main.py "Create a Stock Tracker"')
        sys.exit(1)

    prompt = " ".join(sys.argv[1:]).strip()
    out_dir = build_project(prompt)
    print(f"\n✅ Generated project at: {out_dir}")
    print(f"Next:\n  cd {out_dir}\n  pip install -r requirements.txt\n  streamlit run app.py\n")


if __name__ == "__main__":
    main()
