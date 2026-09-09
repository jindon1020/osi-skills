#!/usr/bin/env python3
"""Portable structural preflight and deterministic .awpkg builder."""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import stat
import sys
import zipfile
from collections import defaultdict, deque
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import yaml
except ImportError:  # Portable fallback: authoritative admission still remains required.
    yaml = None

WORKFLOW_PATH = "workflow.yml"
ALLOWED_PREFIXES = ("resources/references/", "resources/scripts/")
RESOURCE_PATTERN = re.compile(
    r"resources/(?:references|scripts)/[A-Za-z0-9_.@+-]+"
    r"(?:/[A-Za-z0-9_.@+-]+)*"
)
SPEC_PATTERN = re.compile(r"(?m)^spec:\s*agentos\.workflow/v3\s*$")
REMOVED_V2_FIELD_PATTERN = re.compile(
    r"(?m)^\s+(?:contract|structured_output|input_template|preserve_input|"
    r"include_input|result_key|include_messages|include_files):"
)
REGISTERED_NODE_TYPES = {
    "input@1",
    "output@1",
    "llm@1",
    "tool@1",
    "agent@1",
    "human@1",
    "workflow@1",
    "code@2",
    "foreach@1",
    "loop@1",
    "poll@1",
}
NODE_CONFIG_FIELDS = {
    "input@1": (set(), set()),
    "output@1": ({"message"}, set()),
    "llm@1": (
        {
            "prompt",
            "includes",
            "user_prompt",
            "model",
            "temperature",
            "user_language",
            "instruction",
            "mode",
        },
        {"prompt"},
    ),
    "tool@1": ({"name"}, {"name"}),
    "agent@1": (
        {"prompt", "includes", "resources", "tools", "skills", "model", "max_steps"},
        {"prompt"},
    ),
    "human@1": ({"message", "fields", "actions"}, {"message", "actions"}),
    "workflow@1": ({"ref", "lifecycle"}, {"ref"}),
    "code@2": ({"path", "resources"}, {"path"}),
    "foreach@1": (
        {
            "ref",
            "items_input",
            "shared_input",
            "item_input",
            "dependencies_input",
            "item_id_path",
            "depends_on_path",
            "max_concurrency",
            "failure_policy",
        },
        {"ref", "item_id_path"},
    ),
    "loop@1": (
        {
            "ref",
            "initial_state_input",
            "shared_input",
            "state_input",
            "iteration_input",
            "state_output",
            "decision_output",
            "continue_value",
            "done_value",
            "max_iterations",
        },
        {"ref"},
    ),
    "poll@1": (
        {
            "name",
            "handle_input",
            "handle_argument",
            "timeout_argument",
            "timeout_seconds",
            "max_polls",
            "pending_path",
            "pending_values",
            "terminal_path",
            "success_values",
            "failure_values",
        },
        set(),
    ),
}
INPUT_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
ALLOWED_GLUE_IMPORT_ROOTS = {
    "__future__",
    "asyncio",
    "base64",
    "collections",
    "copy",
    "csv",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "functools",
    "hashlib",
    "io",
    "itertools",
    "json",
    "math",
    "operator",
    "pathlib",
    "re",
    "statistics",
    "string",
    "typing",
}
STDLIB_MODULE_ROOTS = frozenset(
    getattr(sys, "stdlib_module_names", ALLOWED_GLUE_IMPORT_ROOTS)
) | ALLOWED_GLUE_IMPORT_ROOTS
BANNED_GLUE_IMPORT_ROOTS = {
    "ftplib",
    "http",
    "socket",
    "smtplib",
    "sqlite3",
    "subprocess",
    "urllib",
}
ALLOWED_SCHEMA_KEYS = {
    "type",
    "properties",
    "required",
    "items",
    "enum",
    "const",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minProperties",
    "maxProperties",
}
MAX_MEMBERS = 256
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 32 * 1024 * 1024
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
WORKFLOW_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
NODE_ID_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


if yaml is not None:
    class _WorkflowYamlLoader(yaml.SafeLoader):
        """Parse YAML 1.2 booleans so an edge key named ``on`` stays a string."""


    _WorkflowYamlLoader.yaml_implicit_resolvers = {
        key: [item for item in values if item[0] != "tag:yaml.org,2002:bool"]
        for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }
    _WorkflowYamlLoader.add_implicit_resolver(
        "tag:yaml.org,2002:bool",
        re.compile(r"^(?:true|false)$", re.IGNORECASE),
        list("tTfF"),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build from a clean package-source directory. This performs portable "
            "structural checks without importing an AgentOS source checkout."
        )
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument(
        "--workflow-key",
        help=(
            "Expected public WPM key. When supplied it must equal workflow.id; "
            "AgentOS rejects a downloaded package whose internal id differs."
        ),
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--output", type=Path)
    action.add_argument("--check", type=Path, help="Require rebuilt bytes to equal this package")
    return parser.parse_args()


def safe_member(raw: str) -> str:
    path = PurePosixPath(raw)
    if (
        not raw
        or "\\" in raw
        or raw.startswith("/")
        or raw.endswith("/")
        or path.as_posix() != raw
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"unsafe package member path: {raw!r}")
    return raw


def validate_resource_reference(value: Any, *, prefix: str | None = None) -> str:
    if not isinstance(value, str):
        raise ValueError("workflow resource reference must be a string")
    path = safe_member(value)
    if not path.startswith(ALLOWED_PREFIXES):
        raise ValueError(
            "workflow resources must be under resources/references or resources/scripts"
        )
    if prefix is not None and not path.startswith(prefix):
        raise ValueError(f"workflow resource {path} must be under {prefix}")
    return path


def validate_code(source: str, *, path: str) -> None:
    tree = ast.parse(source, filename=path, mode="exec")
    entries = [
        item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == "main"
    ]
    if len(entries) != 1 or not isinstance(entries[0], ast.AsyncFunctionDef):
        raise ValueError(f"{path}: must define exactly one async main(ctx, input)")
    arguments = entries[0].args
    names = [argument.arg for argument in arguments.args]
    if (
        arguments.posonlyargs
        or names != ["ctx", "input"]
        or arguments.vararg is not None
        or arguments.kwarg is not None
        or arguments.kwonlyargs
        or arguments.defaults
        or arguments.kw_defaults
    ):
        raise ValueError(f"{path}: main signature must be exactly async main(ctx, input)")
    for item in ast.walk(tree):
        if isinstance(item, ast.Import):
            roots = {alias.name.split(".", 1)[0] for alias in item.names}
        elif isinstance(item, ast.ImportFrom):
            roots = {str(item.module or "").split(".", 1)[0]}
        else:
            roots = set()
        unsupported = sorted(
            root
            for root in roots
            if root not in STDLIB_MODULE_ROOTS or root in BANNED_GLUE_IMPORT_ROOTS
        )
        if unsupported:
            raise ValueError(
                f"{path}: code@2 glue may not import disallowed module {unsupported[0]}"
            )
        if (
            isinstance(item, ast.Call)
            and isinstance(item.func, ast.Attribute)
            and isinstance(item.func.value, ast.Name)
            and item.func.value.id == "ctx"
            and item.func.attr in {"llm", "tool"}
        ):
            raise ValueError(
                f"{path}: code@2 glue may not call ctx.{item.func.attr}(); use a fixed node"
            )


def _expect_mapping(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _validate_schema(schema: Any, *, label: str) -> None:
    value = _expect_mapping(schema, label=label)
    unsupported = sorted(set(value) - ALLOWED_SCHEMA_KEYS)
    if unsupported:
        raise ValueError(f"{label} contains unsupported keyword {unsupported[0]}")
    properties = value.get("properties")
    if properties is not None:
        for name, child in _expect_mapping(
            properties, label=f"{label}.properties"
        ).items():
            _validate_schema(child, label=f"{label}.properties.{name}")
    if "items" in value:
        _validate_schema(value["items"], label=f"{label}.items")


def _validate_interface(node_type: str, interface: Any, *, label: str) -> None:
    value = _expect_mapping(interface, label=label)
    if set(value) != {"inputs", "outputs", "routes"}:
        raise ValueError(f"{label} must contain exactly inputs, outputs, and routes")
    inputs = _expect_mapping(value["inputs"], label=f"{label}.inputs")
    outputs = _expect_mapping(value["outputs"], label=f"{label}.outputs")
    routes = value["routes"]
    if (
        not isinstance(routes, list)
        or any(not isinstance(route, str) or not route for route in routes)
        or len(routes) != len(set(routes))
    ):
        raise ValueError(f"{label}.routes must contain unique non-empty strings")
    if node_type == "input@1":
        if inputs or not outputs or value["routes"]:
            raise ValueError(f"{label}: input@1 requires outputs only")
        invalid_input_keys = [name for name in outputs if INPUT_KEY_PATTERN.fullmatch(str(name)) is None]
        if invalid_input_keys:
            raise ValueError(
                f"{label}: workflow input key must be ASCII snake_case: {invalid_input_keys[0]}"
            )
    elif not outputs:
        raise ValueError(f"{label}: {node_type} requires outputs")
    if routes and node_type not in {"code@2", "human@1"}:
        raise ValueError(f"{label}: {node_type} does not support routes")
    for name, raw_port in inputs.items():
        port = _expect_mapping(raw_port, label=f"{label}.inputs.{name}")
        if not {"schema", "source"} <= set(port) or set(port) - {
            "required",
            "schema",
            "source",
        }:
            raise ValueError(f"{label}.inputs.{name} has an invalid shape")
        _validate_schema(port["schema"], label=f"{label}.inputs.{name}.schema")
        source = _expect_mapping(
            port["source"], label=f"{label}.inputs.{name}.source"
        )
        if source.get("kind") == "node":
            if set(source) != {"kind", "selector"} or not isinstance(
                source["selector"], list
            ) or len(source["selector"]) < 2:
                raise ValueError(f"{label}.inputs.{name} has an invalid node selector")
        elif source.get("kind") == "literal":
            if set(source) != {"kind", "value"}:
                raise ValueError(f"{label}.inputs.{name} has an invalid literal")
        else:
            raise ValueError(f"{label}.inputs.{name} has an unknown source kind")
    for name, raw_port in outputs.items():
        port = _expect_mapping(raw_port, label=f"{label}.outputs.{name}")
        if "schema" not in port or set(port) - {"required", "schema"}:
            raise ValueError(f"{label}.outputs.{name} has an invalid shape")
        _validate_schema(port["schema"], label=f"{label}.outputs.{name}.schema")
    if node_type == "output@1" and set(inputs) != set(outputs):
        raise ValueError(f"{label}: output@1 inputs and outputs must match")
    if node_type == "output@1":
        for name in inputs:
            if inputs[name].get("required", True) != outputs[name].get(
                "required", True
            ) or inputs[name]["schema"] != outputs[name]["schema"]:
                raise ValueError(
                    f"{label}: output@1 port {name} schemas must match"
                )


def _validate_graph(graph: dict[str, Any], *, label: str) -> None:
    allowed = {"entry", "nodes", "edges"}
    if label == "workflow":
        allowed |= {"id", "version", "subworkflows"}
    if unknown := sorted(set(graph) - allowed):
        raise ValueError(f"{label} contains unknown field {unknown[0]}")
    required = {"entry", "nodes", "edges"}
    if missing := sorted(required - set(graph)):
        raise ValueError(f"{label} is missing field {missing[0]}")
    entry = graph["entry"]
    nodes = _expect_mapping(graph["nodes"], label=f"{label}.nodes")
    edges = graph["edges"]
    if not isinstance(entry, str) or entry not in nodes:
        raise ValueError(f"{label}.entry must name an existing node")
    if not nodes:
        raise ValueError(f"{label}.nodes must not be empty")
    for node_id in nodes:
        if not isinstance(node_id, str) or NODE_ID_PATTERN.fullmatch(node_id) is None:
            raise ValueError(f"{label} has invalid node id {node_id!r}")
    if not isinstance(edges, list):
        raise ValueError(f"{label}.edges must be an array")

    outgoing: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
    incoming: dict[str, list[str]] = defaultdict(list)
    identities: set[tuple[str, str, str | None]] = set()
    for index, raw_edge in enumerate(edges):
        edge = _expect_mapping(raw_edge, label=f"{label}.edges.{index}")
        if set(edge) - {"from", "to", "on"} or not {"from", "to"} <= set(edge):
            raise ValueError(f"{label}.edges.{index} has an invalid shape")
        source, target, route = edge["from"], edge["to"], edge.get("on")
        if source not in nodes or target not in nodes:
            raise ValueError(f"{label}.edges.{index} references an unknown node")
        if route is not None and (not isinstance(route, str) or not route):
            raise ValueError(f"{label}.edges.{index}.on must be a non-empty string")
        identity = (source, target, route)
        if identity in identities:
            raise ValueError(f"{label} contains duplicate edge {source}->{target}")
        identities.add(identity)
        outgoing[source].append((target, route))
        incoming[target].append(source)
    if incoming.get(entry):
        raise ValueError(f"{label}.entry must not have predecessors")

    indegree = {node_id: len(incoming[node_id]) for node_id in nodes}
    pending = deque(sorted(node_id for node_id, count in indegree.items() if count == 0))
    order: list[str] = []
    while pending:
        current = pending.popleft()
        order.append(current)
        for target, _route in outgoing[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                pending.append(target)
    if len(order) != len(nodes):
        raise ValueError(f"{label} must be a DAG")

    reachable: set[str] = set()
    pending_nodes = [entry]
    while pending_nodes:
        current = pending_nodes.pop()
        if current in reachable:
            continue
        reachable.add(current)
        pending_nodes.extend(target for target, _route in outgoing[current])
    if unreachable := sorted(set(nodes) - reachable):
        raise ValueError(f"{label} has unreachable nodes: {', '.join(unreachable)}")

    if nodes[entry].get("type") != "input@1":
        raise ValueError(f"{label}.entry must be input@1")
    for node_id, node in nodes.items():
        node_type = node.get("type") if isinstance(node, dict) else None
        routes = node.get("interface", {}).get("routes", []) if isinstance(node, dict) else []
        routed = [route for _target, route in outgoing[node_id] if route is not None]
        ordinary = [route for _target, route in outgoing[node_id] if route is None]
        if routed and ordinary:
            raise ValueError(f"{label}.{node_id} mixes routed and ordinary edges")
        if len(routed) != len(routes) or set(routed) != set(routes):
            raise ValueError(f"{label}.{node_id} routes do not match outgoing edges")
        if node_type == "output@1" and outgoing[node_id]:
            raise ValueError(f"{label}.{node_id} terminal node has outgoing edges")
        if node_type != "output@1" and not outgoing[node_id]:
            raise ValueError(f"{label}.{node_id} non-terminal node has no outgoing edge")

    dominators: dict[str, set[str]] = {entry: {entry}}
    for node_id in order:
        if node_id == entry:
            continue
        predecessors = incoming[node_id]
        dominators[node_id] = {node_id, *set.intersection(*(dominators[p] for p in predecessors))}
    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        interface = node.get("interface")
        if not isinstance(interface, dict) or not isinstance(interface.get("inputs"), dict):
            continue
        for port_name, port in interface["inputs"].items():
            if not isinstance(port, dict) or not isinstance(port.get("source"), dict):
                continue
            source = port["source"]
            if source.get("kind") != "node":
                continue
            selector = source.get("selector")
            if not isinstance(selector, list) or len(selector) < 2:
                continue
            source_id, output_name = selector[:2]
            if source_id not in nodes or source_id == node_id:
                raise ValueError(f"{label}.{node_id}.{port_name} selector has invalid node")
            source_outputs = nodes[source_id].get("interface", {}).get("outputs", {})
            if output_name not in source_outputs:
                raise ValueError(f"{label}.{node_id}.{port_name} selector output does not exist")
            if port.get("required", True) and source_id not in dominators[node_id]:
                raise ValueError(f"{label}.{node_id}.{port_name} source does not dominate consumer")


def _graphs(workflow: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    graphs = [("workflow", workflow)]
    subworkflows = workflow.get("subworkflows", {})
    if subworkflows is not None:
        graphs.extend(
            (f"workflow.subworkflows.{name}", _expect_mapping(graph, label=f"subworkflow {name}"))
            for name, graph in _expect_mapping(
                subworkflows, label="workflow.subworkflows"
            ).items()
        )
    return graphs


def semantic_preflight(
    workflow_text: str, *, expected_workflow_key: str | None = None
) -> tuple[set[str], str, str] | None:
    if yaml is None:
        return None
    payload = yaml.load(workflow_text, Loader=_WorkflowYamlLoader)
    document = _expect_mapping(payload, label="document")
    if set(document) != {"spec", "workflow"}:
        raise ValueError("workflow document must contain exactly spec and workflow")
    if document.get("spec") != "agentos.workflow/v3":
        raise ValueError("portable baseline requires spec: agentos.workflow/v3")
    workflow = _expect_mapping(document["workflow"], label="workflow")
    workflow_id = workflow.get("id")
    version = workflow.get("version")
    if not isinstance(workflow_id, str) or WORKFLOW_KEY_PATTERN.fullmatch(workflow_id) is None:
        raise ValueError("workflow.id must match ^[a-z0-9][a-z0-9-]{1,62}$")
    if not isinstance(version, str) or SEMVER_PATTERN.fullmatch(version) is None:
        raise ValueError("workflow.version must be numeric SemVer x.y.z for WPM")
    if expected_workflow_key is not None and workflow_id != expected_workflow_key:
        raise ValueError(
            f"workflow.id {workflow_id!r} does not match public WPM key "
            f"{expected_workflow_key!r}"
        )
    _validate_graph(workflow, label="workflow")
    for sub_name, sub_graph in _expect_mapping(
        workflow.get("subworkflows", {}), label="workflow.subworkflows"
    ).items():
        if not isinstance(sub_name, str) or not sub_name:
            raise ValueError("subworkflow names must be non-empty strings")
        _validate_graph(_expect_mapping(sub_graph, label=f"subworkflow {sub_name}"), label=f"workflow.subworkflows.{sub_name}")
    referenced: set[str] = set()
    for graph_label, graph in _graphs(workflow):
        nodes = _expect_mapping(graph.get("nodes"), label=f"{graph_label}.nodes")
        for node_id, raw_node in nodes.items():
            label = f"{graph_label}.nodes.{node_id}"
            node = _expect_mapping(raw_node, label=label)
            if set(node) - {"type", "title", "description", "interface", "config", "policy"}:
                raise ValueError(f"{label} contains unknown fields")
            if not {"type", "interface", "config"} <= set(node):
                raise ValueError(f"{label} must declare type, interface, and config")
            node_type = node["type"]
            if node_type not in REGISTERED_NODE_TYPES:
                raise ValueError(f"{label} uses unsupported node type {node_type}")
            _validate_interface(node_type, node["interface"], label=f"{label}.interface")
            config = _expect_mapping(node["config"], label=f"{label}.config")
            allowed, required = NODE_CONFIG_FIELDS[node_type]
            unknown = sorted(set(config) - allowed)
            missing = sorted(required - set(config))
            if unknown:
                raise ValueError(f"{label}.config contains unknown field {unknown[0]}")
            if missing:
                raise ValueError(f"{label}.config is missing field {missing[0]}")
            if node_type == "llm@1":
                mode = config.get("mode", "text")
                if mode not in {"text", "json"}:
                    raise ValueError(f"{label}.config.mode must be text or json")
                temperature = config.get("temperature")
                if temperature is not None and (
                    not isinstance(temperature, (int, float))
                    or isinstance(temperature, bool)
                    or not 0 <= temperature <= 2
                ):
                    raise ValueError(f"{label}.config.temperature must be within 0..2")
                llm_inputs = node["interface"]["inputs"]
                for media_port in ("images", "videos"):
                    if media_port not in llm_inputs:
                        continue
                    media_schema = llm_inputs[media_port]["schema"]
                    if media_schema.get("type") != "array" or not isinstance(
                        media_schema.get("items"), dict
                    ) or media_schema["items"].get("type") != "string":
                        raise ValueError(
                            f"{label}.{media_port} must be an array of strings"
                        )
                if mode == "json" and "videos" in llm_inputs:
                    raise ValueError(
                        f"{label} cannot declare videos when mode is json"
                    )
            if node_type in {"llm@1", "agent@1"}:
                referenced.add(
                    validate_resource_reference(
                        config["prompt"], prefix="resources/references/"
                    )
                )
                includes = config.get("includes", [])
                if not isinstance(includes, list):
                    raise ValueError(f"{label}.config.includes must be an array")
                referenced.update(
                    validate_resource_reference(
                        item, prefix="resources/references/"
                    )
                    for item in includes
                )
                if node_type == "agent@1":
                    resources = config.get("resources", [])
                    if not isinstance(resources, list):
                        raise ValueError(f"{label}.config.resources must be an array")
                    referenced.update(
                        validate_resource_reference(item) for item in resources
                    )
            elif node_type == "code@2":
                code_path = validate_resource_reference(
                    config["path"], prefix="resources/scripts/"
                )
                if not code_path.endswith(".py"):
                    raise ValueError(f"{label}.config.path must end with .py")
                referenced.add(code_path)
                resources = config.get("resources", [])
                if not isinstance(resources, list):
                    raise ValueError(f"{label}.config.resources must be an array")
                referenced.update(
                    validate_resource_reference(item) for item in resources
                )
    return referenced, workflow_id, version


def collect_payloads(
    root: Path, *, expected_workflow_key: str | None = None
) -> tuple[dict[str, bytes], str | None, str | None]:
    root = root.resolve()
    workflow = root / WORKFLOW_PATH
    if not workflow.is_file():
        raise ValueError(f"package source is missing {WORKFLOW_PATH}: {root}")
    payloads: dict[str, bytes] = {}
    for candidate in sorted(root.rglob("*")):
        if candidate.is_symlink():
            raise ValueError(f"package source must not contain symlinks: {candidate}")
        if not candidate.is_file():
            continue
        relative = safe_member(candidate.relative_to(root).as_posix())
        if relative != WORKFLOW_PATH and not relative.startswith(ALLOWED_PREFIXES):
            raise ValueError(f"unexpected package source member: {relative}")
        if relative.startswith("resources/scripts/") and not relative.endswith(".py"):
            raise ValueError(f"script member must end with .py: {relative}")
        content = candidate.read_bytes()
        if len(content) > MAX_MEMBER_BYTES:
            raise ValueError(f"package member is too large: {relative}")
        payloads[relative] = content
    if len(payloads) > MAX_MEMBERS:
        raise ValueError("package has too many members")
    if sum(map(len, payloads.values())) > MAX_TOTAL_BYTES:
        raise ValueError("package is too large")
    raw_workflow = payloads[WORKFLOW_PATH]
    try:
        workflow_text = raw_workflow.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("workflow.yml must be UTF-8") from exc
    if SPEC_PATTERN.search(workflow_text) is None:
        raise ValueError("portable baseline requires spec: agentos.workflow/v3")
    if REMOVED_V2_FIELD_PATTERN.search(workflow_text):
        raise ValueError("workflow.yml contains a removed v2 field")
    if re.search(r"\b(?:code@1|script@1)\b", workflow_text):
        raise ValueError("portable baseline rejects code@1 and script@1")
    semantic_result = semantic_preflight(
        workflow_text, expected_workflow_key=expected_workflow_key
    )
    semantic_references = semantic_result[0] if semantic_result is not None else None
    referenced = (
        semantic_references
        if semantic_references is not None
        else set(RESOURCE_PATTERN.findall(workflow_text))
    )
    actual = set(payloads) - {WORKFLOW_PATH}
    missing = sorted(referenced - actual)
    extra = sorted(actual - referenced)
    if missing:
        raise ValueError(f"missing referenced resources: {', '.join(missing)}")
    if extra:
        raise ValueError(f"unreferenced resources: {', '.join(extra)}")
    for path, content in payloads.items():
        if path.startswith("resources/scripts/"):
            try:
                validate_code(content.decode("utf-8"), path=path)
            except UnicodeDecodeError as exc:
                raise ValueError(f"code script must be UTF-8: {path}") from exc
    workflow_id = semantic_result[1] if semantic_result is not None else None
    workflow_version = semantic_result[2] if semantic_result is not None else None
    return payloads, workflow_id, workflow_version


def archive_bytes(payloads: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    names = [WORKFLOW_PATH, *sorted(set(payloads) - {WORKFLOW_PATH})]
    with zipfile.ZipFile(output, "w") as archive:
        for name in names:
            info = zipfile.ZipInfo(name, date_time=ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, payloads[name])
    return output.getvalue()


def report(
    *, target: Path, payloads: dict[str, bytes], built: bytes, identical: bool | None,
    workflow_id: str | None, workflow_version: str | None
) -> dict[str, Any]:
    return {
        "target": str(target.resolve()),
        "sha256": hashlib.sha256(built).hexdigest(),
        "members": [WORKFLOW_PATH, *sorted(set(payloads) - {WORKFLOW_PATH})],
        "member_count": len(payloads),
        "byte_identical": identical,
        "workflow_id": workflow_id,
        "workflow_version": workflow_version,
        "portable_structural_preflight": True,
        "portable_yaml_semantic_preflight": yaml is not None,
        "authoritative_runtime_admission": None,
        "verification_level": "candidate",
    }


def main() -> int:
    args = parse_args()
    payloads, workflow_id, workflow_version = collect_payloads(
        args.source_root, expected_workflow_key=args.workflow_key
    )
    first = archive_bytes(payloads)
    second = archive_bytes(payloads)
    if first != second:
        raise RuntimeError("two in-memory builds were not byte-identical")
    if args.output is not None:
        target = args.output.resolve()
        if target.suffix != ".awpkg":
            raise ValueError("output must end with .awpkg")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(first)
        result = report(
            target=target,
            payloads=payloads,
            built=first,
            identical=True,
            workflow_id=workflow_id,
            workflow_version=workflow_version,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    target = args.check.resolve()
    identical = target.is_file() and target.read_bytes() == first
    result = report(
        target=target,
        payloads=payloads,
        built=first,
        identical=identical,
        workflow_id=workflow_id,
        workflow_version=workflow_version,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if identical else 2


if __name__ == "__main__":
    raise SystemExit(main())
