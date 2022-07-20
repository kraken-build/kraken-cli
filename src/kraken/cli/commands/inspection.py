from __future__ import annotations

import argparse
import sys
from typing import Any

from kraken.core import Context, GroupTask, Property, Task, TaskGraph
from kraken.core.executor import COLORS_BY_STATUS, TaskStatus, get_task_status
from termcolor import colored

from .base import BuildGraphCommand, print


class LsCommand(BuildGraphCommand):
    """list targets in the build"""

    class Args(BuildGraphCommand.Args):
        default: bool
        all: bool

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument(
            "-d",
            "--default",
            action="store_true",
            help="trim non-default tasks (only without selected targets)",
        )

    def resolve_tasks(self, args: Args, context: Context) -> list[Task]:  # type: ignore
        tasks: list[Task] = []
        if args.default:
            if args.targets:
                self.get_parser().error("cannot combine -d,--default with target selection")
            for project in context.iter_projects():
                for task in project.tasks().values():
                    if task.default:
                        tasks.append(task)
            return tasks
        if args.targets:
            return context.resolve_tasks(args.targets)
        for project in context.iter_projects():
            tasks += project.tasks().values()
        return tasks

    def execute_with_graph(self, context: Context, graph: TaskGraph, args: BuildGraphCommand.Args) -> None:
        if len(graph) == 0:
            print("no tasks.", file=sys.stderr)
            sys.exit(1)

        longest_name = max(map(len, (task.path for task in graph.tasks()))) + 1
        print(colored("D " + "Task".ljust(longest_name + 1) + "Type", attrs=["bold"]))
        for task in graph.execution_order():
            print(
                colored("●", "cyan" if task.default else "grey"),
                task.path.ljust(longest_name),
                type(task).__module__ + "." + type(task).__name__,
            )


class QueryCommand(BuildGraphCommand):
    """perform queries on the build graph"""

    class Args(BuildGraphCommand.Args):
        is_up_to_date: bool
        legend: bool

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("--legend", action="store_true", help="print out a legend along with the query result")
        parser.add_argument("--is-up-to-date", action="store_true", help="query if the selected task(s) are up to date")

    def execute(self, args: BuildGraphCommand.Args) -> int | None:  # type: ignore[override]
        args.quiet = True
        return super().execute(args)

    def execute_with_graph(self, context: Context, graph: TaskGraph, args: Args) -> int | None:  # type: ignore
        if args.is_up_to_date:
            tasks = list(graph.tasks(required_only=True))
            print(f"querying status of {len(tasks)} task(s)")
            print()

            need_to_run = 0
            up_to_date = 0
            for task in graph.execution_order():
                if task not in tasks:
                    continue
                status = get_task_status(task)
                print(" ", task.path, colored(status.name, COLORS_BY_STATUS[status]))
                if status in (TaskStatus.SKIPPABLE, TaskStatus.UP_TO_DATE):
                    up_to_date += 1
                else:
                    need_to_run += 1

            print()
            print(colored(f"{up_to_date} task(s) are up to date, need to run {need_to_run} task(s)", attrs=["bold"]))

            if args.legend:
                print()
                print("legend:")
                help_text = {
                    TaskStatus.SKIPPABLE: "the task reports that it can and will be skipped",
                    TaskStatus.UP_TO_DATE: "the task reports that it is up to date",
                    TaskStatus.OUTDATED: "the task reports that it is outdated",
                    TaskStatus.QUEUED: "the task needs to run always or it cannot determine its up to date status",
                }
                for status in TaskStatus:
                    print(colored(status.name.rjust(12), COLORS_BY_STATUS[status]) + ":", help_text[status])

            exit_code = 0 if need_to_run == 0 else 1
            print()
            print("exit code:", exit_code)
            sys.exit(exit_code)

        else:
            self.get_parser().error("missing query")


class DescribeCommand(BuildGraphCommand):
    """describe one or more tasks in detail"""

    def execute_with_graph(self, context: Context, graph: TaskGraph, args: BuildGraphCommand.Args) -> None:
        tasks = context.resolve_tasks(args.targets)
        print("selected", len(tasks), "task(s)")
        print()

        for task in tasks:
            print("Group" if isinstance(task, GroupTask) else "Task", colored(task.path, attrs=["bold", "underline"]))
            print("  Type".ljust(30), type(task).__module__ + "." + type(task).__name__)
            print("  File".ljust(30), colored(sys.modules[type(task).__module__].__file__ or "???", "cyan"))
            print("  Default".ljust(30), task.default)
            print("  Capture".ljust(30), task.capture)
            rels = list(task.get_relationships())
            print("  Relationships".ljust(30), len(rels))
            for rel in rels:
                print(
                    "".ljust(4),
                    colored(rel.other_task.path, attrs=["bold"]),
                    f"before={rel.before}, strict={rel.strict}",
                )
            print("  Properties".ljust(30), len(type(task).__schema__))
            for key in type(task).__schema__:
                prop: Property[Any] = getattr(task, key)
                print("".ljust(4), colored(key, attrs=["reverse"]), f'= {colored(prop.get_or("<unset>"), "blue")}')
            print()
