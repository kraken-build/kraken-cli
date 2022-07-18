""" Inspect a Python environment for all installed packages. """

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from typing import Any

from nr.python.environment.distributions import Distribution, get_distributions

from kraken.cli import __version__


@dataclasses.dataclass
class EnvironmentState:
    python_version: str
    kraken_cli_version: str
    distributions: dict[str, Distribution]

    @staticmethod
    def from_json(data: dict[str, Any]) -> EnvironmentState:
        return EnvironmentState(
            python_version=data["python_version"],
            kraken_cli_version=data["kraken_cli_version"],
            distributions={k: Distribution.from_json(v) for k, v in data["distributions"].items()},
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "python_version": self.python_version,
            "kraken_cli_version": self.kraken_cli_version,
            "distributions": {k: Distribution.to_json(v) for k, v in self.distributions.items()},
        }


def get_environment_state() -> EnvironmentState:
    return EnvironmentState(
        python_version=sys.version,
        kraken_cli_version=__version__,
        distributions=get_distributions(),
    )


def get_environment_state_of_interpreter(python_bin: str) -> EnvironmentState:
    """Retrieves the environment state of another Python environment. This environment must have Kraken-CLI
    and its dependencies installed."""

    code = (
        f"import json; from {__name__} import get_environment_state; "
        "print(json.dumps(get_environment_state().to_json()))"
    )
    return EnvironmentState.from_json(json.loads(subprocess.check_output([python_bin, "-c", code]).decode()))
