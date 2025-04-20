import boto3
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    sqs = boto3.client('sqs')
    asg = boto3.client('autoscaling')

    queue_url = os.environ['QUEUE_URL']
    asg_name = os.environ['ASG_NAME']

    try:
        attrs = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['ApproximateNumberOfMessages']
        )
        message_count = int(attrs['Attributes']['ApproximateNumberOfMessages'])
        logger.info(f"ApproximateNumberOfMessages: {message_count}")
    except Exception as e:
        logger.error(f"Error fetching SQS attributes: {e}")
        raise

    try:
        group = asg.describe_auto_scaling_groups(
            AutoScalingGroupNames=[asg_name]
        )['AutoScalingGroups'][0]
        current = group['DesiredCapacity']
        logger.info(f"Current ASG desired capacity: {current}")
    except Exception as e:
        logger.error(f"Error describing ASG: {e}")
        raise

    try:
        if message_count > 0 and current == 0:
            logger.info("Scaling up to 1.")
            asg.set_desired_capacity(
                AutoScalingGroupName=asg_name,
                DesiredCapacity=1,
                HonorCooldown=False
            )
        elif message_count == 0 and current > 0:
            logger.info("Scaling down to 0.")
            asg.set_desired_capacity(
                AutoScalingGroupName=asg_name,
                DesiredCapacity=0,
                HonorCooldown=False
            )
        else:
            logger.info("No scaling action needed.")
    except Exception as e:
        logger.error(f"Error updating ASG desired capacity: {e}")
        raise

    return {
        'statusCode': 200,
        'body': f'Messages: {message_count}, DesiredCapacity: {current}'
    }