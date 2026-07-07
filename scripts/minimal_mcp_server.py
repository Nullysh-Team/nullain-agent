"""Servidor MCP mínimo para testes locais do NULLAIN."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("nullain-test")


@mcp.tool()
def ping() -> str:
    """Retorna pong para validar conexão MCP."""
    return "pong"


if __name__ == "__main__":
    mcp.run(transport="stdio")