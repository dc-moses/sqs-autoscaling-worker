import boto3
import botocore
import time
import uuid
import os

STACK_NAME = "SQSWorkerStack"
REGION = "us-east-1"
LAMBDA_NAME = os.getenv("LAMBDA_NAME", "sqs-worker-lambda")

cf = boto3.client("cloudformation", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)
ec2 = boto3.client("ec2", region_name=REGION)


def create_bucket_and_upload():
    unique_suffix = str(uuid.uuid4())[:8]
    bucket_name = f"worker-bucket-{unique_suffix}"
    print(f"Creating bucket: {bucket_name}")

    s3.create_bucket(
        Bucket=bucket_name,
        CreateBucketConfiguration={"LocationConstraint": REGION}
    )

    s3.upload_file("worker.py", bucket_name, "worker.py")
    print(f"Uploaded worker.py to s3://{bucket_name}/worker.py")
    return bucket_name


def discover_default_subnet():
    subnets = ec2.describe_subnets(
        Filters=[{"Name": "default-for-az", "Values": ["true"]}]
    )["Subnets"]

    if not subnets:
        raise Exception("No default subnet found.")
    subnet_id = subnets[0]["SubnetId"]
    print(f"Using subnet: {subnet_id}")
    return subnet_id


def describe_stack_failures():
    try:
        events = cf.describe_stack_events(StackName=STACK_NAME)["StackEvents"]
        for event in events:
            status = event["ResourceStatus"]
            if "FAILED" in status or "ROLLBACK" in status:
                reason = event.get("ResourceStatusReason", "No reason provided")
                print(f"Error: {event['LogicalResourceId']} ({event['ResourceType']}): {reason}")
    except Exception as e:
        print(f"⚠️ Could not fetch stack events: {e}")


def deploy_stack():
    with open("template.yml") as f:
        template_body = f.read()

    print("Deploying CloudFormation stack...")

    try:
        cf.create_stack(
            StackName=STACK_NAME,
            TemplateBody=template_body,
            Capabilities=["CAPABILITY_NAMED_IAM"],
            Parameters=[
                {"ParameterKey": "WorkerScriptBucket", "ParameterValue": bucket_name},
                {"ParameterKey": "WorkerScriptKey", "ParameterValue": "worker.py"},
                {"ParameterKey": "SubnetId", "ParameterValue": subnet_id},
            ],
        )

        waiter = cf.get_waiter("stack_create_complete")
        waiter.wait(StackName=STACK_NAME)
        print("✅ Stack created successfully.")

    except botocore.exceptions.ClientError as e:
        print("❌ Stack creation failed. Cleaning up...")
        describe_stack_failures()
        try:
            print(f"🧹 Deleting CloudFormation stack: {STACK_NAME}")
            cf.delete_stack(StackName=STACK_NAME)
            waiter = cf.get_waiter("stack_delete_complete")
            waiter.wait(StackName=STACK_NAME)
            print("🧹 Stack deleted.")
        except Exception as delete_error:
            print(f"⚠️ Failed to delete stack: {delete_error}")
        raise e


if __name__ == "__main__":
    bucket_name = create_bucket_and_upload()
    subnet_id = discover_default_subnet()
    deploy_stack()