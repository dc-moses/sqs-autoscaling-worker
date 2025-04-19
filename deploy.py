import boto3
import uuid
import time
import traceback

STACK_NAME = "SQSWorkerStack"
REGION = "us-east-1"

s3 = boto3.client("s3", region_name=REGION)
cf = boto3.client("cloudformation", region_name=REGION)
ec2 = boto3.client("ec2", region_name=REGION)

def create_bucket_and_upload():
    bucket_name = f"worker-bucket-{uuid.uuid4().hex[:8]}"
    print(f"Creating bucket: {bucket_name}")

    if REGION == "us-east-1":
        s3.create_bucket(Bucket=bucket_name)
    else:
        s3.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={"LocationConstraint": REGION}
        )

    s3.upload_file("worker.py", bucket_name, "worker.py")
    print(f"Uploaded worker.py to s3://{bucket_name}/worker.py")
    return bucket_name

def get_default_subnet():
    subnets = ec2.describe_subnets(
        Filters=[{"Name": "default-for-az", "Values": ["true"]}]
    )
    subnet_id = subnets["Subnets"][0]["SubnetId"]
    print(f"Using subnet: {subnet_id}")
    return subnet_id

def deploy_stack():
    bucket = create_bucket_and_upload()
    subnet_id = get_default_subnet()

    with open("template.yml") as f:
        template_body = f.read()

    print("Deploying CloudFormation stack...")

    cf.create_stack(
        StackName=STACK_NAME,
        TemplateBody=template_body,
        Capabilities=["CAPABILITY_NAMED_IAM"],
        Parameters=[
            {"ParameterKey": "WorkerScriptBucket", "ParameterValue": bucket},
            {"ParameterKey": "WorkerScriptKey", "ParameterValue": "worker.py"},
            {"ParameterKey": "SubnetId", "ParameterValue": subnet_id},
        ],
        OnFailure="DO_NOTHING"
    )

    waiter = cf.get_waiter("stack_create_complete")
    try:
        waiter.wait(StackName=STACK_NAME)
        print("✅ Stack created successfully.")
    except Exception as e:
        print("❌ Stack creation failed. Fetching failure events...")
        try:
            events = cf.describe_stack_events(StackName=STACK_NAME)["StackEvents"]
            for event in events[:5]:
                print("Error:", event.get("ResourceStatusReason"))
        except Exception as nested:
            print("⚠️ Failed to retrieve stack events:", nested)

        # Skip cleanup to allow console debugging
        print("🚫 Skipping cleanup so you can inspect the failed stack in the AWS Console.")
        traceback.print_exc()

if __name__ == "__main__":
    deploy_stack()