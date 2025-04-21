import boto3
import os
import sys
import time
import json

queue_url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("QUEUE_URL")
if not queue_url:
    print("[Worker] QUEUE_URL not provided.")
    exit(1)

print(f"[Worker] Starting job processor with queue: {queue_url}")
sqs = boto3.client("sqs")

# Poll for a message
response = sqs.receive_message(
    QueueUrl=queue_url,
    MaxNumberOfMessages=1,
    WaitTimeSeconds=10,
)

messages = response.get("Messages", [])
if not messages:
    print("[Worker] No messages to process.")
    exit(0)

message = messages[0]
receipt_handle = message["ReceiptHandle"]
body = message["Body"]

print(f"[Worker] Got message: {body}")
# Simulate processing
time.sleep(5)
print("[Worker] Done.")

# Delete message
sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
print("[Worker] Message deleted.")