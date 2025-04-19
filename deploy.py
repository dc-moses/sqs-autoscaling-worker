import boto3
import time
import uuid
import os
import sys
from botocore.exceptions import ClientError

STACK_NAME = "SQSWorkerStack"
TEMPLATE_FILE = "template.yml"
REGION = "us-east-1"
LAMBDA_NAME = "sqs-worker-lambda"

def create_bucket_and_upload():
    s3 = boto3.client("s3", region_name=REGION)
    bucket_name = f"worker-bucket-{uuid.uuid4().hex[:8]}"
    print(f"Creating bucket: {bucket_name}")
    try:
        s3.create_bucket(Bucket=bucket_name)
    except ClientError as e:
        print("❌ Bucket creation failed:", e)
        raise

    s3.upload_file("worker.py", bucket_name, "worker.py")
    print(f"Uploaded worker.py to s3://{bucket_name}/worker.py")
    return bucket_name

def get_default_subnet():
    ec2 = boto3.client("ec2", region_name=REGION)
    print("Fetching default subnet...")
    subnets = ec2.describe_subnets(
        Filters=[{"Name": "default-for-az", "Values": ["true"]}]
    )
    subnet_id = subnets["Subnets"][0]["SubnetId"]
    print(f"Using subnet: {subnet_id}")
    return subnet_id

def delete_stack():
    print(f"🧹 Deleting CloudFormation stack: {STACK_NAME}")
    cf = boto3.client("cloudformation", region_name=REGION)
    try:
        cf.delete_stack(StackName=STACK_NAME)
        waiter = cf.get_waiter("stack_delete_complete")
        waiter.wait(StackName=STACK_NAME)
        print("✅ Stack deleted.")
    except Exception as e:
        print("⚠️ Stack deletion failed:", e)

def delete_bucket(bucket_name):
    print(f"🧹 Deleting S3 bucket: {bucket_name}")
    s3 = boto3.resource("s3")
    bucket = s3.Bucket(bucket_name)
    try:
        bucket.objects.all().delete()
        bucket.delete()
        print(f"✅ Bucket {bucket_name} deleted.")
    except Exception as e:
        print("⚠️ Bucket deletion failed:", e)

def deploy_stack():
    cf = boto3.client("cloudformation", region_name=REGION)

    with open(TEMPLATE_FILE) as f:
        template_body = f.read()

    try:
        cf.create_stack(
            StackName=STACK_NAME,
            TemplateBody=template_body,
            Parameters=[
                {"ParameterKey": "WorkerScriptBucket", "ParameterValue": bucket_name},
                {"ParameterKey": "WorkerScriptKey", "ParameterValue": "worker.py"},
                {"ParameterKey": "SubnetId", "ParameterValue": subnet_id},
            ],
            Capabilities=["CAPABILITY_NAMED_IAM"]
        )
        print("Deploying CloudFormation stack...")
        waiter = cf.get_waiter("stack_create_complete")
        waiter.wait(StackName=STACK_NAME)
        print("✅ Stack created successfully.")

    except ClientError as e:
        print("❌ Stack creation failed:", e)
        if "AlreadyExistsException" in str(e):
            print("⚠️ Stack already exists.")
        raise e

    except Exception as e:
        print("❌ Stack creation failed. Cleaning up...")
        raise e

# ---- Deployment Flow ----
try:
    bucket_name = create_bucket_and_upload()
    subnet_id = get_default_subnet()
    deploy_stack()

except Exception:
    print("⚠️ Cleanup triggered due to failure.")
    delete_stack()
    if "bucket_name" in locals():
        delete_bucket(bucket_name)
    sys.exit(1)