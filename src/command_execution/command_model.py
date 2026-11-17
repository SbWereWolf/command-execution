"""Neutral execution value records; services and consumers do not belong here."""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CommandSpec:
    id: str
    argv: list[str]
    source_index: int
    order: int
    execution: str
    on_error: str
    batch_mode: int
    sync_mode: int
    properties: dict


@dataclass(frozen=True)
class CommandPlan:
    commands: list[CommandSpec]
    parameters: dict = field(default_factory=dict)
    profile: str = 'resolved'
    deferred: tuple = ()


@dataclass(frozen=True)
class RawOutcome:
    argv: list[str]
    returncode: int | None
    stdout: bytes = b''
    stderr: bytes = b''
    launch_error: dict | None = None
    transport_errors: list = field(default_factory=list)

    @property
    def exit_code(self):
        return self.returncode


@dataclass(frozen=True)
class CommandOutcome:
    id: str
    source_index: int
    state: str
    raw: RawOutcome | None
    input: Any
    interpretation: dict
    error: Any = None


@dataclass(frozen=True)
class OutputChunk:
    run_id: str
    command_id: str
    message_id: str
    sequence: int
    stream: str
    data: bytes


@dataclass(frozen=True)
class ChainResult:
    status: str
    commands: list
    data: Any
    error: Any = None
    infrastructure_errors: list = field(default_factory=list)
    observer_errors: list = field(default_factory=list)
    delivery_errors: list = field(default_factory=list)

    @property
    def outcomes(self):
        return self.commands


@dataclass(frozen=True)
class CallOutcome:
    source_index: int
    value: Any = None
    error: BaseException | None = None


@dataclass(frozen=True)
class CallListResult:
    outcomes: list
    first_error: BaseException | None = None
