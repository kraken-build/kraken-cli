from __future__ import annotations

import argparse
import builtins
import logging
import os
import shlex
import subprocess as sp
import sys
from functools import partial
from pathlib import Path
from typing import Any, cast

from kraken.core import Context, Task, TaskGraph
from slap.core.cli import Command
from termcolor import colored

from kraken.cli import __version__
from kraken.cli.buildenv.environment import BuildEnvironment
from kraken.cli.buildenv.lockfile import Lockfile
from kraken.cli.buildenv.project import DefaultProjectImpl, ProjectInterface

DEFAULT_BUILD_DIR = Path("build")
DEFAULT_PROJECT_DIR = Path(".")
print = partial(builtins.print, flush=True)


def get_implied_requirements(develop: bool) -> list[str]:
    """Returns a list of requirements that are implied for build environments managed by Kraken CLI.

    :param develop: If set to `True`, it is assumed that the current Kraken CLI is installed in develop mode
        using `slap link` or `slap install --link` and will be installed from the local project directory on
        the file system instead of from PyPI. Otherwise, Kraken CLI will be picked up from PyPI.
    """

    if develop:
        import kraken.cli

        init_path = Path(kraken.cli.__file__).resolve()
        kraken_path = init_path.parent.parent.parent
        project_root = kraken_path.parent
        pyproject = project_root / "pyproject.toml"
        if not pyproject.is_file():
            raise RuntimeError(
                "kraken-cli does not seem to be installed in development mode (expected kraken-cli's "
                'pyproject.toml at "%s")' % pyproject
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


class BuildAwareCommand(Command):
    """A build aware command is aware of the build environment and provides the capabilities to dispatch the
    same command to the same command inside the build environment.

    It serves as the base command for all Kraken commands as they either need to dispatch to the build environment
    or manage it."""

    class Args:
        verbose: bool
        quiet: bool
        build_dir: Path
        project_dir: Path

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("-v", "--verbose", action="store_true", help="always show task output and logs")
        parser.add_argument("-q", "--quiet", action="store_true", help="show less logs")
        parser.add_argument(
            "-b",
            "--build-dir",
            metavar="PATH",
            type=Path,
            default=DEFAULT_BUILD_DIR,
            help="the build directory to write to [default: %(default)s]",
        )
        parser.add_argument(
            "-p",
            "--project-dir",
            metavar="PATH",
            type=Path,
            default=DEFAULT_PROJECT_DIR,
            help="the root project directory [default: ./]",
        )

    def in_build_environment(self) -> bool:
        """Returns `True` if we're currently situated inside a build environment."""

        return os.getenv("KRAKEN_MANAGED") == "1"

    def get_build_environment(self, args: Args) -> BuildEnvironment:
        """Returns the handle to manage the build environment."""

        return BuildEnvironment(args.project_dir, args.build_dir / "venv")

    def get_project_interface(self, args: Args) -> ProjectInterface:
        """Returns the implementation that deals with project specific data such as build requirements and
        lock files on disk."""

        develop = os.getenv("KRAKEN_DEVELOP") == "1"
        implied_requirements = get_implied_requirements(develop)
        return DefaultProjectImpl(args.project_dir, implied_requirements)

    def install(self, build_env: BuildEnvironment, project: ProjectInterface, upgrade: bool = False) -> None:
        """Make sure that the build environment exists and the requirements are installed.

        :param build_env: The build environment to ensure is up to date.
        :param project: Implementation that provides access to the requirement spec and lockfile.
        :param upgrade: If set to `True`, ignore the lockfile and reinstall requirement spec.
        """

        if not build_env.exists():
            print(
                colored(
                    "Creating Kraken build environment (%s) ..." % (colored(str(build_env.path), attrs=["bold"]),),
                    "blue",
                )
            )
            build_env.create(None)
        else:
            print(
                colored(
                    "Reusing Kraken build environment (%s)" % (colored(str(build_env.path), attrs=["bold"]),),
                    "blue",
                )
            )

        # NOTE (@NiklasRosenstein): This requirement spec will already contain the implied Kraken CLI requirement.
        requirements = project.get_requirement_spec()

        if not upgrade:
            lockfile_path = project.get_lock_file()
            lockfile = Lockfile.from_path(lockfile_path)
            if lockfile is not None:
                if lockfile.requirements.to_hash() != requirements.to_hash():
                    print(
                        colored(
                            "Warning: Your lockfile (%s) appears to be outdated. Consider re-writing it using the\n"
                            "         %s command."
                            % (
                                colored(str(lockfile_path), attrs=["bold"]),
                                colored("kraken env lock", "grey", attrs=["underline"]),
                            ),
                            "yellow",
                        )
                    )

                if lockfile.requirements.to_hash() != build_env.hash:
                    print(
                        colored(
                            "Warning: Your build environment is outdated compared to your lockfile (%s).\n"
                            "         Reinstalling from lockfile now ..."
                            % (colored(str(lockfile_path), attrs=["bold"]),),
                            "yellow",
                        )
                    )
                    build_env.install_lockfile(lockfile)
                    build_env.hash = lockfile.requirements.to_hash()

                return

        if build_env.hash is not None and requirements.to_hash() != build_env.hash:
            print(
                colored(
                    "Warning: Your build environment is outdated compared to your requirements.\n"
                    "         Reinstalling from requirements now ...",
                    "yellow",
                )
            )
            install = True
        elif build_env.hash is None:
            print(colored("Installing from requirements ...", "blue"))
            install = True
        elif upgrade:
            print(colored("Upgrading environment from requirements ...", "blue"))
            install = True
        else:
            install = False

        if install:
            build_env.install_requirements(requirements, upgrade)
            build_env.hash = requirements.to_hash()

    def dispatch_to_build_environment(self, args: Args) -> int:
        """Dispatch to the build environment."""

        if self.in_build_environment():
            raise RuntimeError("cannot dispatch if we're already inside the build environment")

        build_env = self.get_build_environment(args)
        project = self.get_project_interface(args)
        self.install(build_env, project)

        print(
            colored(
                "Dispatching command `%s` to build environment (%s)"
                % (
                    "kraken " + " ".join(map(shlex.quote, sys.argv[1:])),
                    colored(str(build_env.path), attrs=["bold"]),
                ),
                "blue",
            )
        )

        kraken_cli = build_env.get_program("kraken")
        env = os.environ.copy()
        env["KRAKEN_MANAGED"] = "1"
        return sp.call([str(kraken_cli)] + sys.argv[1:], env=env)

    def execute(self, args: Args) -> int | None:
        logging.basicConfig(
            level=logging.INFO if args.verbose else logging.ERROR if args.quiet else logging.WARNING,
            format=f"{colored('%(levelname)-7s', 'magenta')} | {colored('%(name)-24s', 'blue')} | "
            f"{colored('%(message)s', 'cyan')}",
        )
        return None


class BuildGraphCommand(BuildAwareCommand):
    """Base class for commands that require the fully materialized Kraken build graph."""

    class Args(BuildAwareCommand.Args):
        file: Path | None
        targets: list[str]

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("targets", metavar="target", nargs="*", help="one or more target to build")

    def resolve_tasks(self, args: Args, context: Context) -> list[Task]:
        return context.resolve_tasks(args.targets or None)

    def execute(self, args: Args) -> int | None:  # type: ignore[override]
        super().execute(args)

        if not self.in_build_environment():
            return self.dispatch_to_build_environment(args)

        # NOTE (@NiklasRosenstein): If we're inside the build environment that is managed by Kraken, we could
        #       skip this step, but if we're not (e.g. if the user manually sets KRAKEN_MANAGED=1), we still
        #       need to update the path.
        project = self.get_project_interface(args)
        sys.path += [str((args.project_dir / path)) for path in project.get_requirement_spec().pythonpath]

        context = Context(args.build_dir)
        context.load_project(None, Path.cwd())
        context.finalize()
        targets = self.resolve_tasks(args, context)
        graph = TaskGraph(targets)

        return self.execute_with_graph(context, graph, args)

    def execute_with_graph(self, context: Context, graph: TaskGraph, args: Args) -> int | None:
        raise NotImplementedError
