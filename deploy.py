import boto3
import time
import uuid

cf = boto3.client('cloudformation')
s3 = boto3.client('s3')

STACK_NAME = 'SQSWorkerStack'
TEMPLATE_FILE = 'template.yaml'
SCRIPT_FILE = 'worker.py'
REGION = 'us-east-1'

bucket_name = f"worker-bucket-{uuid.uuid4().hex[:8]}"
script_key = 'worker.py'

def create_bucket_and_upload():
    print(f"Creating bucket: {bucket_name}")
    if REGION == 'us-east-1':
        s3.create_bucket(Bucket=bucket_name)
    else:
        s3.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={'LocationConstraint': REGION}
        )

    s3.upload_file(SCRIPT_FILE, bucket_name, script_key)
    print(f"Uploaded {SCRIPT_FILE} to s3://{bucket_name}/{script_key}")

def deploy_stack():
    with open(TEMPLATE_FILE) as f:
        template_body = f.read()

    print("Deploying CloudFormation stack...")
    cf.create_stack(
        StackName=STACK_NAME,
        TemplateBody=template_body,
        Capabilities=['CAPABILITY_NAMED_IAM'],
        Parameters=[
            {'ParameterKey': 'WorkerScriptBucket', 'ParameterValue': bucket_name},
            {'ParameterKey': 'WorkerScriptKey', 'ParameterValue': script_key},
        ]
    )

    waiter = cf.get_waiter('stack_create_complete')
    waiter.wait(StackName=STACK_NAME)
    print("Stack deployed successfully.")

if __name__ == '__main__':
    create_bucket_and_upload()
    deploy_stack()
