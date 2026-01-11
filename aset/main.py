from dotenv import load_dotenv
load_dotenv()

import argparse
from pathlib import Path

from aset.orchestrator.orchestrator import Orchestrator, OrchestratorConfig
from aset.utils.logger import get_logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Autonomous Software Team — build a product from a natural language request."
    )
    parser.add_argument(
        "--prompt",
        type=str,
        required=True,
        help="User request, e.g. 'I want a software to track employee work hours.'",
    )
    parser.add_argument(
        "--project-dir",
        type=str,
        default=".",
        help="Root directory for this project run (default: current directory).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logger = get_logger("main")

    project_root = Path(args.project_dir).resolve()
    logger.info("Using project root: %s", project_root)

    cfg = OrchestratorConfig(project_root=project_root)
    orchestrator = Orchestrator(cfg)

    state = orchestrator.run(user_prompt=args.prompt)
    logger.info("Done. Clarified spec:\n%s", state.spec.clarified_spec)


if __name__ == "__main__":
    main()
