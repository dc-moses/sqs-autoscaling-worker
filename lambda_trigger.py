import json
import boto3
import os

sqs = boto3.client('sqs')
QUEUE_URL = os.environ['QUEUE_URL']

def lambda_handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        wait = int(body.get('wait_seconds', 10))

        message = {
            "wait_seconds": wait
        }

        response = sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(message)
        )

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Job enqueued',
                'wait_seconds': wait,
                'messageId': response['MessageId']
            })
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }
