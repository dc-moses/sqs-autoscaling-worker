import boto3
import uuid
import os
import traceback

STACK_NAME = "SQSWorkerStack"
REGION = "us-east-1"
SCRIPT_KEY = "worker.py"

s3 = boto3.client("s3", region_name=REGION)
cf = boto3.client("cloudformation", region_name=REGION)
ec2 = boto3.client("ec2", region_name=REGION)


def create_bucket_and_upload():
    bucket_name = f"worker-bucket-{uuid.uuid4().hex[:8]}"
    print(f"Creating bucket: {bucket_name}")

    s3.create_bucket(
        Bucket=bucket_name,
        CreateBucketConfiguration={"LocationConstraint": REGION}
    )

    s3.upload_file(SCRIPT_KEY, bucket_name, SCRIPT_KEY)
    print(f"Uploaded {SCRIPT_KEY} to s3://{bucket_name}/{SCRIPT_KEY}")
    return bucket_name


def get_default_subnet():
    subnets = ec2.describe_subnets(
        Filters=[{"Name": "default-for-az", "Values": ["true"]}]
    )["Subnets"]
    subnet_id = subnets[0]["SubnetId"]
    print(f"Using subnet: {subnet_id}")
    return subnet_id


def deploy_stack():
    bucket = create_bucket_and_upload()
    subnet_id = get_default_subnet()

    with open("template.yml") as f:
        template_body = f.read()

    print("Deploying CloudFormation stack...")

    # Use list_stacks instead of describe_stacks for reliability
    stack_exists = False
    stacks = cf.list_stacks(
        StackStatusFilter=[
            "CREATE_IN_PROGRESS", "CREATE_FAILED", "CREATE_COMPLETE",
            "ROLLBACK_IN_PROGRESS", "ROLLBACK_FAILED", "ROLLBACK_COMPLETE",
            "UPDATE_IN_PROGRESS", "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS",
            "UPDATE_COMPLETE", "UPDATE_ROLLBACK_IN_PROGRESS",
            "UPDATE_ROLLBACK_FAILED", "UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS",
            "UPDATE_ROLLBACK_COMPLETE"
        ]
    )["StackSummaries"]

    for stack in stacks:
        if stack["StackName"] == STACK_NAME:
            stack_exists = True
            break

    parameters = [
        {"ParameterKey": "WorkerScriptBucket", "ParameterValue": bucket},
        {"ParameterKey": "WorkerScriptKey", "ParameterValue": SCRIPT_KEY},
        {"ParameterKey": "SubnetId", "ParameterValue": subnet_id},
    ]

    try:
        if stack_exists:
            print(f"Stack {STACK_NAME} exists — updating.")
            cf.update_stack(
                StackName=STACK_NAME,
                TemplateBody=template_body,
                Capabilities=["CAPABILITY_NAMED_IAM"],
                Parameters=parameters
            )
            waiter = cf.get_waiter("stack_update_complete")
        else:
            print(f"Stack {STACK_NAME} does not exist — creating.")
            cf.create_stack(
                StackName=STACK_NAME,
                TemplateBody=template_body,
                Capabilities=["CAPABILITY_NAMED_IAM"],
                Parameters=parameters,
                OnFailure="DO_NOTHING"
            )
            waiter = cf.get_waiter("stack_create_complete")

        waiter.wait(StackName=STACK_NAME)
        print("✅ Stack deployed successfully.")
        return bucket

    except Exception as e:
        print("❌ Stack deployment failed. Fetching failure events...")
        try:
            events = cf.describe_stack_events(StackName=STACK_NAME)["StackEvents"]
            for event in events[:5]:
                print("Error:", event.get("ResourceStatusReason"))
        except Exception as nested:
            print("⚠️ Failed to retrieve stack events:", nested)

        print("🚫 Skipping cleanup so you can inspect the failed stack.")
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    deploy_stack()