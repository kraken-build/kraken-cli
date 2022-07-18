# Welcome to the Kraken CLI documentation!

  [Kraken]: https://pypi.org/project/kraken-build/

Kraken CLI is the command-line interface for the [Kraken][] build system. 

It's responsibilities are

* executing build scripts to generate a build graph
* allow you to inspect and execute tasks in the build graph
* manage a separate Python virtual environment with build time dependencies to ensure consistent, repeatable builds (see [Build Environment](./buildenv.md))

## Synopsis

```
$ kraken
usage: kraken [-h] [--version] [{run,fmt,lint,build,test,ls,query,describe,env}] ...

positional arguments:
  {run,fmt,lint,build,test,ls,query,describe,env}  the subcommand to execute
  ...                                              arguments for the subcommand

options:
  -h, --help                                       show this help message and exit
  --version                                        show program's version number and exit

subcommands:
  run                                              execute one or more kraken tasks
  fmt                                              execute "fmt" tasks
  lint                                             execute "lint" tasks
  build                                            execute "build" tasks
  test                                             execute "test" tasks
  ls                                               list targets in the build
  query                                            perform queries on the build graph
  describe                                         describe one or more tasks in detail
  env                                              manage the build environment
```

```
$ kraken env
usage: kraken env [-h] [{status,install,upgrade,lock,remove}] ...

positional arguments:
  {status,install,upgrade,lock,remove}  the subcommand to execute
  ...                                   arguments for the subcommand

options:
  -h, --help                            show this help message and exit

subcommands:
  status                                provide the status of the build environment
  install                               ensure the build environment is installed
  upgrade                               upgrade the build environment and lock file
  lock                                  create or update the lock file
  remove                                remove the build environment
```
