import boto3
import json
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--queue-url', required=True, help='SQS Queue URL')
parser.add_argument('--wait', type=int, default=10, help='Wait time in seconds')
args = parser.parse_args()

sqs = boto3.client('sqs')

message = {
    "wait_seconds": args.wait
}

response = sqs.send_message(
    QueueUrl=args.queue_url,
    MessageBody=json.dumps(message)
)

print(f"Sent message with wait={args.wait} seconds. MessageId: {response['MessageId']}")
