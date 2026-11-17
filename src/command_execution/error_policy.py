"""Stateless stop/continue decisions on interpreted outcomes."""
from .command_model import CommandOutcome


class ErrorPolicy:
    def should_stop(self, on_error, outcome):
        if on_error not in ('stop', 'continue'):
            raise ValueError('Unknown command error policy')
        interpretation = outcome.get('interpretation', {}) if isinstance(outcome, dict) else outcome.interpretation
        return on_error == 'stop' and interpretation.get('success') is not True
