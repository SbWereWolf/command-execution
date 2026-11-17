"""Direct argv execution and coordination without operating-system policies."""
from copy import deepcopy
from dataclasses import replace
import json
import os
import subprocess
import threading
import uuid
from .command_model import RawOutcome, CommandOutcome, ChainResult
from .lists import ListCoordinator
from .results import MemoryResultStore, DispatchResultView
from .error_policy import ErrorPolicy
from .delivery import OutputDelivery


def error_record(error):
    return {'type': type(error).__name__, 'message': str(error)}


def _dataflow_snapshot(value):
    """Check the existing stdin encoding boundary before replacing chain data."""
    json.dumps(value, ensure_ascii=True, allow_nan=False)
    return deepcopy(value)


class _DispatchStopped(Exception):
    pass


class ProcessWorker:
    def _start(self, argv):
        return subprocess.Popen(argv, shell=False, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def run(self, argv, stdin=None, on_chunk=None):
        argv = list(argv)
        try:
            process = self._start(argv)
        except _DispatchStopped:
            raise
        except OSError as error:
            return RawOutcome(list(argv), None, launch_error=error_record(error))
        captured = {'out': [], 'err': []}
        errors = []

        def drain(stream, name):
            try:
                while True:
                    chunk = os.read(stream.fileno(), 65536)
                    if not chunk:
                        break
                    captured[name].append(chunk)
                    if on_chunk is not None:
                        try:
                            on_chunk(name, chunk)
                        except BaseException as error:
                            errors.append(error_record(error))
            except BaseException as error:
                errors.append(error_record(error))
            finally:
                stream.close()

        def feed():
            try:
                if stdin is not None:
                    process.stdin.write(stdin)
                    process.stdin.flush()
            except BrokenPipeError:
                pass
            except BaseException as error:
                errors.append(error_record(error))
            finally:
                try:
                    process.stdin.close()
                except BrokenPipeError:
                    pass

        readers = [threading.Thread(target=drain, args=(process.stdout, 'out')),
                   threading.Thread(target=drain, args=(process.stderr, 'err'))]
        writer = threading.Thread(target=feed)
        for thread in readers + [writer]:
            thread.start()
        code = process.wait()
        for thread in readers + [writer]:
            thread.join()
        return RawOutcome(list(argv), code, b''.join(captured['out']), b''.join(captured['err']),
                          transport_errors=errors)


class ChainRun:
    def __init__(self, view):
        self._view = view
        self._complete = threading.Event()
        self._result = None

    def dispatch_snapshot(self):
        return self._view.snapshot()

    def wait(self):
        self._complete.wait()
        return self._result


class ChainCoordinator:
    def __init__(self, plan, store=None, error_policy=None, delivery=None, interpreter=None):
        self.plan = plan
        self.store = store if store is not None else MemoryResultStore()
        self.error_policy = error_policy if error_policy is not None else ErrorPolicy()
        self.delivery = delivery if delivery is not None else OutputDelivery(self.store)
        self.interpreter = interpreter

    def _run_process(self, spec, stdin, on_chunk, coordinator):
        class CoordinatedWorker(ProcessWorker):
            def _start(worker, argv):
                process = coordinator.start(lambda: super(CoordinatedWorker, worker)._start(argv))
                if process is None:
                    raise _DispatchStopped()
                return process
        return CoordinatedWorker().run(spec.argv, stdin, on_chunk)

    def dispatch(self, initial, on_result=None):
        coordinator = ListCoordinator(self.store, self.error_policy)
        run_id = str(uuid.uuid4())
        self.delivery.begin(run_id, self.plan.commands)
        view = DispatchResultView(self.store)
        run = ChainRun(view)
        workers, infrastructure, observers = [], [], []
        state_lock = threading.RLock()
        state = {'data': deepcopy(initial), 'failed': False}

        def fail(error, collection=infrastructure):
            with state_lock:
                collection.append(error_record(error))
                state['failed'] = True
            coordinator.stop()

        def not_attempted(spec, data):
            row = CommandOutcome(spec.id, spec.source_index, 'not_attempted', None, data, {})
            try:
                self.store.record_outcome(spec.source_index, row)
            except BaseException as error:
                fail(error)

        def execute(spec, data):
            def deliver_chunk(stream, chunk):
                try:
                    self.delivery.chunk(spec, stream, chunk)
                except BaseException as error:
                    fail(error)
                if self.delivery.errors:
                    coordinator.stop()

            try:
                stdin = json.dumps(data, ensure_ascii=True, allow_nan=False).encode('utf-8')
                raw = self._run_process(spec, stdin, deliver_chunk, coordinator)
            except _DispatchStopped:
                not_attempted(spec, data)
                return
            except BaseException as error:
                fail(error)
                return
            interpreted = None
            try:
                interpreted = self.interpreter(raw, spec) if self.interpreter else {
                    'success': raw.launch_error is None and raw.returncode == 0,
                    'value': None, 'error': raw.launch_error or (
                        None if raw.returncode == 0 else {'returncode': raw.returncode})}
                if not isinstance(interpreted, dict):
                    raise ValueError('Interpreter must return an object with success, value and error')
                missing = [name for name in ('success', 'value', 'error') if name not in interpreted]
                if missing:
                    raise ValueError('Interpreter result is missing required fields: ' + ', '.join(missing))
                if type(interpreted['success']) is not bool:
                    raise ValueError('Interpreter result success must be boolean')
            except BaseException as error:
                context = {'stage': 'interpretation', 'command_id': spec.id, **error_record(error)}
                if isinstance(interpreted, dict) and interpreted.get('error') is not None:
                    context['previous_error'] = interpreted['error']
                interpreted = {'success': False, 'value': None,
                    'error': context}
            advance = False
            if spec.execution == 'sync' and 'next_input' in interpreted:
                try:
                    next_data = _dataflow_snapshot(interpreted['next_input'])
                    advance = True
                except BaseException as error:
                    if not isinstance(error, (TypeError, ValueError, RecursionError, OverflowError)):
                        fail(error)
                    context = {'stage': 'next_input', 'command_id': spec.id,
                               **error_record(error)}
                    if interpreted['error'] is not None:
                        context['previous_error'] = interpreted['error']
                    interpreted = {**interpreted, 'success': False, 'error': context}
                    interpreted.pop('next_input', None)
            row = CommandOutcome(spec.id, spec.source_index,
                'launch_failed' if raw.launch_error else 'finished', raw, data,
                interpreted, interpreted.get('error'))
            with state_lock:
                state['failed'] = state['failed'] or not interpreted['success']
                if advance:
                    state['data'] = next_data
            coordinator.observe(spec.on_error, row)
            try:
                self.store.record_outcome(spec.source_index, row)
            except BaseException as error:
                fail(error)
            if raw.transport_errors:
                with state_lock:
                    infrastructure.extend(raw.transport_errors)
                    state['failed'] = True
                coordinator.stop()
            if self.delivery.errors:
                coordinator.stop()
            if on_result is not None:
                try:
                    on_result(row)
                except BaseException as error:
                    fail(error, observers)

        for spec in self.plan.commands:
            with state_lock:
                data = deepcopy(state['data'])
            if coordinator.halted:
                not_attempted(spec, data)
            elif spec.execution == 'async':
                worker = threading.Thread(target=execute, args=(spec, data))
                workers.append(worker)
                worker.start()
            else:
                execute(spec, data)
        with state_lock:
            view.freeze(status='failed' if state['failed'] else 'succeeded',
                        data=state['data'], error=(infrastructure + observers or [None])[0])

        def finish():
            try:
                for worker in workers:
                    worker.join()
                try:
                    self.delivery.replay()
                except BaseException as error:
                    fail(error)
                try:
                    outcomes = self.store.outcomes()
                except BaseException as error:
                    fail(error)
                    outcomes = []
                with state_lock:
                    errors = infrastructure + observers + self.delivery.errors
                    result = ChainResult('failed' if state['failed'] or errors else 'succeeded',
                        outcomes, deepcopy(state['data']), errors[0] if errors else next(
                            (row.error for row in outcomes if row.error), None),
                        list(infrastructure), list(observers), list(self.delivery.errors))
                self.delivery.terminal(result)
                if self.delivery.errors != result.delivery_errors:
                    result = replace(result, status='failed',
                        error=result.error or self.delivery.errors[0],
                        delivery_errors=list(self.delivery.errors))
                run._result = result
            finally:
                run._complete.set()
        threading.Thread(target=finish).start()
        return run

    def run(self, initial, on_result=None):
        return self.dispatch(initial, on_result).wait()
