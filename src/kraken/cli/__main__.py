from __future__ import annotations

import argparse
import logging
import os
import subprocess as sp

# import profile
import sys
from pathlib import Path
from typing import Any, cast

from kraken.core.build_context import BuildContext, BuildError
from kraken.core.build_graph import BuildGraph
from kraken.core.executor import COLORS_BY_STATUS, TaskStatus, get_task_status
from kraken.core.property import Property
from kraken.core.task import Task
from slap.core.cli import CliApp, Command, Group
from termcolor import colored

from kraken.cli.buildenv.environment import BuildEnvironment
from kraken.cli.buildenv.project import DefaultProjectImpl, ProjectInterface

from . import __version__

logger = logging.getLogger(__name__)


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
            default=Path(".build"),
            help="the build directory to write to [default: %(default)s]",
        )
        parser.add_argument(
            "-p",
            "--project-dir",
            metavar="PATH",
            type=Path,
            default=Path.cwd(),
            help="the root project directory [default: ./]",
        )

    def in_build_environment(self) -> bool:
        """Returns `True` if we're currently situated inside a build environment."""

        if os.getenv("KRAKEN_MANAGED") == "1":
            logger.info("found KRAKEN_MANAGED=1, current environment is considered the build environment")
            return True
        return False

    def get_build_environment(self, args: Args) -> BuildEnvironment:
        """Returns the handle to manage the build environment."""

        return BuildEnvironment(args.build_dir / "venv")

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
            logger.info("creating build environment (%s)", build_env.path)
            build_env.create(None)

        # NOTE (@NiklasRosenstein): This requirement spec will already contain the implied Kraken CLI requirement.
        requirements = project.get_requirement_spec()

        if not upgrade:
            lockfile = project.read_lock_file()
            if lockfile is not None:
                if lockfile.requirements.to_hash() != requirements.to_hash():
                    logger.warning("lockfile appears to be outdated compared to project build requirements.")
                    logger.warning("    you should consider re-locking using the `kraken env lock` command.")

                if lockfile.requirements.to_hash() != build_env.hash:
                    logger.info("environment is outdated compared to lockfile")
                    build_env.install_lockfile(lockfile)
                    build_env.hash = lockfile.requirements.to_hash()
                    return

        if requirements.to_hash() != build_env.hash or upgrade:
            logger.info("installing requirements into build environment (%s)", build_env.path)
            build_env.install_requirements(requirements, upgrade)
            return

        logger.info("build environment is up to date")

    def dispatch_to_build_environment(self, args: Args) -> int:
        """Dispatch to the build environment."""

        if self.in_build_environment():
            raise RuntimeError("cannot dispatch if we're already inside the build environment")

        build_env = self.get_build_environment(args)
        project = self.get_project_interface(args)
        self.install(build_env, project)

        logger.info("dispatching to virtual environment %s", build_env.path)
        kraken_cli = build_env.get_program("kraken")
        env = os.environ.copy()
        env["KRAKEN_MANAGED"] = "1"
        return sp.call([str(kraken_cli)] + sys.argv[1:], env=env)

    def execute(self, args: Args) -> int | None:
        logging.basicConfig(
            level=logging.INFO if args.verbose else logging.ERROR if args.quiet else logging.WARNING,
            format=f"{colored('%(levelname)7s', 'magenta')} | {colored('%(name)s', 'blue')} | "
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

    def resolve_tasks(self, args: Args, context: BuildContext) -> list[Task]:
        return context.resolve_tasks(args.targets or None)

    def execute(self, args: Args) -> int | None:  # type: ignore[override]
        super().execute(args)

        if not self.in_build_environment():
            return self.dispatch_to_build_environment(args)

        context = BuildContext(args.build_dir)
        context.load_project(None, Path.cwd())
        context.finalize()
        targets = self.resolve_tasks(args, context)
        graph = BuildGraph(targets)

        return self.execute_with_graph(context, graph, args)

    def execute_with_graph(self, context: BuildContext, graph: BuildGraph, args: Args) -> int | None:
        raise NotImplementedError


class RunCommand(BuildGraphCommand):
    class Args(BuildGraphCommand.Args):
        skip_build: bool

    def __init__(self, main_target: str | None = None) -> None:
        super().__init__()
        self._main_target = main_target

    def get_description(self) -> str:
        if self._main_target:
            return f'execute "{self._main_target}" tasks'
        else:
            return "execute one or more kraken tasks"

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("-s", "--skip-build", action="store_true", help="just load the project, do not build")

    def resolve_tasks(self, args: BuildGraphCommand.Args, context: BuildContext) -> list[Task]:
        if self._main_target:
            targets = [self._main_target] + list(args.targets or [])
            return context.resolve_tasks(targets)
        return super().resolve_tasks(args, context)

    def execute_with_graph(self, context: BuildContext, graph: BuildGraph, args: Args) -> int | None:  # type: ignore
        graph.trim()
        if not graph:
            print("error: no tasks selected", file=sys.stderr)
            return 1
        if not args.skip_build:
            try:
                context.execute(graph, True)
            except BuildError as exc:
                logger.error("%s", exc)
                return 1
        return 0


class LsCommand(BuildGraphCommand):
    """list targets in the build"""

    class Args(BuildGraphCommand.Args):
        default: bool
        all: bool

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument(
            "-d",
            "--default",
            action="store_true",
            help="trim non-default tasks (only without selected targets)",
        )

    def resolve_tasks(self, args: Args, context: BuildContext) -> list[Task]:  # type: ignore
        tasks: list[Task] = []
        if args.default:
            if args.targets:
                self.get_parser().error("cannot combine -d,--default with target selection")
            for project in context.iter_projects():
                for task in project.tasks().values():
                    if task.default:
                        tasks.append(task)
            return tasks
        if args.targets:
            return context.resolve_tasks(args.targets)
        for project in context.iter_projects():
            tasks += project.tasks().values()
        return tasks

    def execute_with_graph(self, context: BuildContext, graph: BuildGraph, args: BuildGraphCommand.Args) -> None:
        if len(graph) == 0:
            print("no tasks.", file=sys.stderr)
            sys.exit(1)

        longest_name = max(map(len, (task.path for task in graph.tasks()))) + 1
        print(colored("D " + "Task".ljust(longest_name + 1) + "Type", attrs=["bold"]))
        for task in graph.execution_order():
            print(
                colored("●", "cyan" if task.default else "grey"),
                task.path.ljust(longest_name),
                type(task).__module__ + "." + type(task).__name__,
            )


class QueryCommand(BuildGraphCommand):
    """perform queries on the build graph"""

    class Args(BuildGraphCommand.Args):
        is_up_to_date: bool
        legend: bool

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("--legend", action="store_true", help="print out a legend along with the query result")
        parser.add_argument("--is-up-to-date", action="store_true", help="query if the selected task(s) are up to date")

    def execute(self, args: BuildGraphCommand.Args) -> int | None:  # type: ignore[override]
        args.quiet = True
        return super().execute(args)

    def execute_with_graph(self, context: BuildContext, graph: BuildGraph, args: Args) -> int | None:  # type: ignore
        if args.is_up_to_date:
            tasks = list(graph.tasks(required_only=True))
            print(f"querying status of {len(tasks)} task(s)")
            print()

            need_to_run = 0
            up_to_date = 0
            for task in graph.execution_order():
                if task not in tasks:
                    continue
                status = get_task_status(task)
                print(" ", task.path, colored(status.name, COLORS_BY_STATUS[status]))
                if status in (TaskStatus.SKIPPABLE, TaskStatus.UP_TO_DATE):
                    up_to_date += 1
                else:
                    need_to_run += 1

            print()
            print(colored(f"{up_to_date} task(s) are up to date, need to run {need_to_run} task(s)", attrs=["bold"]))

            if args.legend:
                print()
                print("legend:")
                help_text = {
                    TaskStatus.SKIPPABLE: "the task reports that it can and will be skipped",
                    TaskStatus.UP_TO_DATE: "the task reports that it is up to date",
                    TaskStatus.OUTDATED: "the task reports that it is outdated",
                    TaskStatus.QUEUED: "the task needs to run always or it cannot determine its up to date status",
                }
                for status in TaskStatus:
                    print(colored(status.name.rjust(12), COLORS_BY_STATUS[status]) + ":", help_text[status])

            exit_code = 0 if need_to_run == 0 else 1
            print()
            print("exit code:", exit_code)
            sys.exit(exit_code)

        else:
            self.get_parser().error("missing query")


class DescribeCommand(BuildGraphCommand):
    """describe one or more tasks in detail"""

    def execute_with_graph(self, context: BuildContext, graph: BuildGraph, args: BuildGraphCommand.Args) -> None:
        tasks = list(graph.tasks(required_only=True))
        print("selected", len(tasks), "task(s)")
        print()

        for task in tasks:
            print("Task", colored(task.path, attrs=["bold", "underline"]))
            print("  Type".ljust(30), type(task).__module__ + "." + type(task).__name__)
            print("  File".ljust(30), colored(sys.modules[type(task).__module__].__file__ or "???", "cyan"))
            print("  Default".ljust(30), task.default)
            print("  Capture".ljust(30), task.capture)
            rels = list(task.get_relationships())
            print("  Relationships".ljust(30), len(rels))
            for rel in rels:
                print(
                    "".ljust(4),
                    colored(rel.other_task.path, attrs=["bold"]),
                    f"before={rel.before}, strict={rel.strict}",
                )
            print("  Properties".ljust(30), len(type(task).__schema__))
            for key in type(task).__schema__:
                prop: Property[Any] = getattr(task, key)
                print("".ljust(4), colored(key, attrs=["reverse"]), f'= {colored(prop.get_or("<unset>"), "blue")}')
            print()


class EnvStatusCommand(BuildAwareCommand):
    """provide the status of the build environment"""

    def execute(self, args: Any) -> None:
        super().execute(args)
        if self.in_build_environment():
            self.get_parser().error("`kraken env` commands cannot be used inside managed enviroment")

        build_env = self.get_build_environment(args)
        project = self.get_project_interface(args)
        requirements = project.get_requirement_spec()
        lockfile = project.read_lock_file()

        print(" environment path:", build_env.path, "" if build_env.exists() else "(does not exist)")
        print(" environment hash:", build_env.hash)
        print("requirements hash:", requirements.to_hash())
        print("    lockfile hash:", lockfile.requirements.to_hash() if lockfile else None)


class BaseEnvCommand(BuildAwareCommand):
    def write_lock_file(self, build_env: BuildEnvironment, project: ProjectInterface) -> None:
        result = build_env.calculate_lockfile(project.get_requirement_spec())
        if result.extra_distributions:
            logger.warning(
                "build environment contains distributions that are not required: %s",
                result.extra_distributions,
            )
        project.write_lock_file(result.lockfile)

    def execute(self, args: BuildAwareCommand.Args) -> int | None:
        super().execute(args)
        if self.in_build_environment():
            self.get_parser().error("`kraken env` commands cannot be used inside managed enviroment")
        return None


class EnvInstallCommand(BaseEnvCommand):
    """ensure the build environment is installed"""

    def execute(self, args: Any) -> None:
        super().execute(args)
        build_env = self.get_build_environment(args)
        project = self.get_project_interface(args)
        self.install(build_env, project)


class EnvUpgradeCommand(BaseEnvCommand):
    """upgrade the build environment and lock file"""

    def execute(self, args: Any) -> None:
        super().execute(args)
        build_env = self.get_build_environment(args)
        project = self.get_project_interface(args)
        self.install(build_env, project, True)
        if project.has_lock_file():
            self.write_lock_file(build_env, project)


class EnvLockCommand(BaseEnvCommand):
    """create or update the lock file"""

    def execute(self, args: Any) -> None:
        super().execute(args)
        build_env = self.get_build_environment(args)
        project = self.get_project_interface(args)
        self.write_lock_file(build_env, project)


class EnvRemoveCommand(BaseEnvCommand):
    """remove the build environment"""

    def execute(self, args: BuildAwareCommand.Args) -> int | None:
        super().execute(args)
        build_env = self.get_build_environment(args)
        if build_env.exists():
            logger.info("removing build environment (%s)", build_env.path)
            build_env.remove()
            return 0
        else:
            print("build environment does not exist")
            return 1


def _main() -> None:
    from kraken import core

    env = Group("manage the build environment")
    env.add_command("status", EnvStatusCommand())
    env.add_command("install", EnvInstallCommand())
    env.add_command("upgrade", EnvUpgradeCommand())
    env.add_command("lock", EnvLockCommand())
    env.add_command("remove", EnvRemoveCommand())

    app = CliApp("kraken", f"cli: {__version__}, core: {core.__version__}", features=[])
    app.add_command("run", RunCommand())
    app.add_command("fmt", RunCommand("fmt"))
    app.add_command("lint", RunCommand("lint"))
    app.add_command("build", RunCommand("build"))
    app.add_command("test", RunCommand("test"))
    app.add_command("ls", LsCommand())
    app.add_command("query", QueryCommand())
    app.add_command("describe", DescribeCommand())
    app.add_command("env", env)
    sys.exit(app.run())


def _entrypoint() -> None:
    _main()
    # prof = profile.Profile()
    # try:
    #     prof.runcall(_main)
    # finally:
    #     import pstats
    #     stats = pstats.Stats(prof)
    #     stats.sort_stats('cumulative')
    #     stats.print_stats(.1)


if __name__ == "__main__":
    _entrypoint()
