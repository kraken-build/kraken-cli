from __future__ import annotations

# import profile
import sys

from slap.core.cli import CliApp, Group


def _main() -> None:
    from kraken import core

    from . import __version__
    from .commands.env import EnvInfoCommand, EnvInstallCommand, EnvLockCommand, EnvRemoveCommand, EnvUpgradeCommand
    from .commands.inspection import DescribeCommand, LsCommand, QueryCommand
    from .commands.run import RunCommand

    env = Group("manage the build environment")
    env.add_command("info", EnvInfoCommand())
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
