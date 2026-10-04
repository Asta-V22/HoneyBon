"""Turn a Pydantic model into the JSON Schema subset that provider structured-output modes accept.

Providers reject length/number constraints and some reject `$ref`, so this inlines references,
drops unsupported keywords, closes every object, and marks every property required (optional
fields stay nullable). The server still validates the full Pydantic model afterwards, so nothing
the provider is not told is ever trusted.
"""

from typing import Any

from pydantic import BaseModel

_DROP = {
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "pattern",
    "default",
    "title",
    "uniqueItems",
}


def provider_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})
    return _clean(schema, defs)


def _clean(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, list):
        return [_clean(item, defs) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        target = defs[node["$ref"].rsplit("/", 1)[-1]]
        merged = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
        return _clean(merged, defs)

    out = {k: _clean(v, defs) for k, v in node.items() if k not in _DROP and k != "properties"}
    if "properties" in node:
        # Keys here are field names, not keywords: a field may be called "pattern" or "title".
        out["properties"] = {name: _clean(sub, defs) for name, sub in node["properties"].items()}
    if out.get("type") == "object" or "properties" in out:
        out["type"] = "object"
        out["additionalProperties"] = False
        out["required"] = list(out.get("properties", {}))
    return out
