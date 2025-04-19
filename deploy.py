import boto3
import time
import uuid
import os
import json
import base64
from botocore.exceptions import ClientError

STACK_NAME = "SQSWorkerStack"
TEMPLATE_FILE = "template.yml"
REGION = "us-east-1"
BUCKET_PREFIX = "worker-bucket-"

cf = boto3.client("cloudformation", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)
ec2 = boto3.client("ec2", region_name=REGION)
autoscaling = boto3.client("autoscaling", region_name=REGION)

def create_bucket_and_upload():
    bucket_name = f"{BUCKET_PREFIX}{uuid.uuid4().hex[:8]}"
    print(f"Creating bucket: {bucket_name}")
    s3.create_bucket(Bucket=bucket_name)
    s3.upload_file("worker.py", bucket_name, "worker.py")
    print(f"Uploaded worker.py to s3://{bucket_name}/worker.py")
    return bucket_name

def get_default_subnet():
    print("Fetching default subnet...")
    response = ec2.describe_subnets(Filters=[{"Name": "default-for-az", "Values": ["true"]}])
    subnet_id = response["Subnets"][0]["SubnetId"]
    print(f"Using subnet: {subnet_id}")
    return subnet_id

def deploy_stack(bucket_name, subnet_id):
    try:
        with open(TEMPLATE_FILE) as f:
            template_body = f.read()

        print("Deploying CloudFormation stack...")
        cf.create_stack(
            StackName=STACK_NAME,
            TemplateBody=template_body,
            Capabilities=["CAPABILITY_NAMED_IAM"],
            Parameters=[
                {"ParameterKey": "WorkerScriptBucket", "ParameterValue": bucket_name},
                {"ParameterKey": "WorkerScriptKey", "ParameterValue": "worker.py"},
                {"ParameterKey": "SubnetId", "ParameterValue": subnet_id},
            ]
        )

        waiter = cf.get_waiter("stack_create_complete")
        waiter.wait(StackName=STACK_NAME)
        print("✅ Stack created successfully.")
        return True

    except ClientError as e:
        if "AlreadyExistsException" in str(e):
            print(f"⚠️ Stack already exists.")
        else:
            print(f"❌ Stack creation failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def delete_stack():
    print(f"🧹 Deleting CloudFormation stack: {STACK_NAME}")
    try:
        cf.delete_stack(StackName=STACK_NAME)
        waiter = cf.get_waiter("stack_delete_complete")
        waiter.wait(StackName=STACK_NAME)
        print("✅ Stack deleted.")
    except Exception as e:
        print(f"⚠️ Failed to delete stack: {e}")

def delete_bucket(bucket_name):
    print(f"🧹 Deleting S3 bucket: {bucket_name}")
    try:
        s3.delete_object(Bucket=bucket_name, Key="worker.py")
        s3.delete_bucket(Bucket=bucket_name)
        print(f"✅ Bucket {bucket_name} deleted.")
    except Exception as e:
        print(f"⚠️ Failed to delete bucket: {e}")

if __name__ == "__main__":
    bucket_name = create_bucket_and_upload()
    subnet_id = get_default_subnet()
    success = deploy_stack(bucket_name, subnet_id)

    if not success:
        print("⚠️ Cleanup triggered due to failure.")
        delete_stack()
        delete_bucket(bucket_name)
        exit(1)