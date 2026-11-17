"""Dispatch-failure contract: no invented child facts, policy and caller callback."""
import threading
import pytest
from command_execution import ChainCoordinator, CommandPlanner, RawOutcome
import command_execution.execution as execution


@pytest.mark.parametrize('all_threads', [False, True])
@pytest.mark.parametrize('stage', ['construct', 'start'])
@pytest.mark.parametrize('policy', ['stop', 'continue'])
def test_worker_dispatch_failure_is_a_completed_outcome(monkeypatch, stage, policy, all_threads):
    plan, issues = CommandPlanner().compile({'commands': [
        dict(id='background', argv=['never'], execution='async', on_error=policy),
        dict(id='successor', argv=['next'], execution='sync')]})
    assert not issues
    launched, callbacks, interpreted = [], [], []
    class Coordinator(ChainCoordinator):
        def _run_process(self, spec, stdin, chunk, coordinator):
            launched.append(spec.id)
            return RawOutcome(spec.argv, 0, b'ok', b'')
    def interpret(raw, spec):
        interpreted.append(spec.id)
        return dict(success=True, value=None, error=None)
    real = threading.Thread
    def factory(*args, **kwargs):
        if all_threads or kwargs.get('target').__name__ == 'execute':
            if stage == 'construct':
                raise RuntimeError('dispatch unavailable')
            worker = real(*args, **kwargs)
            def fail():
                raise RuntimeError('dispatch unavailable')
            worker.start = fail
            return worker
        return real(*args, **kwargs)
    monkeypatch.setattr(execution.threading, 'Thread', factory)
    caller = threading.get_ident()
    run = Coordinator(plan, interpreter=interpret).dispatch({'n': 1},
        on_result=lambda row: callbacks.append((threading.get_ident(), row)))
    result = run.wait()
    failed = result.commands[0]
    assert failed.state == 'dispatch_failed'
    assert failed.raw is None
    assert failed.input == {'n': 1}
    assert failed.interpretation == dict(success=False, value=None, error=failed.error)
    assert failed.error == dict(stage='dispatch', command_id='background',
        type='RuntimeError', message='dispatch unavailable')
    assert callbacks[0] == (caller, failed)
    assert launched == interpreted == (['successor'] if policy == 'continue' else [])
    assert result.commands[1].state == ('finished' if policy == 'continue' else 'not_attempted')
    assert result.status == run.dispatch_snapshot()['status'] == 'failed'
    assert result.error == failed.error
    assert result.infrastructure_errors == result.observer_errors == result.delivery_errors == []
    assert result.data == {'n': 1}
