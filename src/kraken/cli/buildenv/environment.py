""" Provides the :class:`EnvironmentManager` which ensures the build environment is up to date and allows for locking
the requirements in place."""

from __future__ import annotations

import contextlib
import dataclasses
import datetime
import logging
import os
import shutil
import subprocess as sp
import sys
from pathlib import Path
from typing import Iterator, TextIO

from packaging.requirements import Requirement

from .inspect import get_environment_state_of_interpreter
from .lockfile import Lockfile, LockfileMetadata
from .requirements import RequirementSpec

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class CalculateLockfileResult:
    lockfile: Lockfile
    extra_distributions: set[str]


class BuildEnvironment:
    """Represents a separate Python environment that we install build time requirements into."""

    def __init__(self, project_path: Path, path: Path, verbosity: int) -> None:
        """
        :param project_path: The directory that relative paths should be assumed relative to.
        :param path: The directory at which the environment should be located.
        :param verbosity: 1 for showing Pip output, 2 for making Pip output verbose.
        """

        self._project_path = project_path
        self._path = path
        self._hash_file = path / ".hash"
        self._install_log_file = path / ".install-log"
        self._verbosity = verbosity

    @property
    def path(self) -> Path:
        return self._path

    @property
    def hash_file(self) -> Path:
        return self._hash_file

    @property
    def install_log_file(self) -> Path:
        return self._install_log_file

    @property
    def hash(self) -> str | None:
        """Returns the hash code of the environment."""

        if self._hash_file.exists():
            return self._hash_file.read_text().strip()
        return None

    @hash.setter
    def hash(self, value: str) -> None:
        """Writes the hash code of the environment."""

        self._hash_file.write_text(value)

    def exists(self) -> bool:
        """Returns `True` if the environment exists."""

        return self._path.is_dir()

    def create(self, from_python_bin: str | Path | None) -> None:
        """Create the build environment."""

        if from_python_bin is None:
            from_python_bin = sys.executable

        env = os.environ.copy()
        env.pop("VIRTUAL_ENV", None)
        env.pop("VIRTUAL_ENV_PROMPT", None)
        command = [str(sys.executable), "-m", "venv", str(self._path)]
        sp.check_call(command, env=env)

        # Install keyring such that Pip can look up credetials in the system keychain, and upgrade Pip.
        command = self._get_pip_command() + ["--upgrade", "pip", "keyring"]
        with self._open_logfile_and_print_delta_on_error() as fp:
            sp.check_call(command, env=env, stdout=fp, stderr=sp.STDOUT)

    def remove(self) -> None:
        """Remove the virtual environment."""

        if not self._path.is_dir():
            return

        # Sanity check if this is really a virtual environment.
        python_bin = self.get_program("python")
        if not python_bin.exists():
            raise RuntimeError(
                f"would remove directory {self._path} but after a sanity check this doesn't look "
                "like a virtual environment!"
            )

        shutil.rmtree(self._path)

    def get_program(self, name: str) -> Path:
        """Returns the path to a program in the virtual environment."""

        if os.name == "nt":
            prefix = self._path / "Scripts"
            suffix = ".exe"
        else:
            prefix = self._path / "bin"
            suffix = ""
        return prefix / (name + suffix)

    def install_requirements(self, requirements: RequirementSpec, upgrade: bool) -> None:
        """Install requirements into the environment using Pip.

        :param requirements: The requirements to install into the environment.
        :param upgrade: Pass the `--upgrade` flag to Pip.
        """

        command = self._get_pip_command() + requirements.to_args(self._project_path)
        if upgrade:
            command += ["--upgrade"]
        logger.info("%s", command)
        with self._open_logfile_and_print_delta_on_error() as fp:
            sp.check_call(command, stdout=fp, stderr=sp.STDOUT)
        self._install_pythonpath(requirements.pythonpath)

    def install_lockfile(self, lockfile: Lockfile) -> None:
        """Install requirements from a lockfile.

        :param lockfile: The lockfile to install from."""

        command = self._get_pip_command() + ["--upgrade"]
        command += lockfile.to_args(self._project_path)
        logger.info("%s", command)
        with self._open_logfile_and_print_delta_on_error() as fp:
            sp.check_call(command, stdout=fp, stderr=sp.STDOUT)
        self._install_pythonpath(lockfile.requirements.pythonpath)

    def _get_pip_command(self) -> list[str]:
        python = self.get_program("python")
        command = [str(python), "-m", "pip", "install", "--no-input"]
        if self._verbosity > 2:
            command += ["-vv"]
        elif self._verbosity > 1:
            command += ["-v"]
        return command

    def _install_pythonpath(self, pythonpath: list[str]) -> None:
        """Installs the given list of paths by placing a `.pth` file into the environment."""

        # TODO (@NiklasRosenstein): The path here might be different again on Windows.
        python = self.get_program("python")
        command = [str(python), "-c", "from sysconfig import get_path; print(get_path('purelib'))"]
        site_packages = Path(sp.check_output(command).decode().strip())
        pth_file = site_packages / "kraken-cli.pth"
        pth_file.write_text("\n".join(str((self._project_path / path).absolute()) for path in pythonpath))

    @contextlib.contextmanager
    def _open_logfile_and_print_delta_on_error(self) -> Iterator[TextIO]:
        """A context manager to open the environment log file and return it. If an error occurs inside the context
        manager, the delta (everything that was appended since the file was opened) will be printed to stderr."""

        if self._verbosity > 0:
            yield sys.stdout
            return

        with self._install_log_file.open("a") as fp:
            print(f"\n[{datetime.datetime.utcnow()} UTC]", file=fp, flush=True)
            start_index = fp.tell()
            try:
                yield fp
            except Exception:
                fp.close()
                with self._install_log_file.open("r") as fp:
                    fp.seek(start_index)
                    print(fp.read(), file=sys.stderr)
                raise

    def calculate_lockfile(self, requirements: RequirementSpec) -> CalculateLockfileResult:
        """Calculate the lockfile of the environment.

        :param requirements: The requirements that were used to install the environment. These requirements
            will be embedded as part of the returned lockfile.
        """

        python = self.get_program("python")
        env = get_environment_state_of_interpreter(str(python))

        # Convert all distribution names to lowercase.
        # TODO (@NiklasRosenstein): Further changes may be needed to correctly normalize all distribution names.
        env.distributions = {k.lower(): v for k, v in env.distributions.items()}

        # Collect only the package name and version for required packages.
        distributions = {}
        requirements_stack = list(requirements.requirements)

        while requirements_stack:
            package_req = requirements_stack.pop(0)
            package_name = package_req.name.lower()

            if package_name in distributions:
                continue
            if package_name not in env.distributions:
                # NOTE (@NiklasRosenstein): We may be missing the package because it's a requirement that is only
                #       installed under certain conditions (e.g. markers/extras).
                continue

            dist = env.distributions[package_name]

            # Pin the package version.
            distributions[package_name] = dist.version

            # Filter the requirements of the distribution down to the ones required according to markers and the
            # current package requirement's extras.
            for req in map(Requirement, dist.requirements):
                if isinstance(package_req, Requirement) and req.marker:
                    satisfied = any(req.marker.evaluate({"extra": extra}) for extra in package_req.extras)
                else:
                    satisfied = True
                if satisfied:
                    requirements_stack.append(req)

        metadata = LockfileMetadata.new()
        metadata.kraken_cli_version = f"{env.kraken_cli_version} (instrumented by {metadata.kraken_cli_version})"
        metadata.python_version = f"{env.python_version} (instrumented by {env.python_version})"

        extra_distributions = env.distributions.keys() - distributions.keys() - {"pip"}
        return CalculateLockfileResult(Lockfile(metadata, requirements, distributions), extra_distributions)
