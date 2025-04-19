import boto3
import json
import time
import uuid
import os
from botocore.exceptions import ClientError, WaiterError

STACK_NAME = "SQSWorkerStack"
REGION = "us-east-1"
SCRIPT_KEY = "worker.py"
SCRIPT_FILE = "worker.py"
TEMPLATE_FILE = "template.yml"

s3 = boto3.client("s3", region_name=REGION)
cf = boto3.client("cloudformation", region_name=REGION)
ec2 = boto3.client("ec2", region_name=REGION)


def create_bucket_and_upload():
    unique_id = str(uuid.uuid4())[:8]
    bucket_name = f"worker-bucket-{unique_id}"
    print(f"Creating bucket: {bucket_name}")

    try:
        # us-east-1 does NOT require LocationConstraint
        s3.create_bucket(Bucket=bucket_name)
    except ClientError as e:
        print("Bucket creation failed:", e)
        raise

    s3.upload_file(SCRIPT_FILE, bucket_name, SCRIPT_KEY)
    print(f"Uploaded {SCRIPT_FILE} to s3://{bucket_name}/{SCRIPT_KEY}")
    return bucket_name


def get_default_subnet():
    print("Fetching default subnet...")
    response = ec2.describe_subnets(
        Filters=[{"Name": "default-for-az", "Values": ["true"]}]
    )
    subnet_id = response["Subnets"][0]["SubnetId"]
    print(f"Using subnet: {subnet_id}")
    return subnet_id


def deploy_stack():
    bucket = create_bucket_and_upload()
    subnet_id = get_default_subnet()

    with open(TEMPLATE_FILE) as f:
        template_body = f.read()

    print("Deploying CloudFormation stack...")
    try:
        cf.create_stack(
            StackName=STACK_NAME,
            TemplateBody=template_body,
            Capabilities=["CAPABILITY_NAMED_IAM"],
            Parameters=[
                {"ParameterKey": "WorkerScriptBucket", "ParameterValue": bucket},
                {"ParameterKey": "WorkerScriptKey", "ParameterValue": SCRIPT_KEY},
                {"ParameterKey": "SubnetId", "ParameterValue": subnet_id},
            ],
        )
        waiter = cf.get_waiter("stack_create_complete")
        waiter.wait(StackName=STACK_NAME)
        print("✅ Stack created successfully.")
    except ClientError as e:
        print("Error:", e)
        raise
    except WaiterError as e:
        print("❌ Stack creation failed. Fetching failure events...")
        events = cf.describe_stack_events(StackName=STACK_NAME)["StackEvents"]
        for event in events[:5]:
            print(
                f"Error:  {event['LogicalResourceId']} ({event['ResourceType']}): {event.get('ResourceStatusReason', '')}"
            )
        raise
    except Exception as e:
        print("Unhandled error during deployment:", e)
        raise

    return bucket


def delete_stack_and_bucket(bucket_name):
    print(f"Deleting CloudFormation stack: {STACK_NAME}")
    try:
        cf.delete_stack(StackName=STACK_NAME)
        waiter = cf.get_waiter("stack_delete_complete")
        waiter.wait(StackName=STACK_NAME)
        print(f"🧹 Stack deleted.")
    except Exception as e:
        print("Failed to delete stack:", e)

    print(f"Deleting S3 bucket: {bucket_name}")
    try:
        s3_resource = boto3.resource("s3", region_name=REGION)
        bucket = s3_resource.Bucket(bucket_name)
        bucket.objects.all().delete()
        bucket.delete()
        print(f"🧹 Bucket {bucket_name} deleted.")
    except Exception as e:
        print("Failed to delete bucket:", e)


if __name__ == "__main__":
    try:
        bucket_name = deploy_stack()
    except Exception:
        print("Cleaning up due to failure...")
        try:
            delete_stack_and_bucket(bucket_name)
        except:
            print("Cleanup encountered an error.")
        exit(1)
