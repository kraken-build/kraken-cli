# Build Environment

The Kraken CLI manages a separate build environment in which only the requirements needed for the execution of the
build script are installed.

The build requirements are read from the header of the `.kraken.py` build script of the root project. __Example__:

```py
# ::requirements PyYAML kraken-std
# ::requirements --extra-index-url https://test.pypi.org/simple
# ::pythonpath ./build-support
```

!!! info

    The `::requirements` and `::pythonpath` lines must be within the first single-line comment block at the top of
    the file. Using `::pythonpath`, you can specify a path relative to your project directory that should be added
    to `sys.path` when executing your build script.

!!! warning

    The requirements listed in build scripts that are included as sub projects by the main build script are ignored,
    thus collecting the dependencies of build scripts transitively is not currently supported.

Using the `kraken env lock` or `kraken env update` command will write a lock file named **`.kraken.lock`** that is a
JSON file containing the exact installed versions.

Below is a summary of Kraken CLI's behaviour for several commands with respect to the build environment:

| Command | Behaviour |
| ------- | --------- |
| `kraken env install` | Ensure that the build environment is installed. <sup>(1)</sup> |
| `kraken env upgrade` | Reinstall requirements, ignoring the existing lock file and write a new one. |
| `kraken env lock` | Write the lock file. Requires that the build environment exists. |
| `kraken env remove` | Delete the build environment. |
| `kraken run` | (1) |

## Workflow chart

![](./img/kraken.excalidraw.png)

## Environment variables

The following environment variables alter the behaviour of Kraken CLI with respect to the build environment:

| Variables | Description |
| --------- | ----------- |
| `KRAKEN_MANAGED` | If set to `1`, the Python environment from which the `kraken` command is run will be considered the build environment. No requirements will be installed and no subprocess is used to dispatch the build to a separate Python environment. |
| `KRAKEN_DEVELOP` | If set to `1`, Kraken CLI must currently be installed in develop mode and will instruct it to install the same Kraken CLI from your local file system into the build environment instead of from PyPI. |
| `KRAKEN_ALWAYS_UPDATE_LOCAL_REQUIREMENTS` | If set to `1`, Kraken CLI will always run an update on local requirements in the project's requirement spec, even if the build environment already exists and appears to be up to date. |

> Note: Currently, the source directory of the kraken-cli project is derived by following the symlink of the
> `kraken/cli/__init__.py` file and then looking four directories up (cli, kraken, src, kraken-cli project root).
> This assumption is made based on how symlink installs work with `slap link` or `slap install --link`.
