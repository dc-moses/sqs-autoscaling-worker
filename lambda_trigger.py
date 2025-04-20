import boto3
import os
import time
import botocore.exceptions

def lambda_handler(event, context):
    sqs = boto3.client("sqs")
    asg = boto3.client("autoscaling")

    queue_url = os.environ["QUEUE_URL"]
    asg_name = os.environ["ASG_NAME"]

    attrs = sqs.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"]
    )

    visible = int(attrs["Attributes"]["ApproximateNumberOfMessages"])
    not_visible = int(attrs["Attributes"]["ApproximateNumberOfMessagesNotVisible"])
    total = visible + not_visible

    print(f"[SQS] Visible: {visible}, NotVisible: {not_visible}, Total: {total}")

    group = asg.describe_auto_scaling_groups(
        AutoScalingGroupNames=[asg_name]
    )["AutoScalingGroups"][0]

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
            print("[ASG] Scale-up successful")
        except Exception as e:
            print(f"[ASG] Scale-up failed: {e}")

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
