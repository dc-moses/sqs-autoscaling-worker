import boto3
import time
import uuid
import os
import botocore.exceptions

cf = boto3.client('cloudformation')
s3 = boto3.client('s3')

STACK_NAME = 'SQSWorkerStack'
TEMPLATE_FILE = 'template.yaml'
SCRIPT_FILE = 'worker.py'
REGION = 'us-east-1'

bucket_name = f"worker-bucket-{uuid.uuid4().hex[:8]}"
script_key = 'worker.py'

def create_bucket_and_upload():
    print(f"Creating bucket: {bucket_name}")
    if REGION == 'us-east-1':
        s3.create_bucket(Bucket=bucket_name)
    else:
        s3.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={'LocationConstraint': REGION}
        )

    s3.upload_file(SCRIPT_FILE, bucket_name, script_key)
    print(f"Uploaded {SCRIPT_FILE} to s3://{bucket_name}/{script_key}")

def deploy_stack():
    with open(TEMPLATE_FILE) as f:
        template_body = f.read()

    print("Deploying CloudFormation stack...")
    try:
        subnet_id = os.environ.get('SUBNET_ID')
        if not subnet_id:
            raise Exception("Missing SUBNET_ID environment variable")
        print(f"Using subnet: {subnet_id}")

        cf.create_stack(
            StackName=STACK_NAME,
            TemplateBody=template_body,
            Capabilities=['CAPABILITY_NAMED_IAM'],
            Parameters=[
                {'ParameterKey': 'WorkerScriptBucket', 'ParameterValue': bucket_name},
                {'ParameterKey': 'WorkerScriptKey', 'ParameterValue': script_key},
                {'ParameterKey': 'SubnetId', 'ParameterValue': subnet_id},
            ]
        )

        waiter = cf.get_waiter('stack_create_complete')
        waiter.wait(StackName=STACK_NAME)
        print("✅ Stack deployed successfully.")

    except botocore.exceptions.WaiterError as e:
        print("❌ Stack creation failed. Fetching failure events...")
        events = cf.describe_stack_events(StackName=STACK_NAME)['StackEvents']
        for event in events:
            if event['ResourceStatus'] == 'CREATE_FAILED':
                print(f"[ERROR] {event['LogicalResourceId']} ({event['ResourceType']}): {event['ResourceStatusReason']}")
        raise e
    except botocore.exceptions.ClientError as e:
        print(f"❌ Client error: {e}")
        raise e

def cleanup():
    try:
        print(f"Deleting CloudFormation stack: {STACK_NAME}")
        cf.delete_stack(StackName=STACK_NAME)
        waiter = cf.get_waiter('stack_delete_complete')
        waiter.wait(StackName=STACK_NAME)
        print("🧹 Stack deleted.")
    except Exception as e:
        print(f"⚠️ Failed to delete stack: {e}")

    try:
        print(f"Deleting S3 bucket: {bucket_name}")
        s3_resource = boto3.resource('s3')
        bucket = s3_resource.Bucket(bucket_name)
        bucket.objects.all().delete()
        bucket.delete()
        print(f"🧹 Bucket {bucket_name} deleted.")
    except Exception as e:
        print(f"⚠️ Failed to delete bucket: {e}")

if __name__ == '__main__':
    create_bucket_and_upload()
    try:
        deploy_stack()
    except Exception as e:
        print("Cleaning up due to failure...")
    finally:
        cleanup()