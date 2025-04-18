import boto3
import time

STACK_NAME = 'SQSWorkerStack'

cf = boto3.client('cloudformation')
s3 = boto3.client('s3')

print("Getting stack resources...")
resources = cf.describe_stack_resources(StackName=STACK_NAME)['StackResources']
bucket_name = next(r['PhysicalResourceId'] for r in resources if r['ResourceType'] == 'AWS::S3::Bucket')

print(f"Deleting all objects in bucket {bucket_name}...")
objs = s3.list_objects_v2(Bucket=bucket_name)
if 'Contents' in objs:
    for obj in objs['Contents']:
        print(f"Deleting {obj['Key']}")
        s3.delete_object(Bucket=bucket_name, Key=obj['Key'])

print(f"Deleting bucket {bucket_name}...")
s3.delete_bucket(Bucket=bucket_name)

print(f"Deleting CloudFormation stack {STACK_NAME}...")
cf.delete_stack(StackName=STACK_NAME)

print("Waiting for stack deletion to complete...")
cf.get_waiter('stack_delete_complete').wait(StackName=STACK_NAME)
print("Stack and bucket deleted.")
