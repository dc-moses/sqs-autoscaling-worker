import boto3
import os
import sys
import time
import json
import requests

def wait_until_instance_running():
    try:
        identity_doc = requests.get("http://169.254.169.254/latest/dynamic/instance-identity/document", timeout=5).json()
        instance_id = identity_doc["instanceId"]
        region = identity_doc["region"]
    except Exception as e:
        print(f"[Startup Delay] Failed to get instance metadata: {e}")
        return

    ec2 = boto3.client("ec2", region_name=region)
    print(f"[Startup Delay] Waiting for instance {instance_id} to report state 'running'...")
    for i in range(30):
        state = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"][0]["Instances"][0]["State"]["Name"]
        print(f"[Startup Delay] Poll {i+1}: Current state is '{state}'")
        if state == "running":
            print(f"[Startup Delay] Instance is running.")
            return
        time.sleep(5)

wait_until_instance_running()

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