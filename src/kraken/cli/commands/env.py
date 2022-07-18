from __future__ import annotations

from typing import Any

from termcolor import colored

from kraken.cli.buildenv.environment import BuildEnvironment
from kraken.cli.buildenv.lockfile import Lockfile
from kraken.cli.buildenv.project import ProjectInterface

from .base import BuildAwareCommand


class EnvStatusCommand(BuildAwareCommand):
    """provide the status of the build environment"""

    def execute(self, args: Any) -> None:
        super().execute(args)
        if self.in_build_environment():
            self.get_parser().error("`kraken env` commands cannot be used inside managed enviroment")

        build_env = self.get_build_environment(args)
        project = self.get_project_interface(args)
        requirements = project.get_requirement_spec()
        lockfile = Lockfile.from_path(project.get_lock_file())

        print(" environment path:", build_env.path, "" if build_env.exists() else "(does not exist)")
        print(" environment hash:", build_env.hash)
        print("requirements hash:", requirements.to_hash())
        print("    lockfile hash:", lockfile.requirements.to_hash() if lockfile else None)


class BaseEnvCommand(BuildAwareCommand):
    def write_lock_file(self, build_env: BuildEnvironment, project: ProjectInterface) -> None:
        result = build_env.calculate_lockfile(project.get_requirement_spec())
        result.lockfile.write_to(project.get_lock_file())
        if result.extra_distributions:
            print(
                colored(
                    "Warning: Your build environment contains %d distributions that are not required.\n"
                    "         The offending distributions are: %s\n" % ", ".join(result.extra_distributions),
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
