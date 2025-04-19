import boto3
import os

sqs = boto3.client('sqs')
asg = boto3.client('autoscaling')

def lambda_handler(event, context):
    queue_url = os.environ['QUEUE_URL']
    asg_name = os.environ['ASG_NAME']

    # Check number of visible messages
    attrs = sqs.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=['ApproximateNumberOfMessages']
    )
    message_count = int(attrs['Attributes']['ApproximateNumberOfMessages'])

    # Get current ASG desired capacity
    group = asg.describe_auto_scaling_groups(
        AutoScalingGroupNames=[asg_name]
    )['AutoScalingGroups'][0]
    current = group['DesiredCapacity']

    # Scale up/down based on message count
    if message_count > 0 and current == 0:
        print(f"Scaling up ASG {asg_name} to 1 (messages: {message_count})")
        asg.set_desired_capacity(AutoScalingGroupName=asg_name, DesiredCapacity=1, HonorCooldown=False)
    elif message_count == 0 and current > 0:
        print(f"Scaling down ASG {asg_name} to 0 (no messages)")
        asg.set_desired_capacity(AutoScalingGroupName=asg_name, DesiredCapacity=0, HonorCooldown=False)

    return {
        'statusCode': 200,
        'body': f'Messages: {message_count}, ASG Desired: {current}'
    }