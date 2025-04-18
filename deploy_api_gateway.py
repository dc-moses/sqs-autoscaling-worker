import boto3
import json
import time
import os

REGION = 'us-east-1'
LAMBDA_NAME = 'sqs-worker-lambda'

lambda_client = boto3.client('lambda', region_name=REGION)
apigw_client = boto3.client('apigateway', region_name=REGION)
account_id = boto3.client('sts').get_caller_identity()['Account']

with open('api_gateway_template.json') as f:
    swagger = f.read()

swagger = swagger.replace('{region}', REGION)
swagger = swagger.replace('{accountId}', account_id)
swagger = swagger.replace('{lambdaName}', LAMBDA_NAME)

response = apigw_client.import_rest_api(
    failOnWarnings=True,
    body=swagger
)
api_id = response['id']
print(f"Imported API Gateway with ID: {api_id}")

apigw_client.create_deployment(
    restApiId=api_id,
    stageName='prod'
)
print(f"Deployed to stage: prod")

lambda_client.add_permission(
    FunctionName=LAMBDA_NAME,
    StatementId=f'apigateway-{api_id}',
    Action='lambda:InvokeFunction',
    Principal='apigateway.amazonaws.com',
    SourceArn=f"arn:aws:execute-api:{REGION}:{account_id}:{api_id}/*/POST/enqueue"
)

print(f"Invoke URL: https://{api_id}.execute-api.{REGION}.amazonaws.com/prod/enqueue")
