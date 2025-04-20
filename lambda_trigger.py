import boto3
import os
import time
import botocore.exceptions

def lambda_handler(event, context):
    sqs = boto3.client("sqs")
    asg = boto3.client("autoscaling")

    queue_url = os.environ["QUEUE_URL"]
    asg_name = os.environ["ASG_NAME"]

    # Retrieve both visible and in-flight messages
    try:
        attrs = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=[
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible"
            ]
        )
    except botocore.exceptions.ClientError as e:
        print(f"[SQS] Failed to retrieve queue attributes: {e}")
        return {
            "statusCode": 500,
            "body": "Failed to retrieve SQS attributes"
        }

    visible = int(attrs["Attributes"].get("ApproximateNumberOfMessages", 0))
    not_visible = int(attrs["Attributes"].get("ApproximateNumberOfMessagesNotVisible", 0))
    total = visible + not_visible

    print(f"[SQS] Visible: {visible}, NotVisible: {not_visible}, Total: {total}")

    # Get ASG desired capacity
    try:
        group = asg.describe_auto_scaling_groups(
            AutoScalingGroupNames=[asg_name]
        )["AutoScalingGroups"][0]
    except botocore.exceptions.ClientError as e:
        print(f"[ASG] Failed to describe auto scaling group: {e}")
        return {
            "statusCode": 500,
            "body": "Failed to describe ASG"
        }

    current_capacity = group["DesiredCapacity"]
    print(f"[ASG] Current desired capacity: {current_capacity}")

    # Scale UP
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
                "body": "Failed to scale up ASG"
            }

    # Scale DOWN
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