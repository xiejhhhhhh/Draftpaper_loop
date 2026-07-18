"""Method execution verification, formula extraction and manuscript writing APIs."""

from . import formulas, verification, writer
from .common import MethodsGateError, _read_manifest
from .formulas import _write_method_formulas
from .verification import _resolve_verification_inputs, _validate_verify_argv, verify_methods
from .writer import _method_reproducibility_contract, build_method_writing_context, write_methods

__all__ = [
    "MethodsGateError",
    "verify_methods",
    "build_method_writing_context",
    "write_methods",
]
