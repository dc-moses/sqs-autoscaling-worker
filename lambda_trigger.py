import boto3
import os
import time
import botocore.exceptions

def lambda_handler(event, context):
    sqs = boto3.client("sqs")
    asg = boto3.client("autoscaling")

    queue_url = os.environ.get("QUEUE_URL")
    asg_name = os.environ.get("ASG_NAME")

    if not queue_url or not asg_name:
        print("[ERROR] Missing required environment variables.")
        return {
            "statusCode": 500,
            "body": "Missing QUEUE_URL or ASG_NAME in environment variables"
        }

    print(f"[ENV] QUEUE_URL={queue_url}")
    print(f"[ENV] ASG_NAME={asg_name}")

    try:
        attrs = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=[
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible"
            ]
        )
    except botocore.exceptions.ClientError as e:
        print(f"[ERROR] Failed to fetch SQS attributes: {e}")
        return {
            "statusCode": 500,
            "body": f"Error fetching queue attributes: {e}"
        }

    visible = int(attrs["Attributes"].get("ApproximateNumberOfMessages", 0))
    not_visible = int(attrs["Attributes"].get("ApproximateNumberOfMessagesNotVisible", 0))
    total = visible + not_visible

    print(f"[SQS] Visible: {visible}, NotVisible: {not_visible}, Total: {total}")

    try:
        group = asg.describe_auto_scaling_groups(
            AutoScalingGroupNames=[asg_name]
        )["AutoScalingGroups"][0]
    except (IndexError, botocore.exceptions.ClientError) as e:
        print(f"[ERROR] Failed to fetch ASG info: {e}")
        return {
            "statusCode": 500,
            "body": f"Error fetching ASG details: {e}"
        }

    current_capacity = group["DesiredCapacity"]
    print(f"[ASG] Current desired capacity: {current_capacity}")

    if total > 0 and current_capacity == 0:
        print(f"[ASG] Scaling UP {asg_name} to 1")
        try:
            asg.set_desired_capacity(
                AutoScalingGroupName=asg_name,
                DesiredCapacity=1,
                HonorCooldown=False
            )
        except botocore.exceptions.ClientError as e:
            print(f"[ASG] Failed to scale up: {e}")
            return {
                "statusCode": 500,
                "body": f"Error scaling up: {e}"
            }

    elif total == 0 and current_capacity > 0:
        print(f"[ASG] Attempting to scale DOWN {asg_name} to 0")
        for attempt in range(3):
            try:
                asg.set_desired_capacity(
                    AutoScalingGroupName=asg_name,
                    DesiredCapacity=0,
                    HonorCooldown=False
                )
                print(f"[ASG] Scale-down request successful on attempt {attempt + 1}")
                break
            except botocore.exceptions.ClientError as e:
                print(f"[ASG] Attempt {attempt + 1} failed to scale down: {e}")
                if attempt < 2:
                    time.sleep(5)
                else:
                    print("[ASG] All scale-down attempts failed.")

    return {
        "statusCode": 200,
        "body": f"Queue={total}, DesiredCapacity={current_capacity}"
    }