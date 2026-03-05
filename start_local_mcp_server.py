import logging
import uvicorn
import os
from fastapi import FastAPI, Request
from starlette.types import ASGIApp
from tools.mcp_policy.mysql_server_api import create_mcp_lifespan_and_handler
from datetime import datetime

logging.basicConfig(level=logging.INFO)

app_name = 'MCP Server'
version_no = os.getenv("APP_VERSION", datetime.strftime(datetime.now(), '%Y_%m_%d_%H_%M_%S'))

mcp_lifespan, mcp_handler = create_mcp_lifespan_and_handler()

app = FastAPI(lifespan=mcp_lifespan)

app.mount("/policy/", mcp_handler)
app.mount("/booking/", mcp_handler)

@app.get("/health")
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "app_name": app_name, "version": version_no}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
