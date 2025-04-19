import boto3
import botocore
import time
import uuid
import os
import sys

STACK_NAME = "SQSWorkerStack"
TEMPLATE_FILE = "template.yml"
REGION = "us-east-1"
SCRIPT_KEY = "worker.py"

def generate_bucket_name():
    return f"worker-bucket-{uuid.uuid4().hex[:8]}"

def get_default_subnet():
    ec2 = boto3.client("ec2", region_name=REGION)
    subnets = ec2.describe_subnets(Filters=[{"Name": "default-for-az", "Values": ["true"]}])
    if not subnets["Subnets"]:
        raise Exception("No default subnet found.")
    return subnets["Subnets"][0]["SubnetId"]

def create_bucket_and_upload():
    s3 = boto3.client("s3", region_name=REGION)
    bucket_name = generate_bucket_name()
    print(f"Creating bucket: {bucket_name}")
    
    s3.create_bucket(
        Bucket=bucket_name,
        CreateBucketConfiguration={"LocationConstraint": REGION}
    )

    s3.upload_file("worker.py", bucket_name, SCRIPT_KEY)
    print(f"Uploaded worker.py to s3://{bucket_name}/{SCRIPT_KEY}")
    return bucket_name

def deploy_stack():
    cf = boto3.client("cloudformation", region_name=REGION)
    try:
        with open(TEMPLATE_FILE) as f:
            template_body = f.read()

        bucket = create_bucket_and_upload()
        subnet_id = get_default_subnet()
        print(f"Using subnet: {subnet_id}")

        print("Deploying CloudFormation stack...")
        cf.create_stack(
            StackName=STACK_NAME,
            TemplateBody=template_body,
            Parameters=[
                {"ParameterKey": "WorkerScriptBucket", "ParameterValue": bucket},
                {"ParameterKey": "WorkerScriptKey", "ParameterValue": SCRIPT_KEY},
                {"ParameterKey": "SubnetId", "ParameterValue": subnet_id}
            ],
            Capabilities=["CAPABILITY_NAMED_IAM"]
        )

        waiter = cf.get_waiter("stack_create_complete")
        waiter.wait(StackName=STACK_NAME)
        print("✅ Stack created successfully.")

    except botocore.exceptions.WaiterError as e:
        print("❌ Stack creation failed. Fetching failure events...")

        try:
            events = cf.describe_stack_events(StackName=STACK_NAME)["StackEvents"]
            for event in events:
                if event["ResourceStatus"] in ["CREATE_FAILED", "ROLLBACK_IN_PROGRESS", "ROLLBACK_COMPLETE"]:
                    print(f"Error: {event['LogicalResourceId']} ({event['ResourceType']}): {event.get('ResourceStatusReason', '')}")
        except Exception as event_err:
            print(f"Could not fetch stack events: {event_err}")

        print("Cleaning up due to failure...")

        try:
            print(f"Deleting CloudFormation stack: {STACK_NAME}")
            cf.delete_stack(StackName=STACK_NAME)
            waiter = cf.get_waiter("stack_delete_complete")
            waiter.wait(StackName=STACK_NAME)
            print("🧹 Stack deleted.")
        except Exception as stack_err:
            print(f"Failed to delete stack: {stack_err}")

        try:
            print(f"Deleting S3 bucket: {bucket}")
            s3 = boto3.resource("s3", region_name=REGION)
            bucket_resource = s3.Bucket(bucket)
            bucket_resource.objects.all().delete()
            bucket_resource.delete()
            print(f"🧹 Bucket {bucket} deleted.")
        except Exception as bucket_err:
            print(f"Failed to delete bucket: {bucket_err}")

        sys.exit(1)

if __name__ == "__main__":
    deploy_stack()