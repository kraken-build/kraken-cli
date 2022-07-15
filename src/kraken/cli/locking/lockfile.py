from __future__ import annotations

import dataclasses
import datetime
import platform
import sys
from typing import Any

from .requirements import RequirementSpec

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

    def to_args(self) -> list[str]:
        """Converts the pinned versions in the lock file to Pip install args."""

        args = self.requirements.to_args(with_requirements=False)
        for key, value in self.pinned.items():
            args += [f"{key}=={value}"]
        return args
