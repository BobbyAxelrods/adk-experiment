import os
import asyncio
import logging
import re
from fastapi import FastAPI, BackgroundTasks, Request, Response
import json
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
from dotenv import load_dotenv

from pubsub.manager import PubSubManager
from agents.agent import root_agent
from google.cloud import pubsub_v1

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
ps_manager = PubSubManager()
session_service = InMemorySessionService()

# Initialize Runner
app_name = os.getenv("APP_NAME", "CompleteAgentDemo")
version_no = os.getenv("APP_VERSION", "0.0.3")
ENABLE_SIMULATION_TEST = os.getenv("ENABLE_SIMULATION_TEST", False)

runner = Runner(
    app_name=app_name,
    agent=root_agent,
    session_service=session_service
)

async def process_message(data: dict):
    session_id = data.get("session_id")
    user_id = data.get("user_id")
    user_query = data.get("user_query")
    user_state = data.get("user_state", {})

    if not all([session_id, user_id, user_query]):
        logger.warning(f"Invalid message format: {data}")
        return

    logger.info(f"Processing query for session {session_id}, user {user_id}: {user_query}")

    try:
        logger.info("Attempting to create/get session...")
        from google.adk.errors.already_exists_error import AlreadyExistsError
        try:
            await session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id)
            logger.info("Session created successfully.")
        except AlreadyExistsError:
            logger.info("Session already exists, reusing it.")

        full_response = ""
        
        # Check if this is a resume command
        resume_match = re.match(r"RESUME_FLOW: (.*) approved", user_query)
        
        if resume_match:
            ticket_id = resume_match.group(1)
            call_id = user_state.get("call_id")
            logger.info(f"Resuming flow for ticket {ticket_id} with call_id {call_id}")
            
            if call_id:
                # Proper ADK resumption using FunctionResponse part
                input_message = types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                id=call_id,
                                name="submit_for_approval",
                                response={"status": "approved", "ticket_id": ticket_id}
                            )
                        )
                    ]
                )
            else:
                # Fallback to text message if call_id is missing
                input_message = types.Content(parts=[types.Part(text=f"The approval for ticket {ticket_id} has been GRANTED. Please proceed with the task.")])
        else:
            logger.info("Normal query detected.")
            input_message = types.Content(parts=[types.Part(text=user_query)])

        logger.info(f"Starting runner for session {session_id}...")
        
        last_long_running_call_id = None
        # We wrap the runner call in its own try block to catch LLM/ADK specific errors
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=input_message
            ):
                logger.info(f"ADK Event received: {type(event)}")
                if hasattr(event, 'long_running_tool_ids') and event.long_running_tool_ids:
                    logger.info(f"Long-running tool IDs in event: {event.long_running_tool_ids}")
                
                if event.content:
                    for part in event.content.parts:
                        if part.text:
                            logger.info(f"Agent Part [TEXT]: {part.text}")
                            full_response += part.text
                        if part.function_call:
                            logger.info(f"Agent Part [FC]: {part.function_call.name} (ID: {part.function_call.id})")
                            # Capture it if it's explicitly long-running OR if it's our target tool
                            is_long_running = part.function_call.id in (event.long_running_tool_ids or [])
                            if is_long_running:
                                logger.info(f"MATCH: Long-running tool detected: {part.function_call.id}")
                                last_long_running_call_id = part.function_call.id
                            elif part.function_call.name == "submit_for_approval":
                                logger.info(f"MATCH: submit_for_approval tool detected: {part.function_call.id}")
                                last_long_running_call_id = part.function_call.id
                            elif part.function_call.name == "Approval_Agent":
                                # If it's the subagent itself, it might be the one we need to resume if ADK bubbles it up
                                logger.info(f"NOTE: Approval_Agent call detected: {part.function_call.id}")
                                # We'll keep this as a secondary fallback if submit_for_approval is never seen
                                if not last_long_running_call_id:
                                    last_long_running_call_id = part.function_call.id
        except Exception as runner_err:
            logger.error(f"Error during runner.run_async: {runner_err}", exc_info=True)
            full_response = f"I encountered an error while processing with the agent: {runner_err}"

        logger.info(f"Execution finished. Final response: {full_response}")
        
        if full_response:
            logger.info(f"Publishing response to {ps_manager.outgoing_topic_path}")
            # The 'to' field is the user_id (phone number)
            ps_manager.publish_outgoing(session_id, user_id, full_response, user_id, user_state)
        else:
            logger.warning("Empty response from agent, nothing to publish.")
        
        # Special check for approval flow
        if "ticket ID" in full_response or "ticket_id" in full_response:
            match = re.search(r"TICK-\d+", full_response)
            ticket_id = match.group(0) if match else "UNKNOWN"
            
            # Try to find the call_id from the session history or just guess it was the last long-running one
            # For this demo, we can use the last event's tool IDs if we saved them
            # But simpler: we can just tell the user to provide it in the next step or 
            # we can look into the session's history.
            # ADK stores history in the session.
            
            logger.info(f"Approval flow detected. Publishing to process queue: {ticket_id} (Call ID: {last_long_running_call_id})")
            ps_manager.publish_process_queue(session_id, user_id, {"ticket_id": ticket_id, "call_id": last_long_running_call_id})
            
            # Print the exact command for the user to copy/paste
            print(f"\n>>>> PROMPT: Approval needed! Run this command:")
            print(f"python approval.py {session_id} {user_id} {ticket_id} {last_long_running_call_id}\n")

    except Exception as e:
        logger.error(f"Critical error in process_message: {e}", exc_info=True)

async def send_twilio_message(to: str, body: str):
    """Sends a WhatsApp message via Twilio."""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_whatsapp = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886") # Default Sandbox number

    if not account_sid or not auth_token:
        logger.warning("Twilio credentials missing. Skipping outbound message.")
        return

    logger.info(f"Sending Twilio message to {to}: {body[:50]}...")
    
    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        message = client.messages.create(
            from_=from_whatsapp,
            body=body,
            to=to
        )
        logger.info(f"Twilio message sent. SID: {message.sid}")
    except Exception as e:
        logger.error(f"Failed to send Twilio message: {e}")

@app.on_event("startup")
async def startup_event():
    ps_manager.setup_resources()
    
    loop = asyncio.get_running_loop()

    # 1. Start Incoming Listener (Process Messages)
    def listen_incoming():
        future = ps_manager.start_listening(
            lambda data: asyncio.run_coroutine_threadsafe(process_message(data), loop),
            subscription_path=ps_manager.incoming_sub_path
        )
        try:
            future.result()
        except Exception as e:
            logger.error(f"Incoming subscriber stopped: {e}")

    # 2. Start Outgoing Listener (Log Results & Send to Twilio)
    def listen_outgoing():
        def handle_outgoing(data):
            print("\n--- [LOG] Received Output Message ---")
            print(json.dumps(data, indent=2))
            print("-------------------------------------\n")
            
            # Trigger Twilio outbound message
            to = data.get("to")
            body = data.get("response")
            if to and body:
                asyncio.run_coroutine_threadsafe(send_twilio_message(to, body), loop)

        future = ps_manager.start_listening(
            handle_outgoing,
            subscription_path=ps_manager.outgoing_sub_path
        )
        try:
            future.result()
        except Exception as e:
            logger.error(f"Outgoing subscriber stopped: {e}")

    # Run listeners in separate threads
    asyncio.create_task(asyncio.to_thread(listen_incoming))
    if not ENABLE_SIMULATION_TEST:
        asyncio.create_task(asyncio.to_thread(listen_outgoing))

@app.get("/health")
def health_check():
    return {"status": "healthy", "version":version_no}




# Configuration
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
TOPIC_ID = os.getenv("PUBSUB_TOPIC", "gc_incoming_messages")

# Initialize Pub/Sub publisher
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

@app.post("/webhook")
async def twilio_webhook(request: Request):
    """
    Handle incoming WhatsApp messages from Twilio using FastAPI.
    Twilio sends data as application/x-www-form-urlencoded.
    """
    try:
        # FastAPI's way of getting form data as a dict
        form_data = await request.form()
        data = dict(form_data)

        print("message from twilio")
        print(data)
        
        if not data:
            return Response(content="No data received", status_code=400)

        print(f"Received message from {data.get('From')}: {data.get('Body')}")

        # Prepare payload for Pub/Sub
        payload = {
            "session_id": data.get("AccountSid"),
            "user_id": data.get("From"),
            "user_query": data.get("Body"),
            "user_state": {}
        }

        # Publish to Pub/Sub
        message_json = json.dumps(payload)
        message_bytes = message_json.encode("utf-8")
        
        future = publisher.publish(topic_path, message_bytes)
        message_id = future.result()

        print(f"Published message ID: {message_id}")

        # Respond to Twilio with TwiML
        twiml_response = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
        return Response(content=twiml_response, media_type="text/xml")

    except Exception as e:
        print(f"Error processing webhook: {str(e)}")
        return Response(content=f"Internal Server Error: {str(e)}", status_code=500)

    except Exception as e:
        print(f"Error processing webhook: {str(e)}")
        return f"Internal Server Error: {str(e)}", 500


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
