from __future__ import annotations

# import profile
import sys

from slap.core.cli import CliApp, Group


def _main() -> None:
    from kraken import core

    from . import __version__
    from .commands.env import EnvInfoCommand, EnvInstallCommand, EnvLockCommand, EnvRemoveCommand, EnvUpgradeCommand
    from .commands.query import DescribeCommand, IsUpToDateCommand, LsCommand, VizCommand
    from .commands.run import RunCommand

    env = Group("manage the build environment")
    env.add_command("info", EnvInfoCommand())
    env.add_command("install", EnvInstallCommand())
    env.add_command("upgrade", EnvUpgradeCommand())
    env.add_command("lock", EnvLockCommand())
    env.add_command("remove", EnvRemoveCommand())

    query = Group("run queries against on the task graph")
    query.add_command("ls", LsCommand())
    query.add_command("up-to-date", IsUpToDateCommand())
    query.add_command("describe", DescribeCommand())
    query.add_command("viz", VizCommand())

    app = CliApp("kraken", f"cli: {__version__}, core: {core.__version__}", features=[])
    app.add_command("run", RunCommand())
    app.add_command("env", env)
    app.add_command("q", query)
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
