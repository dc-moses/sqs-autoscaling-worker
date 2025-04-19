import boto3
import os
import time
import uuid
import botocore.exceptions

REGION = "us-east-1"
STACK_NAME = "SQSWorkerStack"
SCRIPT_KEY = "worker.py"
SCRIPT_PATH = "worker.py"
TEMPLATE_PATH = "template.yml"

s3 = boto3.client("s3", region_name=REGION)
cf = boto3.client("cloudformation", region_name=REGION)
ec2 = boto3.client("ec2", region_name=REGION)
autoscaling = boto3.client("autoscaling", region_name=REGION)


def create_bucket_and_upload():
    bucket_name = f"worker-bucket-{uuid.uuid4().hex[:8]}"
    print(f"Creating bucket: {bucket_name}")
    try:
        s3.create_bucket(Bucket=bucket_name)
    except botocore.exceptions.ClientError as e:
        print(f"❌ Failed to create bucket: {e}")
        raise

    s3.upload_file(SCRIPT_PATH, bucket_name, SCRIPT_KEY)
    print(f"✅ Uploaded {SCRIPT_PATH} to s3://{bucket_name}/{SCRIPT_KEY}")
    return bucket_name


def get_default_subnet():
    print("Fetching default subnet...")
    subnets = ec2.describe_subnets(Filters=[{"Name": "default-for-az", "Values": ["true"]}])
    subnet_id = subnets["Subnets"][0]["SubnetId"]
    print(f"Using subnet: {subnet_id}")
    return subnet_id


def deploy_stack(bucket, subnet):
    print("Deploying CloudFormation stack...")
    with open(TEMPLATE_PATH) as f:
        template_body = f.read()

    try:
        cf.create_stack(
            StackName=STACK_NAME,
            TemplateBody=template_body,
            Capabilities=["CAPABILITY_NAMED_IAM"],
            Parameters=[
                {"ParameterKey": "WorkerScriptBucket", "ParameterValue": bucket},
                {"ParameterKey": "WorkerScriptKey", "ParameterValue": SCRIPT_KEY},
                {"ParameterKey": "SubnetId", "ParameterValue": subnet},
            ]
        )
    except botocore.exceptions.ClientError as e:
        if "AlreadyExistsException" in str(e):
            print("⚠️ Stack already exists.")
        else:
            raise

    try:
        waiter = cf.get_waiter("stack_create_complete")
        waiter.wait(StackName=STACK_NAME)
        print("✅ Stack created successfully.")
        return True
    except botocore.exceptions.WaiterError as e:
        print(f"❌ Stack creation failed: {e}")
        log_stack_failure()
        return False


def log_stack_failure():
    print("🔍 Logging stack failure reasons...")
    try:
        events = cf.describe_stack_events(StackName=STACK_NAME)["StackEvents"]
        for event in events:
            if event["ResourceStatus"] in ["CREATE_FAILED", "ROLLBACK_IN_PROGRESS", "ROLLBACK_COMPLETE"]:
                print(f"🔴 {event['LogicalResourceId']}: {event.get('ResourceStatusReason', 'No reason provided')}")
    except Exception as e:
        print(f"⚠️ Could not retrieve stack events: {e}")


def wait_for_scale_events():
    print("⏳ Waiting for scale-up...")
    asg_name = get_asg_name()
    instance_id = None

    # Wait for scale-up
    for i in range(40):
        response = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        asg = response["AutoScalingGroups"][0]
        instances = asg["Instances"]
        if len(instances) > 0:
            instance_id = instances[0]["InstanceId"]
            print(f"✅ ASG scaled up. Instance ID: {instance_id}")
            break
        print(f"Waiting for scale-up... Poll {i+1}")
        time.sleep(30)

    print("⏳ Waiting for scale-down...")
    # Wait for scale-down
    for i in range(40):
        response = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        instance_count = len(response["AutoScalingGroups"][0]["Instances"])
        print(f"Poll {i+1}: Current instance count = {instance_count}")
        if instance_count == 0:
            print("✅ ASG scaled down to 0.")
            return
        time.sleep(30)

    print("❌ EC2 instance did not terminate in expected time.")


def get_asg_name():
    resources = cf.describe_stack_resources(StackName=STACK_NAME)["StackResources"]
    for res in resources:
        if res["ResourceType"] == "AWS::AutoScaling::AutoScalingGroup":
            return res["PhysicalResourceId"]
    raise Exception("ASG not found")


def cleanup(bucket):
    print("⚠️ Cleanup triggered due to failure.")
    try:
        print(f"🧹 Deleting CloudFormation stack: {STACK_NAME}")
        cf.delete_stack(StackName=STACK_NAME)
        cf.get_waiter("stack_delete_complete").wait(StackName=STACK_NAME)
        print("✅ Stack deleted.")
    except Exception as e:
        print(f"⚠️ Failed to delete stack: {e}")

    try:
        print(f"🧹 Deleting S3 bucket: {bucket}")
        s3_resource = boto3.resource("s3", region_name=REGION)
        bucket_obj = s3_resource.Bucket(bucket)
        bucket_obj.objects.all().delete()
        bucket_obj.delete()
        print(f"✅ Bucket {bucket} deleted.")
    except Exception as e:
        print(f"⚠️ Failed to delete bucket: {e}")


if __name__ == "__main__":
    bucket_name = create_bucket_and_upload()
    subnet_id = get_default_subnet()
    success = deploy_stack(bucket_name, subnet_id)

    if success:
        wait_for_scale_events()
    else:
        cleanup(bucket_name)
        exit(1)
