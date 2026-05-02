"""Future FastMCP adapter for jupyter-workbench service parity.

The MCP surface is intentionally an adapter around the same DTO-returning core
services that power the CLI and direct library API. JSON serialization belongs
at this boundary; transport-independent decisions stay in ``core`` services.

Example future pattern::

    # from fastmcp import FastMCP
    # from jupyter_workbench.composition import build_session_service
    #
    # mcp = FastMCP("jupyter-workbench")
    #
    # @mcp.tool
    # def open_session(session_id: str | None = None) -> dict[str, object]:
    #     service = build_session_service()
    #     result = service.open(session_id=session_id)
    #     return dataclasses.asdict(result)
"""
