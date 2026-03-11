import os
import json
import sys
from google.cloud import pubsub_v1

def approve_ticket(session_id, user_id, ticket_id):
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    topic_id = "gc_incoming_messages"
    
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, topic_id)
    
    # Message to resume the agent
    data = {
        "session_id": session_id,
        "user_id": user_id,
        "user_query": f"RESUME_FLOW: {ticket_id} approved", # Keyword for main.py to handle resume
        "user_state": {"ticket_id": ticket_id, "status": "approved"}
    }
    
    data_bytes = json.dumps(data).encode("utf-8")
    future = publisher.publish(topic_path, data_bytes)
    print(f"Published approval message for ticket {ticket_id} (ID: {future.result()})")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python approve_ticket.py <session_id> <user_id> <ticket_id>")
        sys.exit(1)
        
    session_id = sys.argv[1]
    user_id = sys.argv[2]
    ticket_id = sys.argv[3]
    approve_ticket(session_id, user_id, ticket_id)
