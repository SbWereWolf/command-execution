"""Immutable-style ordered collections inside complete JSON documents."""
from copy import deepcopy
import jsonpatch


class DocumentCollection:
    def __init__(self, document, array_name, id_field='id'):
        if not isinstance(document, dict):
            raise ValueError('Expected a complete JSON object')
        if not isinstance(document.get(array_name), list):
            raise ValueError('Expected declared collection array')
        self._document = deepcopy(document)
        self.array_name, self.id_field = array_name, id_field
        identifiers = []
        for row in self._document[array_name]:
            identifier = row.get(id_field) if isinstance(row, dict) else None
            if not isinstance(identifier, str) or not identifier or identifier in identifiers:
                raise ValueError('Collection IDs must be unique nonempty strings')
            identifiers.append(identifier)

    def document(self):
        return deepcopy(self._document)

    def ids(self):
        return [row[self.id_field] for row in self._document[self.array_name]]

    def select(self, identifiers=None):
        if identifiers is None or identifiers == 'all':
            return deepcopy(self._document[self.array_name])
        if isinstance(identifiers, str):
            identifiers = [identifiers]
        rows = {row[self.id_field]: row for row in self._document[self.array_name]}
        try:
            return [deepcopy(rows[identifier]) for identifier in identifiers]
        except KeyError as error:
            raise ValueError('Unknown collection ID: ' + str(error)) from error

    def _with_rows(self, rows):
        document = self.document()
        document[self.array_name] = rows
        return type(self)(document, self.array_name, self.id_field)

    def add(self, row):
        return self._with_rows([*self.select(), deepcopy(row)])

    def replace(self, identifier, row):
        if identifier not in self.ids():
            raise ValueError('Unknown collection ID')
        return self._with_rows([deepcopy(row) if value[self.id_field] == identifier else value
                                for value in self.select()])

    def delete(self, identifier):
        if identifier not in self.ids():
            raise ValueError('Unknown collection ID')
        return self._with_rows([row for row in self.select() if row[self.id_field] != identifier])

    def clear(self):
        return self._with_rows([])

    def move(self, identifier, index):
        identifiers = self.ids()
        if identifier not in identifiers or type(index) is not int or not 0 <= index < len(identifiers):
            raise ValueError('Invalid move')
        identifiers.remove(identifier)
        identifiers.insert(index, identifier)
        return self.reorder(identifiers)

    def reorder(self, identifiers):
        if not isinstance(identifiers, list) or len(identifiers) != len(self.ids()) or set(identifiers) != set(self.ids()):
            raise ValueError('Reorder requires an exact permutation')
        return self._with_rows(self.select(identifiers))

    def patch_child(self, identifier, operations):
        row = self.select([identifier])[0]
        try:
            changed = jsonpatch.apply_patch(row, operations, in_place=False)
            return self.replace(identifier, changed)
        except (jsonpatch.JsonPatchException, KeyError, TypeError) as error:
            raise ValueError('Invalid child patch: ' + str(error)) from error
