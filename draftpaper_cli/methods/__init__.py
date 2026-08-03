"""Method execution verification, formula extraction and manuscript writing APIs."""

from . import formulas as formulas, verification as verification, writer as writer
from .common import MethodsGateError as MethodsGateError, _read_manifest as _read_manifest
from .formulas import _write_method_formulas as _write_method_formulas
from .verification import (
    _resolve_verification_inputs as _resolve_verification_inputs,
    _validate_verify_argv as _validate_verify_argv,
    verify_methods as verify_methods,
)
from .writer import (
    _method_reproducibility_contract as _method_reproducibility_contract,
    build_method_writing_context as build_method_writing_context,
    write_methods as write_methods,
)

__all__ = [
    "MethodsGateError",
    "formulas",
    "verification",
    "writer",
    "_read_manifest",
    "_write_method_formulas",
    "_resolve_verification_inputs",
    "_validate_verify_argv",
    "_method_reproducibility_contract",
    "verify_methods",
    "build_method_writing_context",
    "write_methods",
]
