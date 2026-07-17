"""Normalized runtime contracts composed from CLI syntax and execution policy."""

from __future__ import annotations

import argparse
import inspect
from importlib import import_module
from typing import Any

from .command_registry import COMMAND_SPECS, CommandSpec


HARD_GATE_COMMANDS = frozenset({
    "assess-core-evidence",
    "assess-data-quality",
    "assess-result-validity",
    "verify-methods",
    "audit-citations",
    "run-integrity-gate",
    "quality-check",
})


def _subparser_choices(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _actions(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    result = [action for action in parser._actions if action.dest != "help"]
    for child in _subparser_choices(parser).values():
        result.extend(_actions(child))
    return result


def _json_type(action: argparse.Action) -> str:
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        return "boolean"
    if action.type is int:
        return "integer"
    if action.type is float:
        return "number"
    if action.nargs in {"+", "*"}:
        return "array"
    return "string"


def command_input_schema(command: str) -> tuple[dict[str, Any], bool]:
    from .cli import build_parser

    parser = _subparser_choices(build_parser()).get(command)
    if parser is None:
        return {"type": "object", "properties": {}, "additionalProperties": False}, False
    properties: dict[str, Any] = {}
    required: list[str] = []
    for action in _actions(parser):
        if action.dest in properties:
            continue
        if isinstance(action, argparse._SubParsersAction):
            properties[action.dest] = {"type": "string", "enum": sorted(action.choices)}
            if action.required:
                required.append(action.dest)
            continue
        contract: dict[str, Any] = {"type": _json_type(action)}
        if action.choices:
            contract["enum"] = list(action.choices)
        properties[action.dest] = contract
        if action.required:
            required.append(action.dest)
    return {
        "type": "object",
        "properties": properties,
        "required": sorted(set(required)),
        "additionalProperties": False,
    }, "project" in properties


def required_options(command: str) -> list[str]:
    from .cli import build_parser

    parser = _subparser_choices(build_parser()).get(command)
    if parser is None:
        return []
    return [
        action.option_strings[0]
        for action in _actions(parser)
        if action.required and action.option_strings
    ]


def _handler_issues(spec: CommandSpec, parser_destinations: set[str]) -> list[str]:
    if not spec.handler_module or not spec.handler_name:
        return []
    issues: list[str] = []
    bound_parameters = {parameter for parameter, _attribute in spec.argument_bindings}
    bound_attributes = {attribute for _parameter, attribute in spec.argument_bindings}
    missing_attributes = sorted(bound_attributes - parser_destinations)
    if missing_attributes:
        issues.append("binding_attributes_missing_from_parser:" + ",".join(missing_attributes))
    module = import_module(f".{spec.handler_module}", package=__package__)
    handler = getattr(module, spec.handler_name, None)
    if not callable(handler):
        issues.append("handler_not_callable")
        return issues
    signature = inspect.signature(handler)
    accepted = set(signature.parameters)
    missing_parameters = sorted(bound_parameters - accepted)
    if missing_parameters:
        issues.append("binding_parameters_missing_from_handler:" + ",".join(missing_parameters))
    required_parameters = {
        name
        for name, parameter in signature.parameters.items()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind in {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY}
    }
    unbound_required = sorted(required_parameters - bound_parameters)
    if unbound_required:
        issues.append("required_handler_parameters_unbound:" + ",".join(unbound_required))
    return issues


def build_command_contracts() -> dict[str, Any]:
    from .cli import build_parser

    choices = _subparser_choices(build_parser())
    records = []
    issues: list[str] = []
    names = sorted(set(choices) | set(COMMAND_SPECS))
    for name in names:
        spec = COMMAND_SPECS.get(name)
        parser = choices.get(name)
        local_issues = []
        if spec is None:
            local_issues.append("command_spec_missing")
        if parser is None:
            local_issues.append("parser_missing")
        schema, project_scoped = command_input_schema(name) if parser else ({"type": "object"}, False)
        if spec and parser:
            local_issues.extend(_handler_issues(spec, {action.dest for action in _actions(parser)}))
        if spec and name in HARD_GATE_COMMANDS:
            if not spec.handler_module or not spec.handler_name:
                local_issues.append("hard_gate_handler_missing")
            if spec.exit_policy == "always_success":
                local_issues.append("hard_gate_exit_policy_missing")
        issues.extend(f"{name}:{issue}" for issue in local_issues)
        records.append({
            "command": name,
            "coordinator": spec.coordinator if spec else None,
            "handler": f"{spec.handler_module}.{spec.handler_name}" if spec and spec.handler_module else "legacy_cli_dispatch",
            "input_schema": schema,
            "output_schema": spec.output_schema if spec else {},
            "project_scoped": project_scoped,
            "risk_level": spec.risk_level if spec else None,
            "mutates_project": spec.mutates_project if spec else None,
            "issues": local_issues,
        })
    return {
        "schema_version": "dpl.command_contract_registry.v1",
        "status": "passed" if not issues else "failed",
        "command_count": len(records),
        "registered_handler_count": sum(1 for record in records if record["handler"] != "legacy_cli_dispatch"),
        "legacy_dispatch_count": sum(1 for record in records if record["handler"] == "legacy_cli_dispatch"),
        "commands": records,
        "issues": issues,
    }


def validate_command_contracts() -> dict[str, Any]:
    return build_command_contracts()
