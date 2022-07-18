# Welcome to the Kraken CLI documentation!

  [Kraken]: https://pypi.org/project/kraken-build/

Kraken CLI is the command-line interface for the [Kraken][] build system. 

It's responsibilities are

* executing build scripts to generate a build graph
* allow you to inspect and execute tasks in the build graph
* manage a separate Python virtual environment with build time dependencies to ensure consistent, repeatable builds (see [Build Environment](./buildenv.md))

## Synopsis

``` title="$ kraken --help"
@shell kraken --help | sed -r "s/\x1B\[([0-9]{1,3}(;[0-9]{1,2})?)?[mGK]//g"
```

``` title="$ kraken env --help"
@shell kraken env --help | sed -r "s/\x1B\[([0-9]{1,3}(;[0-9]{1,2})?)?[mGK]//g"
```
