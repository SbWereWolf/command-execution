"""Detached recursive JSON edits; no persistence or execution responsibilities."""
from copy import deepcopy
import jsonpatch


class JSONMerger:
    def merge(self, base, overlay, profile='wr-recursive'):
        if isinstance(base, dict) and isinstance(overlay, dict):
            result = deepcopy(base)
            for key, value in overlay.items():
                result[key] = self.merge(result[key], value, profile) if key in result else deepcopy(value)
            return result
        return deepcopy(overlay)


class JSONPathEditor:
    def patch(self, value, operations):
        if not isinstance(operations, list):
            raise ValueError('changes must be an array')
        for index, change in enumerate(operations):
            if not isinstance(change, dict):
                raise ValueError(f'changes[{index}] must be an object')
            if change.get('op') not in ('add', 'replace', 'remove'):
                raise ValueError(f'changes[{index}].op is unsupported: {change.get("op")}')
            if not isinstance(change.get('path'), str):
                raise ValueError(f'changes[{index}].path must be a string')
        try:
            return jsonpatch.apply_patch(deepcopy(value), deepcopy(operations), in_place=False)
        except (jsonpatch.JsonPatchException, KeyError, TypeError) as error:
            raise ValueError(str(error)) from error

    def _parts(self, path, profile):
        if not isinstance(path, str):
            raise ValueError('JSON path must be a string')
        if profile == 'json-pointer':
            if path == '':
                return []
            if not path.startswith('/'):
                raise ValueError('JSON Pointer must start with /')
            return [part.replace('~1', '/').replace('~0', '~') for part in path[1:].split('/')]
        parts = path.split('.')
        if any(not part or part in ('__proto__', 'constructor', 'prototype') for part in parts):
            raise ValueError('Invalid dotted JSON path')
        return parts

    def _key(self, current, part, *, append=False):
        if isinstance(current, list):
            if append and part == '-':
                return len(current)
            if not part.isascii() or not part.isdigit() or str(int(part)) != part:
                raise ValueError('Invalid array index')
            index = int(part)
            if not 0 <= index < len(current) + int(append):
                raise ValueError('Array index outside bounds')
            return index
        if not isinstance(current, dict):
            raise ValueError('JSON path crosses a scalar')
        return part

    def get(self, value, path, *, profile='json-pointer'):
        current = value
        for part in self._parts(path, profile):
            current = current[self._key(current, part)]
        return deepcopy(current)

    def set(self, value, path, item, *, create_parents=True, profile='json-pointer'):
        parts = self._parts(path, profile)
        if not parts:
            return deepcopy(item)
        result = deepcopy(value)
        current = result
        for part in parts[:-1]:
            key = self._key(current, part)
            if isinstance(current, dict) and key not in current:
                if not create_parents:
                    raise KeyError(key)
                current[key] = {}
            current = current[key]
        key = self._key(current, parts[-1], append=True)
        if isinstance(current, list) and key == len(current):
            current.append(deepcopy(item))
        else:
            current[key] = deepcopy(item)
        return result

    def remove(self, value, path, *, profile='json-pointer'):
        parts = self._parts(path, profile)
        if not parts:
            return None
        result = deepcopy(value)
        current = result
        for part in parts[:-1]:
            current = current[self._key(current, part)]
        del current[self._key(current, parts[-1])]
        return result
