""" Provides the :class:`EnvironmentManager` which ensures the build environment is up to date and allows for locking
the requirements in place."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess as sp
import sys
from pathlib import Path
from typing import Any, Iterable, cast

from kraken.cli import __version__

from .lockfile import Lockfile, LockfileMetadata
from .project import ProjectInterface
from .requirements import RequirementSpec

#: This environment variable can be set to "1" to install the Kraken CLI package as a development dependency
#: when bootstrapping a build environment. This is relevant when developing Kraken CLI itself.
ENV_KRAKEN_DEVELOP = "KRAKEN_DEVELOP"

#: This environment variable can be set to "0" to disable using a build environment at all.
ENV_KRAKEN_MANAGED = "KRAKEN_MANAGED"

KRAKEN_REQUIREMENTS_FILE = ".kraken.requirements"
KRAKEN_LOCK_FILE = ".kraken.lock"
KRAKEN_ENV_HASH_FILE = ".kraken-env-hash"
logger = logging.getLogger(__name__)


def _hash_strings(strings: Iterable[str]) -> str:
    return hashlib.md5(":".join(strings).encode()).hexdigest()


class EnvironmentManager:
    """This class manages a virtual environment that is used for executing a Kraken build.

    :param env_dir: The directory in which the virtual environment should be installed to.
    :param project: Provide project-specific capabilities such as reading/writing lock files and finding
        the requirement spec.
    """

    #: We use this file inside the environment directory to keep track of the hash of the requriements that
    #: were used to install the environment.
    HASH_FILE = Path(".kraken-env-hash")

    def __init__(self, env_dir: Path, project: ProjectInterface) -> None:
        self.env_dir = env_dir
        self.project = project
        self._requirements: RequirementSpec | None = None

    def get_implied_requirements(self) -> list[str]:
        """Returns a list of requirements that are implied for build environments managed by Kraken CLI."""

        if os.getenv(ENV_KRAKEN_DEVELOP) == "1":
            logger.info("encountered %s=1, implying local development dependency for kraken-cli", ENV_KRAKEN_DEVELOP)
            import kraken.cli

            init_path = Path(kraken.cli.__file__).resolve()
            kraken_path = init_path.parent.parent.parent
            project_root = kraken_path.parent
            pyproject = project_root / "pyproject.toml"
            if not pyproject.is_file():
                raise RuntimeError(
                    f"{ENV_KRAKEN_DEVELOP}=1, however kraken-cli does not seem to be installed in "
                    'development mode (expected kraken-cli\'s pyproject.toml at "%s")' % pyproject
                )

            # TODO (@NiklasRosenstein): It would be nice if we could tell Pip to install kraken-cli in
            #       development mode, but `pip install -e DIR` does not currently work for projects using
            #       Poetry.
            return [f"kraken-cli@{project_root}"]

        # Determine the next Kraken CLI release that may ship with breaking changes.
        version: tuple[int, int, int] = cast(Any, tuple(map(int, __version__.split("."))))
        if version[0] == 0:
            # While we're in 0 major land, let's assume potential breaks with the next minor version.
            breaking_version = f"0.{version[1]+1}.0"
        else:
            breaking_version = f"{version[0]}.0.0"

        return [f"kraken-cli>={__version__},<{breaking_version}"]

    def get_full_requirements(self) -> RequirementSpec:
        """Returns the full requirements, including implied ones for kraken-cli."""

        if self._requirements is None:
            self._requirements = self.project.get_requirement_spec()
            self._requirements.add_requirements(self.get_implied_requirements())
        return self._requirements

    def calculate_requirements_hash(self) -> str:
        return _hash_strings(self.get_full_requirements().to_args())

    def calculate_lockfile_hash(self) -> str | None:
        lockfile = self.project.read_lock_file()
        if lockfile:
            return _hash_strings(lockfile.requirements.to_args())
        return None

    def read_environment_hash(self) -> str | None:
        """Reads the environment hash that describes the requirements that were used to install the environment."""

        file = self.env_dir / self.HASH_FILE
        return file.read_text().strip() if file.is_file() else None

    def write_environment_hash(self, hash: str) -> None:
        """Writes the environment hash."""

        file = self.env_dir / self.HASH_FILE
        file.write_text(hash)

    def get_program(self, name: str) -> Path:
        if os.name == "nt":
            prefix = self.env_dir / "Scripts"
            suffix = ".exe"
        else:
            prefix = self.env_dir / "bin"
            suffix = ""
        return prefix / (name + suffix)

    def exists(self) -> bool:
        return self.env_dir.is_dir()

    def destroy(self) -> None:
        """Removes the virtual environment if it exists."""

        if not self.env_dir.is_dir():
            return

        # Sanity check if this is really a virtual environment.
        # TODO (@NiklasRosenstein): On Windows this will have to be Scripts/python.exe
        python_bin = self.get_program("python")
        if not python_bin.exists():
            raise RuntimeError(
                f"would remove directory {self.env_dir} but after a sanity check this doesn't look "
                "like a virtual environment!"
            )

        logger.info("destroying virtual environment %s", self.env_dir)
        shutil.rmtree(self.env_dir)

    def check_outdated(self) -> bool:
        expected_hash = self.calculate_requirements_hash()
        got_hash = self.read_environment_hash()

        if expected_hash != got_hash:
            logger.info(
                "environment hash mismatch (expected: %s, got: %s)",
                expected_hash,
                got_hash,
            )
            return True

        return False

    def install(self, update: bool = False) -> None:
        """Ensure that the virtual environment is up to date."""

        verb = "updating" if self.env_dir.exists() else "creating"

        lock_file = self.project.read_lock_file()
        if lock_file and not update:
            if self.calculate_lockfile_hash() != self.read_environment_hash():
                logger.warning("lock file appears to be out dated, your environment may not contain what you expect")
                logger.warning("  run `kraken env --update --lock` to update the lock file")
            requirements = lock_file.to_args()
            logger.info("%s virtual %s environment from lock file", verb, self.env_dir)
        else:
            requirements = self.get_full_requirements().to_args()
            logger.info("%s virtual %s environment from requirements %s", verb, self.env_dir, requirements)

        env = os.environ.copy()
        env.pop("VIRTUAL_ENV", None)
        env.pop("VIRTUAL_ENV_PROMPT", None)

        command = [sys.executable, "-m", "venv", str(self.env_dir)]
        sp.check_call(command, env=env)
        pip = self.get_program("pip")
        command = [str(pip), "install"] + requirements
        if update:
            command += ["--upgrade"]
        sp.check_call(command, env=env)
        self.write_environment_hash(self.calculate_requirements_hash())

    def are_we_in(self) -> bool:
        """Returns `True` if we're inside the environment managed here."""

        if os.getenv(ENV_KRAKEN_MANAGED) == "0":
            logger.info("encountered %s=0, assuming current environment as the build environment", ENV_KRAKEN_MANAGED)
            return True

        try:
            Path(sys.executable).relative_to(self.env_dir)
        except ValueError:
            return False
        else:
            return True

    def dispatch(self, argv: list[str]) -> int:
        """Dispatch to the kraken-cli inside the environment."""

        logger.info("dispatching to virtual environment %s", self.env_dir)
        kraken_cli = self.get_program("kraken")
        env = os.environ.copy()
        env[ENV_KRAKEN_MANAGED] = "0"
        return sp.call([str(kraken_cli)] + argv, env=env)

    def lock(self) -> None:
        """Locks all immediate and transitive dependencies in the virtual environment and writes it into
        the lock file."""

        from .inspect import get_environment_state_of_interpreter

        env = get_environment_state_of_interpreter(str(self.get_program("python")))

        # TODO (@NiklasRosenstein): We should keep only the distributions that are required by the initial
        #       requirement set, and ignore any distributions that were manually added into the build
        #       environment (and warn about them).

        metadata = LockfileMetadata.new()
        metadata.kraken_cli_version = f"{env.kraken_cli_version} (instrumented by {metadata.kraken_cli_version})"
        metadata.python_version = f"{env.python_version} (instrumented by {env.python_version})"
        lockfile = Lockfile(
            metadata,
            self.get_full_requirements(),
            {dist.name: dist.version for dist in env.distributions.values()},
        )
        self.project.write_lock_file(lockfile)
