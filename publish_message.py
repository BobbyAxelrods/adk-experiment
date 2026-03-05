from dotenv import load_dotenv
import os
import json
from google.cloud import pubsub_v1
import time

load_dotenv()

# Setup for local emulator if environment variables are set
project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "demo-project")

# Topic/Subscription IDs
incoming_topic_id = os.getenv("INCOMING_TOPIC", "gc_incoming_messages")
outgoing_sub_id = os.getenv("OUTGOING_SUBSCRIPTION", "gc_outgoing_messages_sub")

publisher = pubsub_v1.PublisherClient()
subscriber = pubsub_v1.SubscriberClient()

incoming_topic_path = publisher.topic_path(project_id, incoming_topic_id)
outgoing_sub_path = subscriber.subscription_path(project_id, outgoing_sub_id)

def publish_query(query: str):
    """Publishes a query to the incoming messages topic."""
    message = {
        "session_id": "test-session-1",
        "user_id": "test-user-1",
        "user_query": query,
        "user_state": {}
    }
    data = json.dumps(message).encode("utf-8")
    future = publisher.publish(incoming_topic_path, data)
    print(f"Published query to {incoming_topic_id}: {query} (ID: {future.result()})")

def callback(message: pubsub_v1.subscriber.message.Message) -> None:
    data = json.loads(message.data.decode("utf-8"))
    print("\n--- Received Output Message ---")
    print(json.dumps(data, indent=2))
    print("-------------------------------\n")
    message.ack()

def listen_for_results(timeout=30.0):
    """Listens for messages from the outgoing messages subscription."""
    print(f"Listening for messages on {outgoing_sub_path} for {timeout} seconds...\n")
    
    streaming_pull_future = subscriber.subscribe(outgoing_sub_path, callback=callback)

    with subscriber:
        try:
            streaming_pull_future.result(timeout=timeout)
        except TimeoutError:
            streaming_pull_future.cancel()
            streaming_pull_future.result()
        except Exception as e:
            print(f"Listening stopped due to error: {e}")
            streaming_pull_future.cancel()

if __name__ == "__main__":
    # 1. Publish a test query
    publish_query("What are the benefits of Product A?")
    
    # 2. Listen for the response
    listen_for_results(timeout=120.0)
