import boto3
import botocore
import os
import time
import uuid

REGION = "us-east-1"
STACK_NAME = "SQSWorkerStack"
SCRIPT_KEY = "worker.py"
TEMPLATE_FILE = "template.yml"

s3 = boto3.client("s3", region_name=REGION)
cf = boto3.client("cloudformation", region_name=REGION)
ec2 = boto3.client("ec2", region_name=REGION)


def generate_unique_bucket_name():
    return f"worker-bucket-{uuid.uuid4().hex[:8]}"


def create_bucket_and_upload():
    bucket_name = generate_unique_bucket_name()
    print(f"Creating bucket: {bucket_name}")
    s3.create_bucket(Bucket=bucket_name)
    s3.upload_file("worker.py", bucket_name, SCRIPT_KEY)
    print(f"Uploaded worker.py to s3://{bucket_name}/{SCRIPT_KEY}")
    return bucket_name


def get_default_subnet():
    subnets = ec2.describe_subnets(
        Filters=[{"Name": "default-for-az", "Values": ["true"]}]
    )
    if not subnets["Subnets"]:
        raise Exception("No default subnet found")
    subnet_id = subnets["Subnets"][0]["SubnetId"]
    print(f"Using subnet: {subnet_id}")
    return subnet_id


def deploy_stack(bucket_name, subnet_id):
    with open(TEMPLATE_FILE) as f:
        template_body = f.read()

    try:
        print("Deploying CloudFormation stack...")
        cf.create_stack(
            StackName=STACK_NAME,
            TemplateBody=template_body,
            Parameters=[
                {"ParameterKey": "WorkerScriptBucket", "ParameterValue": bucket_name},
                {"ParameterKey": "WorkerScriptKey", "ParameterValue": SCRIPT_KEY},
                {"ParameterKey": "SubnetId", "ParameterValue": subnet_id},
            ],
            Capabilities=["CAPABILITY_NAMED_IAM"],
        )
        waiter = cf.get_waiter("stack_create_complete")
        waiter.wait(StackName=STACK_NAME)
        print("✅ Stack created successfully.")

    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "AlreadyExistsException":
            print("Stack already exists. Updating stack...")
            cf.update_stack(
                StackName=STACK_NAME,
                TemplateBody=template_body,
                Parameters=[
                    {"ParameterKey": "WorkerScriptBucket", "ParameterValue": bucket_name},
                    {"ParameterKey": "WorkerScriptKey", "ParameterValue": SCRIPT_KEY},
                    {"ParameterKey": "SubnetId", "ParameterValue": subnet_id},
                ],
                Capabilities=["CAPABILITY_NAMED_IAM"],
            )
            waiter = cf.get_waiter("stack_update_complete")
            waiter.wait(StackName=STACK_NAME)
            print("✅ Stack updated successfully.")
        else:
            print("❌ Stack creation failed. Fetching failure events...")
            events = cf.describe_stack_events(StackName=STACK_NAME)["StackEvents"]
            for event in events[:5]:
                print(
                    f"Error:  {event['LogicalResourceId']} ({event['ResourceType']}): {event.get('ResourceStatusReason', 'No reason provided')}"
                )
            raise


def delete_stack():
    print(f"Deleting CloudFormation stack: {STACK_NAME}")
    cf.delete_stack(StackName=STACK_NAME)
    waiter = cf.get_waiter("stack_delete_complete")
    waiter.wait(StackName=STACK_NAME)
    print("🧹 Stack deleted.")


def delete_bucket(bucket_name):
    print(f"Deleting S3 bucket: {bucket_name}")
    try:
        s3_resource = boto3.resource("s3")
        bucket = s3_resource.Bucket(bucket_name)
        bucket.objects.all().delete()
        bucket.delete()
        print(f"🧹 Bucket {bucket_name} deleted.")
    except Exception as e:
        print(f"⚠️ Error deleting bucket {bucket_name}: {e}")


if __name__ == "__main__":
    try:
        bucket_name = create_bucket_and_upload()
        subnet_id = get_default_subnet()
        deploy_stack(bucket_name, subnet_id)
    except Exception as e:
        print(f"Deployment error: {e}")
        if "bucket_name" in locals():
            delete_stack()
            delete_bucket(bucket_name)
        exit(1)