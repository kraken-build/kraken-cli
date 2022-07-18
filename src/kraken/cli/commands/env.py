from __future__ import annotations

import logging
from typing import Any

from kraken.cli.buildenv.environment import BuildEnvironment
from kraken.cli.buildenv.project import ProjectInterface

from .base import BuildAwareCommand

logger = logging.getLogger(__name__)


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
