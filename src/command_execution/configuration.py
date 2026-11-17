"""Pure command compilation and tolerant, named stream selections."""
from copy import deepcopy
from dataclasses import dataclass
from enum import IntFlag
import re
from .command_model import CommandPlan, CommandSpec
from .parameters import TemplateRenderer


class OutputStreams(IntFlag):
    NONE = 0
    STD_ERR = 1
    STD_OUT = 2
    ALL = STD_ERR | STD_OUT


@dataclass(frozen=True)
class ConfigurationIssue:
    command_index: int | None
    field: str
    element_index: int | None
    code: str
    value: object = None


class OutputSelection:
    def parse(self, value, mode='normal', path=''):
        flags = OutputStreams.NONE
        issues = []
        match = re.match(r'commands\[(\d+)\]\.(.+)', path)
        index, name = (int(match[1]), match[2]) if match else (None, path)
        valid = {'std-err': OutputStreams.STD_ERR, 'std-out': OutputStreams.STD_OUT}
        if not isinstance(value, list):
            if mode in ('validate', 'test'):
                issues.append(ConfigurationIssue(index, name, None, 'selector_not_array', value))
            return flags, issues
        seen = set()
        for offset, item in enumerate(value):
            if not isinstance(item, str) or item not in valid or item in seen:
                if mode in ('validate', 'test'):
                    issues.append(ConfigurationIssue(index, name, offset, 'ignored_selector', item))
                continue
            seen.add(item)
            flags |= valid[item]
        return flags, issues


class CommandPlanner:
    def compile(self, document, parameters=None, profile='resolved', validation=False):
        parameters = deepcopy(parameters or {})
        issues, commands, identifiers = [], [], set()
        if not isinstance(document, dict) or not isinstance(document.get('commands'), list):
            return None, [ConfigurationIssue(None, 'commands', None, 'commands_not_array')]
        structural = False
        renderer, selections = TemplateRenderer(), OutputSelection()
        deferred = tuple(document.get('deferred', ()))
        for index, original in enumerate(document['commands']):
            if not isinstance(original, dict):
                issues.append(ConfigurationIssue(index, 'command', None, 'command_not_object', original))
                structural = True
                continue
            try:
                row = renderer.render(original, parameters, profile, deferred=deferred)
            except (KeyError, ValueError) as error:
                issues.append(ConfigurationIssue(index, 'parameters', None, 'unresolved_parameter', str(error)))
                structural = True
                continue
            identifier = row.get('id', 'command-' + str(index))
            argv = row.get('argv')
            order, execution, on_error = row.get('order', index), row.get('execution', 'sync'), row.get('on_error', 'stop')
            valid = True
            for name, condition in [('id', isinstance(identifier, str) and bool(identifier) and identifier not in identifiers),
                    ('argv', isinstance(argv, list) and bool(argv) and all(isinstance(value, str) for value in argv)),
                    ('order', type(order) is int), ('execution', execution in ('sync', 'async')),
                    ('on_error', on_error in ('stop', 'continue'))]:
                if not condition:
                    issues.append(ConfigurationIssue(index, name, None, 'invalid_' + name, row.get(name)))
                    valid = False
            if isinstance(identifier, str):
                identifiers.add(identifier)
            masks = []
            for name in ('batch-mode', 'sync-mode'):
                flags, errors = selections.parse(row.get(name, []), mode='validate' if validation else 'normal',
                                                  path='commands[' + str(index) + '].' + name)
                masks.append(flags)
                issues.extend(errors)
            if valid:
                commands.append(CommandSpec(identifier, deepcopy(argv), index, order, execution, on_error,
                                            *masks, deepcopy(row)))
            else:
                structural = True
        if structural:
            return None, issues
        return CommandPlan(sorted(commands, key=lambda row: (row.order, row.source_index)), parameters, profile, deferred), issues
