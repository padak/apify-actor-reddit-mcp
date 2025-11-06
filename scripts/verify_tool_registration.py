#!/usr/bin/env python3
"""
Verify that search_reddit tool is properly registered with FastMCP.

This script imports the MCP server and checks that:
1. The server instance exists
2. The search_reddit tool is registered
3. The tool has correct metadata
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.server import mcp
import src.tools.search_reddit  # Ensure tool is imported and registered


def verify_tool_registration():
    """Verify search_reddit tool is registered."""
    print("=" * 60)
    print("MCP Tool Registration Verification")
    print("=" * 60)

    # Check server instance
    print(f"\n✓ MCP Server Instance: {mcp.name} v{mcp.version}")

    # Get registered tools
    tools = mcp.list_tools()
    print(f"\n✓ Total Tools Registered: {len(tools)}")

    # List all tools
    print("\nRegistered Tools:")
    for i, tool in enumerate(tools, 1):
        print(f"  {i}. {tool.get('name', 'Unknown')}")

    # Check for search_reddit
    search_reddit_tool = None
    for tool in tools:
        if tool.get('name') == 'search_reddit':
            search_reddit_tool = tool
            break

    if search_reddit_tool:
        print("\n✓ search_reddit tool is registered!")
        print("\nTool Details:")
        print(f"  - Name: {search_reddit_tool.get('name')}")
        print(f"  - Description: {search_reddit_tool.get('description', 'N/A')[:100]}...")

        # Check if input schema exists
        if 'inputSchema' in search_reddit_tool:
            print(f"  - Input Schema: Present")
            schema = search_reddit_tool['inputSchema']
            if 'properties' in schema:
                print(f"  - Parameters: {', '.join(schema['properties'].keys())}")

        print("\n" + "=" * 60)
        print("✓ VERIFICATION SUCCESSFUL")
        print("=" * 60)
        return True
    else:
        print("\n✗ search_reddit tool NOT found!")
        print("\n" + "=" * 60)
        print("✗ VERIFICATION FAILED")
        print("=" * 60)
        return False


if __name__ == "__main__":
    try:
        success = verify_tool_registration()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
