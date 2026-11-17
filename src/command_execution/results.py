"""Thread-safe evidence storage and explicitly frozen dispatch projections."""
from copy import deepcopy
import threading
from .command_model import OutputChunk


class ResultStore:
    def record_outcome(self, index, value):
        raise NotImplementedError

    def outcomes(self):
        raise NotImplementedError


class MemoryResultStore(ResultStore):
    def __init__(self):
        self._lock = threading.RLock()
        self._outcomes = {}
        self._chunks = []

    def record_outcome(self, index, value):
        with self._lock:
            self._outcomes[index] = value

    def outcomes(self):
        with self._lock:
            return [self._outcomes[index] for index in sorted(self._outcomes)]

    def record_chunk(self, run_id, command_id, stream, data):
        with self._lock:
            sequence = len(self._chunks)
            chunk = OutputChunk(run_id, command_id, run_id + ':' + str(sequence), sequence, stream, data)
            self._chunks.append(chunk)
            return chunk

    def chunks(self):
        with self._lock:
            return list(self._chunks)


class DispatchResultView:
    def __init__(self, store, projection=lambda value: value):
        self.store, self.projection = store, projection
        self._lock = threading.Lock()
        self._frozen = None

    def freeze(self, *, status, data, error):
        with self._lock:
            if self._frozen is not None:
                raise ValueError('Dispatch aggregate is already frozen')
            self._frozen = {'status': status, 'data': deepcopy(data), 'error': error}

    def snapshot(self):
        with self._lock:
            if self._frozen is None:
                raise ValueError('Dispatch aggregate is not frozen')
            return {**self._frozen, 'data': deepcopy(self._frozen['data']),
                    'commands': [self.projection(row) for row in self.store.outcomes()]}
