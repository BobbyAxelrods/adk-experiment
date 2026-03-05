import argparse
import asyncio
import json
import logging
import os
import re

from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
from dotenv import load_dotenv

# Re-use your existing agent setup
from agents.agent import root_agent

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session_service = InMemorySessionService()
app_name = os.getenv("APP_NAME", "CompleteAgentDemo")

async def approve_ticket(session_id: str, user_id: str, ticket_id: str, call_id: str):
    logger.info(f"Starting approval workflow for Session: {session_id}, Ticket: {ticket_id}, CallID: {call_id}")
    
    # Initialize Runner
    runner = Runner(
        app_name=app_name,
        agent=root_agent,
        session_service=session_service
    )

    # 1. Create the FunctionResponse part
    #    This tells the model "The function call you made (submit_for_approval) is now complete with this result."
    function_response_part = types.Part(
        function_response=types.FunctionResponse(
            id=call_id,
            name="submit_for_approval",
            response={
                "status": "approved", 
                "ticket_id": ticket_id,
                "note": "Approved by external script"
            }
        )
    )

    # 2. Add a text part to encourage the model to continue the conversation naturally
    #    (Optional, but helps guide the model's next response)
    text_part = types.Part(
        text="The ticket has been approved. Please inform the user and continue."
    )

    input_message = types.Content(
        role="user",
        parts=[function_response_part, text_part]
    )

    # 3. Run the agent with this input
    logger.info("Sending approval response to agent...")
    full_response = ""
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=input_message
        ):
            if event.content:
                for part in event.content.parts:
                    if part.text:
                        print(part.text, end="", flush=True)
                        full_response += part.text
    except Exception as e:
        logger.error(f"Error during approval run: {e}", exc_info=True)

    print("\n\n--- Final Response from Agent ---")
    print(full_response)
    print("---------------------------------")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate approving a ticket externally.")
    parser.add_argument("session_id", help="The Session ID")
    parser.add_argument("user_id", help="The User ID (phone number)")
    parser.add_argument("ticket_id", help="The Ticket ID (e.g., TICK-12345)")
    parser.add_argument("call_id", help="The Function Call ID (from logs)")

    args = parser.parse_args()

    asyncio.run(approve_ticket(args.session_id, args.user_id, args.ticket_id, args.call_id))
