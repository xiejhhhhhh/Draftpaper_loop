"""Stable, capability-negotiated extension host for Draftpaper-loop."""

from .contracts import ExtensionManifest, HostCapabilities, NegotiationResult
from .dispatcher import dispatch_workflow_event
from .events import WorkflowEvent, emit_command_event
from .host_capabilities import build_host_capabilities
from .registry import DiscoveredExtension, discover_extensions

__all__ = [
    "DiscoveredExtension",
    "ExtensionManifest",
    "HostCapabilities",
    "NegotiationResult",
    "WorkflowEvent",
    "build_host_capabilities",
    "discover_extensions",
    "dispatch_workflow_event",
    "emit_command_event",
]
