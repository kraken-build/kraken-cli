from __future__ import annotations

import argparse
import dataclasses
import hashlib
import re
import shlex
from pathlib import Path
from typing import Any, Iterable, TextIO

from packaging.requirements import Requirement

# TODO: Can we get away with pkg_resources.Requirement instead?


def parse_requirement(value: str) -> LocalRequirement | Requirement:
    # TODO (@NiklasRosenstein): Better support for other operating systems to identify a local requirement
    match = re.match(r"(.*?)@(.*)", value)
    if match:
        return LocalRequirement(match.group(1), Path(match.group(2)))
    else:
        return Requirement(value)


@dataclasses.dataclass
class LocalRequirement:
    """Represents a requirement on a local project on the filesystem.

    The string format of a local requirement is `$PATH [$NAME]` where the `$NAME` is the name of the package
    that is located at the path."""

    def __init__(self, name: str, path: Path) -> None:
        self.name = name
        self.path = path

    def __str__(self) -> str:
        return f"{self.name}@{self.path}"

    def __repr__(self) -> str:
        return f"LocalRequirement({str(self)!r})"


@dataclasses.dataclass
class RequirementSpec:
    """Represents install requirements and associated options."""

    requirements: list[Requirement | LocalRequirement]
    index_url: str | None = None
    extra_index_urls: list[str] = dataclasses.field(default_factory=list)
    pythonpath: list[str] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        for req in self.requirements:
            assert isinstance(req, (Requirement, LocalRequirement)), req

    def add_requirements(self, reqs: Iterable[str | Requirement | LocalRequirement]) -> None:
        for req in reqs:
            if isinstance(req, str):
                req = parse_requirement(req)
            self.requirements.append(req)

    @staticmethod
    def from_json(data: dict[str, Any]) -> RequirementSpec:
        return RequirementSpec(
            requirements=[parse_requirement(x) for x in data["requirements"]],
            index_url=data.get("index_url"),
            extra_index_urls=data.get("extra_index_urls", []),
            pythonpath=data.get("pythonpath", []),
        )

    def to_json(self) -> dict[str, Any]:
        result: dict[str, Any] = {"requirements": [str(x) for x in self.requirements], "pythonpath": self.pythonpath}
        if self.index_url is not None:
            result["index_url"] = self.index_url
        if self.extra_index_urls:
            result["extra_index_urls"] = self.extra_index_urls
        return result

    @staticmethod
    def from_args(args: list[str]) -> RequirementSpec:
        """Parses the arguments using :mod:`argparse` as if they are Pip install arguments.

        :raise ValueError: If an invalid argument is encountered."""

        parser = argparse.ArgumentParser()
        parser.add_argument("packages", nargs="*")
        parser.add_argument("--index-url")
        parser.add_argument("--extra-index-url", action="append")
        parsed, unknown = parser.parse_known_args(args)
        if unknown:
            raise ValueError(f"encountered unknown arguments in requirements: {unknown}")

        return RequirementSpec(
            [parse_requirement(x) for x in parsed.packages or []],
            parsed.index_url,
            parsed.extra_index_url or [],
        )

    def to_args(self, base_dir: Path = Path("."), with_requirements: bool = True) -> list[str]:
        """Converts the requirements back to Pip install arguments.

        :param base_dir: The base directory that relative :class:`LocalRequirement`s should be considered relative to.
        :param with_requirements: Can be set to `False` to not return requirements in the argument, just the index URLs.
        """

        args = []
        if self.index_url:
            args += ["--index-url", self.index_url]
        for url in self.extra_index_urls:
            args += ["--extra-index-url", url]
        if with_requirements:
            args += [str(x) if isinstance(x, (str, Requirement)) else str(base_dir / x.path) for x in self.requirements]
        return args

    def to_hash(self, algorithm: str = "sha256") -> str:
        """Hash the requirements spec to a hexdigest."""

        hash_parts = self.to_args() + ["::pythonpath"] + self.pythonpath
        return hashlib.new(algorithm, ":".join(hash_parts).encode()).hexdigest()


def parse_requirements_from_python_script(file: TextIO) -> RequirementSpec:
    """Parses the requirements defined in a Python script.

    The Pip install arguments are extracted from all lines in the first single-line comment block, which has to start
    at the beginning of the file, which start with the text `# ::requirements` (whitespace optional). Additionally,
    paths to ass to `sys.path` can be specified with `# ::pythonpath`.

    Example:

    ```py
    #!/usr/bin/env python
    # :: requirements PyYAML
    # :: pythonpath ./build-support
    ```

    The resulting :class:`RequirementSpec` will contain `["PyYAML"]` as requirement and `"./build-support"` ain
    the Python path.
    """

    requirements = []
    pythonpath = []
    for line in map(str.rstrip, file):
        if not line.startswith("#"):
            break
        match = re.match(r"#\s*::\s*(requirements|pythonpath)(.+)", line)
        if not match:
            break
        args = shlex.split(match.group(2))
        if match.group(1) == "requirements":
            requirements += args
        else:
            pythonpath += args

    result = RequirementSpec.from_args(requirements)
    result.pythonpath = pythonpath
    return result
