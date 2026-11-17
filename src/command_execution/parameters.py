"""Typed parameter lookup, rendering and explicit consumption-time resolution."""
from copy import deepcopy
import re
from string import Template
from .json_codec import js_number

PATTERN = re.compile(r"\$\{([A-Za-z0-9_.-]+)\}")
RESERVED = {"__proto__", "constructor", "prototype"}


def js_string(value):
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return js_number(value)
    if isinstance(value, list):
        return ",".join("" if item is None else js_string(item) for item in value)
    if isinstance(value, dict):
        return "[object Object]"
    return str(value)


def _own_property(value, key):
    if isinstance(value, dict) and key in value:
        return value[key]
    if isinstance(value, list):
        if key == "length":
            return len(value)
        if len(key) <= 10 and re.fullmatch(r"0|[1-9][0-9]*", key, re.ASCII):
            index = int(key)
            if index < len(value):
                return value[index]
    raise KeyError(key)


def lookup(context, key, profile):
    parts = key.split(".")
    if any(part in RESERVED or not part for part in parts):
        raise ValueError(f"Unresolved value: {key}")
    if profile == "wr-workflow":
        if key not in context:
            raise KeyError(key)
        return context[key]
    current = context
    while parts:
        length = len(parts) if profile == "wr-flow" else 1
        while length:
            try:
                selected = _own_property(current, ".".join(parts[:length]))
                break
            except KeyError:
                length -= 1
        else:
            raise KeyError(key)
        current = selected
        parts = parts[length:]
    return current


def render(value, context, profile, *, deferred=(), missing=None):
    if profile == "resolved":
        return deepcopy(value)
    if isinstance(value, list):
        return [render(item, context, profile, deferred=deferred, missing=missing) for item in value]
    if isinstance(value, dict):
        return {key: render(item, context, profile, deferred=deferred, missing=missing) for key, item in value.items()}
    if not isinstance(value, str):
        return value
    if profile == "python-template":
        return Template(value).substitute(context)
    if profile not in ("wr-template", "wr-flow", "wr-workflow"):
        raise ValueError(f"Unknown parameter profile: {profile}")
    def resolve(match):
        key = match.group(1)
        if key in deferred:
            return match.group(0)
        try:
            return lookup(context, key, profile)
        except KeyError:
            if missing is None:
                raise ValueError(f"Unresolved value: {key}")
            missing.add(key)
            return match.group(0)
    full = PATTERN.fullmatch(value)
    if full and profile != "wr-workflow":
        return deepcopy(resolve(full))
    return PATTERN.sub(lambda match: js_string(resolve(match)), value)


class ParameterLookup:
    def resolve(self, context, key, profile='wr-template'):
        return deepcopy(lookup(context,key,profile))


class TemplateRenderer:
    def render(self, value, context, profile='wr-template', *, deferred=(), missing=None):
        return render(value,context,profile,deferred=deferred,missing=missing)


class DeferredResolver:
    def resolve_at_consumption(self, value, context, profile='wr-flow'):
        return render(value,context,profile)
