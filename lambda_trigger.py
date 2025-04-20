import boto3
import os
import time
import botocore.exceptions

sqs = boto3.client("sqs")
asg = boto3.client("autoscaling")

def lambda_handler(event, context):
    queue_url = os.environ.get("QUEUE_URL")
    asg_name = os.environ.get("ASG_NAME")

    if not queue_url or not asg_name:
        print("[ERROR] Missing QUEUE_URL or ASG_NAME in environment variables.")
        return {
            "statusCode": 500,
            "body": "Missing QUEUE_URL or ASG_NAME"
        }

    try:
        attrs = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=[
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible"
            ]
        )
        visible = int(attrs["Attributes"].get("ApproximateNumberOfMessages", 0))
        not_visible = int(attrs["Attributes"].get("ApproximateNumberOfMessagesNotVisible", 0))
        total = visible + not_visible
        print(f"[SQS] Visible: {visible}, In-flight (not visible): {not_visible}, Total: {total}")
    except Exception as e:
        print(f"[ERROR] Failed to fetch SQS attributes: {e}")
        return {
            "statusCode": 500,
            "body": "SQS get_queue_attributes failed"
        }

    try:
        group = asg.describe_auto_scaling_groups(
            AutoScalingGroupNames=[asg_name]
        )["AutoScalingGroups"][0]
        current_capacity = group["DesiredCapacity"]
        print(f"[ASG] Current desired capacity: {current_capacity}")
    except Exception as e:
        print(f"[ERROR] Failed to describe ASG: {e}")
        return {
            "statusCode": 500,
            "body": "ASG describe failed"
        }

    # Scale UP if messages and ASG is at 0
    if total > 0 and current_capacity == 0:
        print(f"[ASG] Scaling UP {asg_name} to 1")
        try:
            asg.set_desired_capacity(
                AutoScalingGroupName=asg_name,
                DesiredCapacity=1,
                HonorCooldown=False
            )
        except Exception as e:
            print(f"[ERROR] Failed to scale up: {e}")
            return {
                "statusCode": 500,
                "body": "Scale up failed"
            }

    # Scale DOWN if no messages and ASG is greater than 0
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
                print(f"[ASG] Attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    time.sleep(5)
                else:
                    print("[ASG] All scale-down attempts failed.")
                    return {
                        "statusCode": 500,
                        "body": "Scale down failed after retries"
                    }

    return {
        "statusCode": 200,
        "body": f"QueueTotal={total}, DesiredCapacity={current_capacity}"
    }