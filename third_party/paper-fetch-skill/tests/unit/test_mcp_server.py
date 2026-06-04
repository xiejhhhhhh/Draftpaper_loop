# ruff: noqa: F403,F405
from __future__ import annotations

from ._mcp_support import *


class McpServerFastMCPApiTests(unittest.TestCase):
    def test_build_server_uses_pinned_fastmcp_resource_registry(self) -> None:
        server = build_server()

        self.assertIsInstance(server._resource_manager._resources, dict)

    def test_build_server_advertises_resource_list_changed_capability(self) -> None:
        server = build_server()

        options = server._mcp_server.create_initialization_options()

        self.assertIsNotNone(options.capabilities.resources)
        self.assertTrue(options.capabilities.resources.listChanged)

    def test_build_server_uses_pinned_fastmcp_stdio_run_surface(self) -> None:
        server = build_server()

        self.assertTrue(callable(server._mcp_server.run))
        self.assertTrue(callable(server._mcp_server.create_initialization_options))
