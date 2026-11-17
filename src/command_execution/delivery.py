"""Structured immediate publication, exact replay and one serialized JSONL writer."""
import base64
from dataclasses import fields, is_dataclass
import json
import queue
import threading
from .command_model import OutputChunk
from .results import ResultStore


def json_value(value):
    if is_dataclass(value):
        return {field.name: getattr(value, field.name) for field in fields(value)}
    if isinstance(value, bytes):
        return {'encoding': 'base64', 'data': base64.b64encode(value).decode('ascii')}
    if isinstance(value, BaseException):
        return {'type': type(value).__name__, 'message': str(value)}
    raise TypeError('Value is not representable in JSON: ' + type(value).__name__)


class JSONLWriter:
    def __init__(self, stream):
        self.stream = stream
        self._queue = queue.Queue()
        self._closed = False
        self._thread = threading.Thread(target=self._write_events, name='command-jsonl-writer')
        self._thread.start()

    def _write_events(self):
        while True:
            item = self._queue.get()
            if item is None:
                return
            event, finished, errors = item
            try:
                text = json.dumps(event, ensure_ascii=True, allow_nan=False, default=json_value) + '\n'
                self.stream.write(text)
                self.stream.flush()
            except BaseException as error:
                errors.append(error)
            finally:
                finished.set()

    def emit(self, event):
        if self._closed:
            raise RuntimeError('JSONL writer is closed')
        finished, errors = threading.Event(), []
        self._queue.put((event, finished, errors))
        finished.wait()
        if errors:
            raise errors[0]

    def close(self):
        if not self._closed:
            self._closed = True
            self._queue.put(None)
            self._thread.join()


class OutputDelivery:
    def __init__(self, store, emit=None):
        self.store, self.emit = store, emit
        self._lock = threading.RLock()
        self.errors = []
        self._commands = {}
        self.run_id = None

    def begin(self, run_id, commands):
        self.run_id = run_id
        self._commands = {command.id: command for command in commands}

    def _publish(self, event):
        with self._lock:
            if self.errors or self.emit is None:
                return
            try:
                self.emit(event)
            except BaseException as error:
                self.errors.append({'type': type(error).__name__, 'message': str(error)})

    @staticmethod
    def _selected(mask, stream):
        # Named constants live with the output contract. Avoid a service import
        # cycle by reading the actual named members from the supplied flag type.
        flags = type(mask)
        selected = flags.STD_OUT if stream == 'out' else flags.STD_ERR
        return bool(mask & selected)

    def _output(self, chunk, delivery):
        self._publish({'event': 'output', 'run_id': chunk.run_id,
            'command_id': chunk.command_id, 'message_id': chunk.message_id,
            'sequence': chunk.sequence, 'stream': chunk.stream, 'delivery': delivery,
            'encoding': 'base64', 'data': base64.b64encode(chunk.data).decode('ascii')})

    def chunk(self, command, stream, data):
        with self._lock:
            chunk = self.store.record_chunk(self.run_id, command.id, stream, data)
            if self._selected(command.sync_mode, stream):
                self._output(chunk, 'immediate')

    def replay(self):
        for chunk in self.store.chunks():
            if self._selected(self._commands[chunk.command_id].batch_mode, chunk.stream):
                self._output(chunk, 'batch')

    def terminal(self, result):
        self._publish({'event': 'result', 'run_id': self.run_id, 'result': result})
