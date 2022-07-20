from __future__ import annotations

import argparse
from typing import Any

from termcolor import colored

from kraken.cli.buildenv.environment import BuildEnvironment
from kraken.cli.buildenv.lockfile import Lockfile
from kraken.cli.buildenv.project import ProjectInterface

from .base import BuildAwareCommand, print


class EnvInfoCommand(BuildAwareCommand):
    """provide the info on the build environment"""

    class Args(BuildAwareCommand.Args):
        path: bool

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument(
            "-P",
            "--path",
            action="store_true",
            help="print the path to the build environment, or nothing and return 1 if it does not exist.",
        )

    def execute(self, args: Args) -> int | None:  # type: ignore[override]
        super().execute(args)
        if self.in_build_environment():
            self.get_parser().error("`kraken env` commands cannot be used inside managed enviroment")

        build_env = self.get_build_environment(args)
        if args.path:
            if build_env.exists():
                print(build_env.path.absolute())
                return 0
            else:
                return 1

        project = self.get_project_interface(args)
        requirements = project.get_requirement_spec()
        lockfile = Lockfile.from_path(project.get_lock_file())

        print("requirements hash:", requirements.to_hash())
        print("    lockfile hash:", lockfile.requirements.to_hash() if lockfile else None)
        print(" environment hash:", build_env.hash)
        print(" environment path:", build_env.path, "" if build_env.exists() else "(does not exist)")
        print()
        print(requirements)
        return 0


class BaseEnvCommand(BuildAwareCommand):
    def write_lock_file(self, build_env: BuildEnvironment, project: ProjectInterface) -> None:
        result = build_env.calculate_lockfile(project.get_requirement_spec())
        print(colored("Writing to lock file (%s)" % (colored(str(project.get_lock_file()), attrs=["bold"]),), "blue"))
        result.lockfile.write_to(project.get_lock_file())
        if result.extra_distributions:
            print(
                colored(
                    "Warning: Your build environment contains %d distributions that are not required.\n"
                    "         The offending distributions are: %s\n"
                    % (len(result.extra_distributions), ", ".join(result.extra_distributions)),
                    "yellow",
                )
            )

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
        if project.get_lock_file().exists():
            self.write_lock_file(build_env, project)


class EnvLockCommand(BaseEnvCommand):
    """create or update the lock file"""

    def execute(self, args: Any) -> None:
        super().execute(args)
        build_env = self.get_build_environment(args)
        project = self.get_project_interface(args)
        if not build_env.exists():
            self.install(build_env, project)
        self.write_lock_file(build_env, project)


class EnvRemoveCommand(BaseEnvCommand):
    """remove the build environment"""

    def execute(self, args: BuildAwareCommand.Args) -> int | None:
        super().execute(args)
        build_env = self.get_build_environment(args)
        if build_env.exists():
            print(colored("Removing build environment (%s)" % (colored(str(build_env.path), attrs=["bold"]),), "blue"))
            build_env.remove()
            return 0
        else:
            print(colored("Build environment cannot be removed because it does not exist.", "red"))
            return 1
