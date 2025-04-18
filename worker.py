import boto3
import time
import sys
import json

sqs = boto3.client('sqs', region_name='us-east-1')  # Adjust region if needed

def process_message(message):
    try:
        body = json.loads(message['Body'])
        wait_time = int(body.get('wait_seconds', 10))
        print(f"[Worker] Waiting for {wait_time} seconds...")
        time.sleep(wait_time)
        print("[Worker] Done.")
    except Exception as e:
        print(f"[Worker] Error: {e}")

if __name__ == '__main__':
    queue_url = sys.argv[1]  # Passed in from user data

    print(f"[Worker] Polling SQS queue: {queue_url}")

    while True:
        response = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20
        )

        messages = response.get('Messages', [])

        for message in messages:
            process_message(message)
            sqs.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=message['ReceiptHandle']
            )
