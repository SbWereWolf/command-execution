"""Shared dispatch serialization and complete source-ordered callable outcomes."""
from concurrent.futures import ThreadPoolExecutor
import threading
from .command_model import CallOutcome, CallListResult
from .results import MemoryResultStore
from .error_policy import ErrorPolicy


class ListCoordinator:
    def __init__(self, store=None, error_policy=None):
        self.store = store if store is not None else MemoryResultStore()
        self.error_policy = error_policy if error_policy is not None else ErrorPolicy()
        self.lock = threading.RLock()
        self.halted = False

    def start(self, launch):
        with self.lock:
            if self.halted:
                return None
            return launch()

    def observe(self, policy, outcome):
        with self.lock:
            if self.error_policy.should_stop(policy, outcome):
                self.halted = True

    def stop(self):
        with self.lock:
            self.halted = True


class CallListRunner:
    def run(self, calls, max_workers=32):
        if type(max_workers) is not int or max_workers < 1:
            raise ValueError('max_workers must be positive')
        coordinator = ListCoordinator()

        def invoke(index, call):
            try:
                outcome = CallOutcome(index, value=call())
            except BaseException as error:
                outcome = CallOutcome(index, error=error)
            coordinator.store.record_outcome(index, outcome)

        if calls:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = [coordinator.start(lambda i=i, call=call: pool.submit(invoke, i, call))
                           for i, call in enumerate(calls)]
                for future in futures:
                    future.result()
        outcomes = coordinator.store.outcomes()
        first = next((row.error for row in outcomes if row.error is not None), None)
        return CallListResult(outcomes, first)
