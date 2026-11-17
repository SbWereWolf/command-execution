"""Pure JSON values with explicit compatibility profiles."""
import json
import math


def js_number(value):
    number = float(value)
    if not math.isfinite(number):
        return "null"
    if number == 0:
        return "0"
    sign = "-" if number < 0 else ""
    text = repr(abs(number)).lower()
    mantissa, _, exponent = text.partition("e")
    before, _, after = mantissa.partition(".")
    position = len(before) + (int(exponent) if exponent else 0)
    digits = before + after
    while digits.startswith("0"):
        digits = digits[1:]
        position -= 1
    digits = digits.rstrip("0") or "0"
    if 0 < position <= 21:
        if position >= len(digits):
            result = digits + "0" * (position - len(digits))
        else:
            result = digits[:position] + "." + digits[position:]
    elif -6 < position <= 0:
        result = "0." + "0" * -position + digits
    else:
        exponent = position - 1
        result = digits[0] + ("." + digits[1:] if len(digits) > 1 else "")
        result += "e" + ("+" if exponent >= 0 else "-") + str(abs(exponent))
    return sign + result


def _quote(value):
    text = json.dumps(value, ensure_ascii=False)
    return "".join(f"\\u{ord(char):04x}" if 0xD800 <= ord(char) <= 0xDFFF else char for char in text)


def stringify(value, *, indent=None, canonical=False):
    """ECMAScript JSON value encoding, including UTF16 canonical key sorting."""
    def encode(item, level):
        if item is None:
            return "null"
        if type(item) is bool:
            return "true" if item else "false"
        if isinstance(item, (int, float)):
            return js_number(item)
        if isinstance(item, str):
            return _quote(item)
        if isinstance(item, (list, dict)):
            if isinstance(item, dict):
                keys = list(item)
                if any(not isinstance(key, str) for key in keys):
                    raise ValueError("JSON object keys must be strings")
                if canonical:
                    keys.sort(key=lambda key: key.encode("utf-16-be", errors="surrogatepass"))
                else:
                    indices = [key for key in keys if key.isascii() and key.isdecimal()
                               and str(int(key)) == key and int(key) < 4294967295]
                    keys = sorted(indices, key=int) + [key for key in keys if key not in indices]
                entries = [_quote(key) + (": " if indent else ":") + encode(item[key], level + 1) for key in keys]
                left, right = "{", "}"
            else:
                entries = [encode(value, level + 1) for value in item]
                left, right = "[", "]"
            if not entries:
                return left + right
            if indent:
                gap = " " * indent
                return left + "\n" + gap * (level + 1) + (",\n" + gap * (level + 1)).join(entries) + "\n" + gap * level + right
            return left + ",".join(entries) + right
        raise ValueError(f"Unsupported JSON type: {type(item).__name__}")
    return encode(value, 0)


def _unique(pairs):
    document = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"Duplicate JSON key: {key}")
        document[key] = value
    return document


def _wr_integer(token):
    number = float(token)
    if token == "-0":
        return -0.0
    return int(number) if math.isfinite(number) else number


def loads(text, profile):
    if profile == "ce-object-v1":
        value = json.loads(text, object_pairs_hook=_unique)
        if not isinstance(value, dict):
            raise ValueError("Expected JSON object")
        return value
    if profile == "wr-json-v1":
        def reject(token):
            raise ValueError(f"Invalid JSON constant: {token}")
        return json.loads(text, parse_int=_wr_integer, parse_constant=reject)
    raise ValueError(f"Unknown JSON read profile: {profile}")


class JSONCodec:
    def __init__(self, profile='ce-object-v1'):
        if profile not in ('ce-object-v1','wr-json-v1'):
            raise ValueError('Unknown JSON profile: '+str(profile))
        self.profile=profile

    def loads(self, text):
        return loads(text,self.profile)

    def dumps(self, value, *, indent=None, canonical=False):
        if self.profile=='wr-json-v1':
            return stringify(value,indent=indent,canonical=canonical)
        return json.dumps(value,ensure_ascii=False,indent=indent,sort_keys=canonical,allow_nan=False)
