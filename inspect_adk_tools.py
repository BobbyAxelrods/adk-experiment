import google.adk.tools
print(f"Contents of google.adk.tools: {dir(google.adk.tools)}")

try:
    from google.adk.tools import Tool
    print("Success: from google.adk.tools import Tool")
except ImportError as e:
    print(f"Failed: {e}")

try:
    import google.adk.tools.tool
    print("Success: import google.adk.tools.tool")
except ImportError as e:
    print(f"Failed: google.adk.tools.tool - {e}")
