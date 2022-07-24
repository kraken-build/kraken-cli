from __future__ import annotations

import argparse
import io
import sys
from typing import Any

from kraken.core import Context, GroupTask, Property, Task, TaskGraph, TaskStatus, TaskStatusType
from kraken.core.executor import COLORS_BY_RESULT
from nr.io.graphviz.render import render_to_browser
from nr.io.graphviz.writer import GraphvizWriter
from termcolor import colored

from .base import BuildGraphCommand, print


class LsCommand(BuildGraphCommand):
    """list all tasks"""

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

    def execute_with_graph(self, context: Context, graph: TaskGraph, args: BuildGraphCommand.Args) -> None:
        if len(graph) == 0:
            print("no tasks.", file=sys.stderr)
            sys.exit(1)

        required_tasks = set(graph.tasks(targets_only=True))
        longest_name = max(map(len, (t.path for t in graph.tasks(all=True)))) + 1

        print()
        print(colored("Tasks", "blue", attrs=["bold", "underline"]))
        print()

        def _print_task(task: Task) -> None:
            line = [task.path.ljust(longest_name)]
            if task in required_tasks:
                line[0] = colored(line[0], "green")
            if task.default:
                line[0] = colored(line[0], attrs=["bold"])
            status = graph.get_status(task)
            if status is not None:
                line.append(f"[{colored(status.type.name, COLORS_BY_RESULT[status.type])}]")
            if task.description:
                line.append(task.description)
            print("  " + " ".join(line))

        for task in graph.tasks(all=True):
            if isinstance(task, GroupTask):
                continue
            _print_task(task)

        print()
        print(colored("Groups", "blue", attrs=["bold", "underline"]))
        print()

        for task in graph.tasks(all=True):
            if not isinstance(task, GroupTask):
                continue
            _print_task(task)

        print()


class IsUpToDateCommand(BuildGraphCommand):
    """ask if the specified targets are up to date."""

    class Args(BuildGraphCommand.Args):
        is_up_to_date: bool
        legend: bool

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("--legend", action="store_true", help="print out a legend along with the query result")

    def execute(self, args: BuildGraphCommand.Args) -> int | None:  # type: ignore[override]
        args.quiet = True
        return super().execute(args)

    def execute_with_graph(self, context: Context, graph: TaskGraph, args: Args) -> int | None:  # type: ignore
        tasks = list(graph.tasks(targets_only=True))
        print(f"querying status of {len(tasks)} task(s)")
        print()

        need_to_run = 0
        up_to_date = 0
        for task in graph.execution_order():
            if task not in tasks:
                continue
            status = task.prepare() or TaskStatus.pending()
            print(" ", task.path, colored(status.type.name, COLORS_BY_RESULT[status.type]))
            if status.is_skipped() or status.is_up_to_date():
                up_to_date += 1
            else:
                need_to_run += 1

        print()
        print(colored(f"{up_to_date} task(s) are up to date, need to run {need_to_run} task(s)", attrs=["bold"]))

        if args.legend:
            print()
            print("legend:")
            help_text = {
                TaskStatusType.PENDING: "the task is pending execution",
                TaskStatusType.SKIPPED: "the task can be skipped",
                TaskStatusType.UP_TO_DATE: "the task is up to date",
            }
            for status_type, help in help_text.items():
                print(colored(status_type.name.rjust(12), COLORS_BY_RESULT[status_type]) + ":", help)

        exit_code = 0 if need_to_run == 0 else 1
        print()
        print("exit code:", exit_code)
        sys.exit(exit_code)


class DescribeCommand(BuildGraphCommand):
    """describe one or more tasks in detail"""

    def execute_with_graph(self, context: Context, graph: TaskGraph, args: BuildGraphCommand.Args) -> None:
        tasks = context.resolve_tasks(args.targets)
        print("selected", len(tasks), "task(s)")
        print()

        for task in tasks:
            print("Group" if isinstance(task, GroupTask) else "Task", colored(task.path, attrs=["bold", "underline"]))
            print("  Type:", type(task).__module__ + "." + type(task).__name__)
            print("  Type defined in:", colored(sys.modules[type(task).__module__].__file__ or "???", "cyan"))
            print("  Default:", task.default)
            print("  Capture:", task.capture)
            rels = list(task.get_relationships())
            print(colored("  Relationships", attrs=["bold"]), f"({len(rels)})")
            for rel in rels:
                print(
                    "".ljust(4),
                    colored(rel.other_task.path, "blue"),
                    f"before={rel.inverse}, strict={rel.strict}",
                )
            print("  " + colored("Properties", attrs=["bold"]) + f" ({len(type(task).__schema__)})")
            longest_property_name = max(map(len, type(task).__schema__.keys())) if type(task).__schema__ else 0
            for key in type(task).__schema__:
                prop: Property[Any] = getattr(task, key)
                print(
                    "".ljust(4),
                    (key + ":").ljust(longest_property_name + 1),
                    f'{colored(prop.get_or("<unset>"), "blue")}',
                )
            print()


class VizCommand(BuildGraphCommand):
    """GraphViz for the task graph"""

    class Args(BuildGraphCommand.Args):
        default: bool
        trim: bool
        show: bool

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("-s", "--show", action="store_true", help="show the graph in the browser (requires `dot`)")

    def execute_with_graph(self, context: Context, graph: TaskGraph, args: Args) -> None:  # type: ignore[override]
        buffer = io.StringIO()
        writer = GraphvizWriter(buffer if args.show else sys.stdout)
        writer.digraph(fontname="monospace")
        writer.set_node_style(style="filled", shape="box")

        for task in graph.execution_order():
            writer.node(
                task.path,
                color="green" if task.default else "gray20",
                fillcolor="dodgerblue1" if isinstance(task, GroupTask) else "aquamarine",
            )
            for predecessor in graph.get_predecessors(task):
                writer.edge(predecessor.path, task.path)

        writer.end()

        if args.show:
            render_to_browser(buffer.getvalue())
