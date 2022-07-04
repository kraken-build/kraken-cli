from __future__ import annotations

import contextlib
import dataclasses
import logging
import os
import sys
import traceback

# from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import IO, AnyStr, Iterator

from kraken.core.action import ActionResult
from kraken.core.build_graph import BuildGraph
from kraken.core.task import AnyTask, TaskCaptureMode
from termcolor import colored

logger = logging.getLogger(__name__)


def get_terminal_width(default: int = 80) -> int:
    """Returns the terminal width through :func:`os.get_terminal_size`, falling back to the `COLUMNS`
    environment variable. If neither is available, return *default*."""

    try:
        terminal_width = os.get_terminal_size().columns
    except OSError:
        try:
            terminal_width = int(os.getenv("COLUMNS", ""))
        except ValueError:
            terminal_width = default
    return terminal_width


@contextlib.contextmanager
def replace_stdio(
    stdin: IO[AnyStr] | None = None,
    stdout: IO[AnyStr] | None = None,
    stderr: IO[AnyStr] | None = None,
) -> Iterator[None]:
    """Temporarily replaces the file handles of stdin/sdout/stderr."""

    stdin_save: int | None = None
    stdout_save: int | None = None
    stderr_save: int | None = None

    if stdin is not None:
        stdin_save = os.dup(sys.stdin.fileno())
        os.dup2(stdin.fileno(), sys.stdin.fileno())
    if stdout is not None:
        stdout_save = os.dup(sys.stdout.fileno())
        os.dup2(stdout.fileno(), sys.stdout.fileno())
    if stderr is not None:
        stderr_save = os.dup(sys.stderr.fileno())
        os.dup2(stderr.fileno(), sys.stderr.fileno())

    try:
        yield
    finally:
        if stdin_save is not None:
            os.dup2(stdin_save, sys.stdin.fileno())
        if stdout_save is not None:
            os.dup2(stdout_save, sys.stdout.fileno())
        if stderr_save is not None:
            os.dup2(stderr_save, sys.stderr.fileno())


@dataclasses.dataclass
class ExecutionResult:
    status: ActionResult
    message: str | None
    output: str


def _execute_task_inner(task: AnyTask) -> tuple[ActionResult, str]:
    if not task.action:
        return ActionResult.SKIPPED, ""
    result = task.action.execute()
    return result, ""


def _execute_task(task: AnyTask, capture: bool) -> ExecutionResult:
    status = ActionResult.FAILED
    message = "unknown error"
    output = ""
    with contextlib.ExitStack() as exit_stack:
        if capture:
            fp = exit_stack.enter_context(NamedTemporaryFile(delete=False))
            exit_stack.enter_context(replace_stdio(None, fp, fp))
        try:
            status, message = _execute_task_inner(task)
        except BaseException as exc:
            status, message = ActionResult.FAILED, f"unhandled exception: {exc}"
            traceback.print_exc()
        finally:
            if capture:
                fp.close()
                output = Path(fp.name).read_text()
                os.remove(fp.name)
            else:
                output = ""
    if not isinstance(status, ActionResult):
        raise RuntimeError(f"{task}.action (= {task.action!r}) did not return ActionResult, got {status!r} instead")
    return ExecutionResult(status, message, output.rstrip())


class Executor:
    COLORS_BY_STATUS = {
        ActionResult.FAILED: "red",
        ActionResult.SKIPPED: "yellow",
        ActionResult.SUCCEEDED: "green",
        ActionResult.UP_TO_DATE: "green",
    }

    def __init__(self, graph: BuildGraph, verbose: bool = False) -> None:
        self.graph = graph
        self.verbose = verbose
        self.terminal_width = get_terminal_width()
        # self.pool = ProcessPoolExecutor()
        self.longest_task_id = max(len(task.path) for task in self.graph.execution_order())

    def execute_task(self, task: AnyTask) -> bool:
        if not task.action:
            result = ExecutionResult(ActionResult.SKIPPED, None, "")
        elif task.action.is_up_to_date():
            result = ExecutionResult(ActionResult.UP_TO_DATE, None, "")
        elif task.action.is_skippable():
            result = ExecutionResult(ActionResult.SKIPPED, None, "")
        else:
            print(">", task.path)
            if task.capture in (TaskCaptureMode.FULL, TaskCaptureMode.SEMI):
                # TODO (@NiklasRosenstein): Transfer values from output properties back to the main process.
                # TODO (@NiklasRosenstein): Until we actually start tasks in paralle, we don't benefit from
                #       using a ProcessPoolExecutor.
                # result = self.pool.submit(_execute_task, task, True).result()
                result = _execute_task(task, True)
            else:
                result = _execute_task(task, False)

        if (
            result.status == ActionResult.FAILED or task.capture == TaskCaptureMode.SEMI or self.verbose
        ) and result.output:
            print(result.output)

        print(
            ">",
            task.path,
            colored(result.status.name, self.COLORS_BY_STATUS[result.status], attrs=["bold"]),
            end="",
        )
        if result.message:
            print(f" ({result.message})", end="")
        print()

        return result.status != ActionResult.FAILED

    def execute(self) -> int:
        result = True
        # with self.pool:
        if True:
            for task in self.graph.execution_order():
                if not task.action:
                    continue
                result = self.execute_task(task)
                if not result:
                    break
        return 0 if result else 1
