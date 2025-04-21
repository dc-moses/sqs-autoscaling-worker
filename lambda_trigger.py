import boto3
import os
import time
import botocore.exceptions

sqs = boto3.client("sqs")
asg = boto3.client("autoscaling")
ec2 = boto3.client("ec2")

VISIBILITY_TIMEOUT_SUGGESTED = 90  # in seconds, should match CF template

def wait_for_instance_initialization(asg_name):
    print(f"[Init] Waiting for EC2 instance in ASG '{asg_name}' to be initialized...")
    for i in range(30):  # Wait up to 5 minutes (30 * 10s)
        response = asg.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        instances = response["AutoScalingGroups"][0].get("Instances", [])
        if instances:
            instance_id = instances[0]["InstanceId"]
            state = instances[0]["LifecycleState"]
            print(f"[Init] Found instance {instance_id} in state: {state}")
            if state == "InService":
                status = ec2.describe_instance_status(InstanceIds=[instance_id])
                checks = status.get("InstanceStatuses", [])
                if checks:
                    system_status = checks[0]["SystemStatus"]["Status"]
                    instance_status = checks[0]["InstanceStatus"]["Status"]
                    print(f"[Init] EC2 health - System: {system_status}, Instance: {instance_status}")
                    if system_status == "ok" and instance_status == "ok":
                        print(f"[Init] EC2 instance {instance_id} is fully initialized.")
                        return True
        else:
            print("[Init] No instance found yet.")

        time.sleep(10)

    print("⚠️ EC2 instance failed to initialize within expected time.")
    return False

def lambda_handler(event, context):
    queue_url = os.environ.get("QUEUE_URL")
    asg_name = os.environ.get("ASG_NAME")

    if not queue_url or not asg_name:
        print("[ERROR] Missing QUEUE_URL or ASG_NAME.")
        return {"statusCode": 500, "body": "Missing QUEUE_URL or ASG_NAME"}

    print(f"[Env] QUEUE_URL: {queue_url}")
    print(f"[Env] ASG_NAME: {asg_name}")

    try:
        attrs = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=[
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible",
                "VisibilityTimeout"
            ]
        )
        visible = int(attrs["Attributes"].get("ApproximateNumberOfMessages", 0))
        not_visible = int(attrs["Attributes"].get("ApproximateNumberOfMessagesNotVisible", 0))
        visibility_timeout = int(attrs["Attributes"].get("VisibilityTimeout", 0))
        total = visible + not_visible

        print(f"[SQS] Messages: {visible} visible / {not_visible} not visible / {total} total")
        print(f"[SQS] Queue Visibility Timeout: {visibility_timeout}s")

        if visibility_timeout < VISIBILITY_TIMEOUT_SUGGESTED:
            print(f"[WARN] Visibility timeout is less than {VISIBILITY_TIMEOUT_SUGGESTED}s. This may cause jobs to be re-queued before completion.")

    except Exception as e:
        print(f"[ERROR] Failed to get SQS attributes: {e}")
        return {"statusCode": 500, "body": str(e)}

    try:
        group = asg.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])["AutoScalingGroups"][0]
        current_capacity = group["DesiredCapacity"]
    except Exception as e:
        print(f"[ERROR] Failed to describe ASG: {e}")
        return {"statusCode": 500, "body": str(e)}

    print(f"[ASG] Desired capacity is currently {current_capacity}")

    if total > 0 and current_capacity == 0:
        print("[ASG] Scaling up ASG to 1 instance.")
        asg.set_desired_capacity(AutoScalingGroupName=asg_name, DesiredCapacity=1, HonorCooldown=False)

        if not wait_for_instance_initialization(asg_name):
            return {"statusCode": 500, "body": "EC2 instance failed to initialize."}

    elif total == 0 and current_capacity > 0:
        print("[ASG] Scaling down ASG to 0.")
        for attempt in range(3):
            try:
                asg.set_desired_capacity(AutoScalingGroupName=asg_name, DesiredCapacity=0, HonorCooldown=False)
                print(f"[ASG] Scale-down successful on attempt {attempt + 1}")
                break
            except botocore.exceptions.ClientError as e:
                print(f"[ASG] Attempt {attempt + 1} failed: {e}")
                time.sleep(5)

    return {
        "statusCode": 200,
        "body": f"Queue={total}, ASGCapacity={current_capacity}"
    }