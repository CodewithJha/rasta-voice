"""Owned first-completed waits, and a structural check that they stay owned."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from rasta.tasks import first_completed, run_until_stopped

RASTA = Path(__file__).resolve().parents[1] / "rasta"
ALLOWED_TASK_CALLS = {("StreamSession.run", "asyncio.create_task")}


def test_first_completed_returns_the_first_result_and_cancels_the_rest():
    async def body():
        first, second = asyncio.Event(), asyncio.Event()
        first.set()
        index, result = await first_completed(first.wait(), second.wait())
        assert index == 0
        await asyncio.sleep(0)
        leftover = asyncio.all_tasks() - {asyncio.current_task()}
        assert leftover == set()

    asyncio.run(body())


def test_first_completed_times_out_without_leaving_tasks():
    async def body():
        hanging = asyncio.Event()
        index, result = await first_completed(hanging.wait(), timeout=0.05)
        assert index is None
        assert result is None
        await asyncio.sleep(0)
        leftover = asyncio.all_tasks() - {asyncio.current_task()}
        assert leftover == set()

    asyncio.run(body())


def test_first_completed_cancels_and_awaits_children_when_the_caller_is_cancelled():
    async def body():
        ev1, ev2 = asyncio.Event(), asyncio.Event()
        caller = asyncio.create_task(first_completed(ev1.wait(), ev2.wait()))
        await asyncio.sleep(0)
        children = [
            task
            for task in asyncio.all_tasks()
            if task is not asyncio.current_task() and task is not caller
        ]
        assert len(children) == 2
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        await asyncio.sleep(0)
        assert all(task.done() for task in children)
        leftover = asyncio.all_tasks() - {asyncio.current_task()}
        assert leftover == set()

    asyncio.run(body())


def test_run_until_stopped_ticks_then_exits_without_leaving_tasks():
    async def body():
        ticks = {"n": 0}
        stopped = asyncio.Event()

        def tick() -> None:
            ticks["n"] += 1
            if ticks["n"] >= 2:
                stopped.set()

        await run_until_stopped(tick, 0.05, stopped)
        await asyncio.sleep(0)
        leftover = asyncio.all_tasks() - {asyncio.current_task()}
        assert ticks["n"] >= 2
        assert leftover == set()

    asyncio.run(body())


def test_stream_session_does_not_create_tasks_outside_the_supervisor():
    source = (RASTA / "stream_session.py").read_text(encoding="utf-8")
    hits = _asyncio_task_calls(source)
    unexpected = [item for item in hits if (item[0], item[1]) not in ALLOWED_TASK_CALLS]
    assert hits, "expected StreamSession.run to spawn the sibling pumps"
    assert not unexpected, unexpected


def test_first_completed_is_the_only_other_production_task_factory():
    allowed_files = {"tasks.py"}
    found: list[str] = []
    for path in sorted((RASTA).glob("*.py")):
        if path.name in allowed_files:
            continue
        for owner, name, line in _asyncio_task_calls(path.read_text(encoding="utf-8")):
            if path.name == "stream_session.py" and (owner, name) in ALLOWED_TASK_CALLS:
                continue
            found.append(f"{path.name}:{line} {owner} {name}")
    assert found == []


def _asyncio_task_calls(source: str) -> list[tuple[str, str, int]]:
    names = {"create_task", "wait", "ensure_future"}
    hits: list[tuple[str, str, int]] = []

    class Finder(ast.NodeVisitor):
        def __init__(self) -> None:
            self.class_name: str | None = None
            self.func: str | None = None

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            previous = self.class_name
            self.class_name = node.name
            self.generic_visit(node)
            self.class_name = previous

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._in_func(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._in_func(node)

        def _in_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            previous = self.func
            self.func = node.name
            self.generic_visit(node)
            self.func = previous

        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "asyncio"
                and func.attr in names
            ):
                owner = self.func or "<module>"
                if self.class_name:
                    owner = f"{self.class_name}.{owner}"
                hits.append((owner, f"asyncio.{func.attr}", node.lineno))
            self.generic_visit(node)

    Finder().visit(ast.parse(source))
    return hits
