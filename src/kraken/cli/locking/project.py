from __future__ import annotations

import abc
import dataclasses
import json
from pathlib import Path

from .lockfile import Lockfile
from .requirements import RequirementSpec, parse_requirements_file, parse_requirements_from_python_script


class ProjectInterface(abc.ABC):
    @abc.abstractmethod
    def get_requirement_spec(self) -> RequirementSpec:
        """Called to read the requirement spec of the project."""

        raise NotImplementedError

    @abc.abstractmethod
    def read_lock_file(self) -> Lockfile | None:
        """Return the lock file in the project."""

        raise NotImplementedError

    @abc.abstractmethod
    def write_lock_file(self, data: Lockfile) -> None:
        """Update the lock file in the project."""

        raise NotImplementedError


class DefaultProjectImpl(ProjectInterface):
    """This implementation looks for requirements in the following way:

    * Load `.kraken/requirements.txt` or `.kraken.requirements.txt`
    * Otherwise find a build script using the Kraken Core loaders interface and load the requirements from the first
        comment block (see :class:`parse_requirements_from_python_script`).

    The Kraken lock file will, if it exists, be loaded from the following locations:

    * `.kraken/lock.json` or `.kraken.lock.json`

    If it does not exist, it will be placed next to the build script if it exists in a `.kraken` folder, otherwise
    into the project root as `.kraken.lock.json`.
    """

    REQUIREMENT_FILES = [Path(".kraken/requirements.txt"), Path(".kraken.requirements")]
    LOCK_FILES = [Path(".kraken/kraken.lock"), Path(".kraken.lock")]

    @dataclasses.dataclass
    class Files:
        requirements: Path | None
        script: Path | None
        lock: Path

    def __init__(self, project_dir: Path | None = None) -> None:
        self.project_dir = project_dir or Path.cwd()
        self._files: DefaultProjectImpl.Files | None = None

    def _get_files(self) -> Files:
        """Determines the files to read/write."""

        from kraken.core.loader import get_loader_implementations

        if self._files is not None:
            return self._files

        # Find a file we can load requirements from.
        requirements_file: Path | None = None
        script_file: Path | None = None
        for path in self.REQUIREMENT_FILES:
            requirements_file = self.project_dir / path
            if requirements_file.is_file():
                break
        else:
            requirements_file = None
            for loader in get_loader_implementations():
                script_file = loader.detect_in_project_directory(self.project_dir)
                if script_file:
                    break
            else:
                raise RuntimeError("could not find a requirements file or Kraken build script")

        assert requirements_file or script_file

        # Find the lock file.
        alternative_lock_file: Path | None = None
        for path in self.LOCK_FILES:
            lock_file = self.project_dir / path
            if lock_file.parent.is_dir() and not alternative_lock_file:
                alternative_lock_file = lock_file
            if lock_file.exists():
                break
        else:
            assert alternative_lock_file
            lock_file = alternative_lock_file

        self._files = self.Files(requirements_file, script_file, lock_file)
        return self._files

    def get_requirement_spec(self) -> RequirementSpec:
        files = self._get_files()
        if files.requirements:
            with files.requirements.open() as fp:
                return RequirementSpec.from_args(parse_requirements_file(fp))
        elif files.script:
            with files.script.open() as fp:
                return RequirementSpec.from_args(parse_requirements_from_python_script(fp))
        else:
            assert False, files

    def read_lock_file(self) -> Lockfile | None:
        files = self._get_files()
        if files.lock.is_file():
            with files.lock.open() as fp:
                return Lockfile.from_json(json.load(fp))
        return None

    def write_lock_file(self, data: Lockfile) -> None:
        files = self._get_files()
        try:
            file = files.lock.relative_to(Path.cwd())
        except ValueError:
            file = files.lock
        print("writing lock file", file)
        files.lock.parent.mkdir(parents=True, exist_ok=True)
        with files.lock.open("w") as fp:
            json.dump(data.to_json(), fp, indent=4)
