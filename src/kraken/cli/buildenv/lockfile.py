from __future__ import annotations

import dataclasses
import datetime
import json
import platform
import sys
from pathlib import Path
from typing import Any

from .requirements import LocalRequirement, RequirementSpec

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.Z"


def dt2json(dt: datetime.datetime) -> str:
    return dt.strftime(DATETIME_FORMAT)


def json2dt(value: str) -> datetime.datetime:
    return datetime.datetime.strptime(value, DATETIME_FORMAT)


@dataclasses.dataclass
class LockfileMetadata:
    """Metadata for the lock file."""

    #: The date and time when the lock file was created.
    created_at: datetime.datetime

    #: The Python version that the lock file was created with.
    python_version: str

    #: The system uname that the lock file was created with.
    uname: str

    #: The version of the Kraken CLI that the lock file was created with.
    kraken_cli_version: str

    @staticmethod
    def new() -> LockfileMetadata:
        from kraken.cli import __version__

        return LockfileMetadata(
            created_at=datetime.datetime.utcnow(),
            python_version=sys.version,
            uname=str(platform.uname()),  # TODO (@NiklasRosenstein): Format uname struct
            kraken_cli_version=__version__,
        )

    @staticmethod
    def from_json(data: dict[str, Any]) -> LockfileMetadata:
        return LockfileMetadata(
            created_at=json2dt(data.pop("created_at")),
            **data,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "created_at": dt2json(self.created_at),
            "python_version": self.python_version,
            "uname": self.uname,
            "kraken_cli_version": self.kraken_cli_version,
        }


@dataclasses.dataclass
class Lockfile:
    """This structure encodes all the data that needs to be present in a lock file to replicate an environment."""

    #: Metadata for when the lock file was created.
    metadata: LockfileMetadata

    #: The requirements from which the environment was originally populated.
    requirements: RequirementSpec

    #: Exact versions for packages that were installed into the environment.
    pinned: dict[str, str]

    @staticmethod
    def from_path(path: Path) -> Lockfile | None:
        if path.is_file():
            with path.open() as fp:
                return Lockfile.from_json(json.load(fp))
        return None

    def write_to(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=2))

    @staticmethod
    def from_json(data: dict[str, Any]) -> Lockfile:
        return Lockfile(
            metadata=LockfileMetadata.from_json(data["metadata"]),
            requirements=RequirementSpec.from_json(data["requirements"]),
            pinned=data["pinned"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_json(),
            "requirements": self.requirements.to_json(),
            "pinned": self.pinned,
        }

    def to_args(self, base_dir: Path = Path(".")) -> list[str]:
        """Converts the pinned versions in the lock file to Pip install args.

        :param base_dir: The base directory that relative :class:`LocalRequirement`s should be considered relative to.
        """

        args = self.requirements.to_args(with_requirements=False)
        local_dependencies = {
            dep.name: base_dir / dep.path for dep in self.requirements.requirements if isinstance(dep, LocalRequirement)
        }
        for key, value in self.pinned.items():
            if key in local_dependencies:
                # NOTE (@NiklasRosenstein): The purpose here is to keep local dependencies installed from the same
                #       local source.
                args += [str(local_dependencies[key])]
            else:
                args += [f"{key}=={value}"]
        return args
