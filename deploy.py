import boto3
import os
import time
import uuid
import botocore.exceptions
import re

REGION = "us-east-1"
STACK_NAME = "SQSWorkerStack"
SCRIPT_KEY = "worker.py"
SCRIPT_PATH = "worker.py"
TEMPLATE_PATH = "template.yml"

s3 = boto3.client("s3", region_name=REGION)
cf = boto3.client("cloudformation", region_name=REGION)
ec2 = boto3.client("ec2", region_name=REGION)
lambda_client = boto3.client("lambda", region_name=REGION)
events = boto3.client("events", region_name=REGION)


def create_bucket_and_upload():
    bucket_name = f"worker-bucket-{uuid.uuid4().hex[:8]}"
    print(f"Creating bucket: {bucket_name}")
    s3.create_bucket(Bucket=bucket_name)
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
                {"ParameterKey": "SubnetId", "ParameterValue": subnet}
            ]
        )
        waiter = cf.get_waiter("stack_create_complete")
        waiter.wait(StackName=STACK_NAME)
        print("✅ Stack created successfully.")
        return True
    except botocore.exceptions.ClientError as e:
        if "AlreadyExistsException" in str(e):
            print("⚠️ Stack already exists.")
            return True
        else:
            print(f"❌ Stack creation failed: {e}")
            return False


def get_stack_output(key):
    response = cf.describe_stacks(StackName=STACK_NAME)
    outputs = response["Stacks"][0].get("Outputs", [])
    for output in outputs:
        if output["OutputKey"] == key:
            return output["OutputValue"]
    return None


def update_lambda_env(lambda_name, queue_url, asg_name):
    print("🔧 Updating Lambda environment with QUEUE_URL and ASG_NAME...")
    lambda_client.update_function_configuration(
        FunctionName=lambda_name,
        Environment={
            "Variables": {
                "QUEUE_URL": queue_url,
                "ASG_NAME": asg_name
            }
        }
    )
    print("✅ Lambda environment updated.")


def ensure_eventbridge_rule(lambda_arn):
    print("🔍 Checking if EventBridge rule exists...")
    rule_name = "ASGScalerSchedule"
    rules = events.list_rules(NamePrefix=rule_name).get("Rules", [])
    rule_arn = None

    if not rules:
        print("➕ Creating EventBridge rule...")
        response = events.put_rule(
            Name=rule_name,
            ScheduleExpression="rate(1 minute)",
            State="ENABLED"
        )
        rule_arn = response["RuleArn"]
    else:
        print("✅ Rule already exists.")
        rule_arn = rules[0]["Arn"]

    targets = events.list_targets_by_rule(Rule=rule_name).get("Targets", [])
    if not any(t["Arn"] == lambda_arn for t in targets):
        print("➕ Adding Lambda target to EventBridge rule...")
        events.put_targets(
            Rule=rule_name,
            Targets=[
                {
                    "Id": "ASGScalerTarget",
                    "Arn": lambda_arn
                }
            ]
        )

    print("🔐 Ensuring Lambda has permission to be invoked by EventBridge...")
    try:
        lambda_client.add_permission(
            FunctionName="ASGScalerFunction",
            StatementId="AllowExecutionFromEventBridge",
            Action="lambda:InvokeFunction",
            Principal="events.amazonaws.com",
            SourceArn=rule_arn
        )
    except botocore.exceptions.ClientError as e:
        if "ResourceConflictException" in str(e):
            print("⚠️ Lambda permission already exists.")
        else:
            raise

    print("✅ EventBridge rule and Lambda target verified.")


def cleanup_all_worker_buckets():
    print("🧹 Scanning for old worker-buckets to delete...")

    s3_resource = boto3.resource("s3", region_name=REGION)
    for bucket in s3_resource.buckets.all():
        if re.match(r"^worker-bucket-[a-f0-9]{8}$", bucket.name):
            print(f"🔸 Deleting bucket: {bucket.name}")
            try:
                bucket.objects.all().delete()
                bucket.delete()
                print(f"✅ Deleted: {bucket.name}")
            except Exception as e:
                print(f"⚠️ Failed to delete {bucket.name}: {e}")


if __name__ == "__main__":
    bucket_name = create_bucket_and_upload()
    subnet_id = get_default_subnet()
    success = deploy_stack(bucket_name, subnet_id)

    if not success:
        print("🚨 Deployment failed.")
        cleanup_all_worker_buckets()
        exit(1)

    queue_url = get_stack_output("SQSQueueURL")
    asg_name = get_stack_output("AutoScalingGroupName")
    print(f"ℹ️ SQS Queue URL: {queue_url}")
    print(f"ℹ️ Auto Scaling Group Name: {asg_name}")

    update_lambda_env("ASGScalerFunction", queue_url, asg_name)

    lambda_arn = lambda_client.get_function(FunctionName="ASGScalerFunction")["Configuration"]["FunctionArn"]
    ensure_eventbridge_rule(lambda_arn)