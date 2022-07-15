# kraken-cli

[![Python application](https://github.com/kraken-build/kraken-cli/actions/workflows/python-package.yml/badge.svg)](https://github.com/kraken-build/kraken-cli/actions/workflows/python-package.yml)
[![PyPI version](https://badge.fury.io/py/kraken-cli.svg)](https://badge.fury.io/py/kraken-cli)

The command-line interface to the Kraken CLI.

Unless you set the environment variable `KRAKEN_MANAGED=0`, the CLI will always bootstrap a new Python virtual
environment for you that contains exactly the build requirements set forth in your project requirements. These
requirements can be specified either in a spearate file (`.kraken/requirements.txt`) or in the build script directly.

```py
# ::requirements PyYAML kraken-std
# ::requirements --extra-index-url https://test.pypi.org/simple
#
# This is a Kraken build script

from kraken.std.docker import build_docker_image
build_docker_image()
```

For package indices that require authentication, the typical way to configure credentials of additional indexes in
Pip should be used (it is recommended to use `~/.netrc` if possible).

## Development

When developing this package locally, it may be desirable to have the current version being developed installed
into the virtual environment. For this purpose, you can set the `KRAKEN_DEVELOP=1` variable, which will change
the implied dependency from `kraken-cli` to the directory that contains the `kraken.cli` module.

> Note: Currently, the source directory of the kraken-cli project is derived by following the symlink of the
> `kraken/cli/__init__.py` file and then looking four directories up (cli, kraken, src, kraken-cli project root).
> This assumption is made based on how symlink installs work with `slap link` or `slap install --link`.
