import boto3
import os
import time
import json
import botocore.exceptions

REGION = "us-east-1"
ssm = boto3.client("ssm", region_name=REGION)
ec2 = boto3.client("ec2", region_name=REGION)
sqs = boto3.client("sqs", region_name=REGION)
asg = boto3.client("autoscaling", region_name=REGION)

def lambda_handler(event, context):
    queue_url = os.environ.get("QUEUE_URL")
    asg_name = os.environ.get("ASG_NAME")

    if not queue_url or not asg_name:
        print("[ERROR] Missing required environment variables.")
        return {"statusCode": 500, "body": "Missing QUEUE_URL or ASG_NAME"}

    print(f"[ENV] QUEUE_URL={queue_url}")
    print(f"[ENV] ASG_NAME={asg_name}")

    # Check SQS queue depth
    try:
        attrs = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=["ApproximateNumberOfMessages"]
        )
        visible = int(attrs["Attributes"].get("ApproximateNumberOfMessages", 0))
        print(f"[SQS] Queue has {visible} message(s)")
    except Exception as e:
        print(f"[ERROR] Failed to get SQS attributes: {e}")
        return {"statusCode": 500, "body": "Failed to get SQS attributes"}

    # Scale up ASG if needed
    try:
        group = asg.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])["AutoScalingGroups"][0]
        current_capacity = group["DesiredCapacity"]
    except Exception as e:
        print(f"[ERROR] Failed to fetch ASG info: {e}")
        return {"statusCode": 500, "body": "Failed to fetch ASG"}

    if visible > 0 and current_capacity == 0:
        print(f"[ASG] Scaling up {asg_name} to 1")
        asg.set_desired_capacity(AutoScalingGroupName=asg_name, DesiredCapacity=1, HonorCooldown=False)
        return {"statusCode": 202, "body": "Scaling up ASG to handle messages"}

    if visible == 0 and current_capacity > 0:
        print(f"[ASG] Scaling down {asg_name} to 0")
        asg.set_desired_capacity(AutoScalingGroupName=asg_name, DesiredCapacity=0, HonorCooldown=False)
        return {"statusCode": 200, "body": "Scaling down ASG (no messages)"}

    if visible == 0:
        print("[SQS] No messages to process.")
        return {"statusCode": 200, "body": "Queue empty"}

    # Poll 1 message from SQS
    print("[SQS] Attempting to fetch a message from queue...")
    response = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=0
    )

    messages = response.get("Messages", [])
    if not messages:
        print("[SQS] No messages received.")
        return {"statusCode": 204, "body": "No messages"}

    message = messages[0]
    receipt_handle = message["ReceiptHandle"]
    message_body = message["Body"]
    print(f"[SQS] Received message: {message_body}")

    # Find running EC2 instance
    instances = ec2.describe_instances(
        Filters=[
            {"Name": "tag:aws:autoscaling:groupName", "Values": [asg_name]},
            {"Name": "instance-state-name", "Values": ["running"]}
        ]
    )["Reservations"]

    if not instances or not instances[0]["Instances"]:
        print("[EC2] No running EC2 instance found.")
        return {"statusCode": 500, "body": "No EC2 instance found"}

    instance_id = instances[0]["Instances"][0]["InstanceId"]
    print(f"[EC2] Found running instance: {instance_id}")

    # Send command via SSM
    try:
        command = f"echo '{message_body}' > /tmp/job.json && python3 /home/ec2-user/worker.py /tmp/job.json"
        print(f"[SSM] Sending command to EC2: {command}")

        ssm_response = ssm.send_command(
            InstanceIds=[instance_id],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": [command]},
        )

        command_id = ssm_response["Command"]["CommandId"]
    except Exception as e:
        print(f"[SSM] Failed to send command: {e}")
        return {"statusCode": 500, "body": "Failed to send SSM command"}

    print(f"[SSM] Waiting for command {command_id} to complete...")
    for attempt in range(12):
        time.sleep(5)
        output = ssm.get_command_invocation(
            CommandId=command_id,
            InstanceId=instance_id
        )
        if output["Status"] in ["Success", "Failed", "Cancelled", "TimedOut"]:
            print(f"[SSM] Command finished with status: {output['Status']}")
            break
    else:
        print("[SSM] Timed out waiting for command to complete.")
        return {"statusCode": 504, "body": "Timeout waiting for SSM"}

    if output["Status"] == "Success":
        print(f"[SSM] Output:\n{output['StandardOutputContent']}")
        print("[SQS] ✅ Job succeeded. Deleting message from SQS...")
        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        return {"statusCode": 200, "body": "Job processed and message deleted"}
    else:
        print(f"[SSM] ❌ Command failed. Message NOT deleted.\nSTDERR:\n{output['StandardErrorContent']}")
        return {"statusCode": 500, "body": "Job failed on EC2, message retained in queue"}