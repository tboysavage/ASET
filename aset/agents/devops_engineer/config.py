# aset/config/devops_config.py

from dataclasses import dataclass

@dataclass
class DevOpsRepairConfig:
    max_iterations: int = 10         # how many repair cycles before giving up
    reinstall_on_change: bool = True
    run_import_check: bool = True
    run_uvicorn_check: bool = False  # optional later
    sleep_between_iterations: int = 15   # <-- new (seconds)
    transient_retry_delay: int = 10      # <-- optional retry if 503/429
