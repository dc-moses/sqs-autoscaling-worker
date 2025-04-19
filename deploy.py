name: Deploy SQS Worker

on:
  push:
    branches: [ main ]
  workflow_dispatch:

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    env:
      LAMBDA_NAME: sqs-worker-lambda

    steps:
      - name: Checkout repository
        uses: actions/checkout@v3

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/github-ci-role
          aws-region: us-east-1

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: pip install boto3

      - name: Deploy CloudFormation stack
        run: python3 deploy.py

      - name: Deploy or Create Lambda function
        run: |
          zip lambda.zip lambda_trigger.py
          if aws lambda get-function --function-name $LAMBDA_NAME > /dev/null 2>&1; then
            aws lambda update-function-code \
              --function-name $LAMBDA_NAME \
              --zip-file fileb://lambda.zip
          else
            aws lambda create-function \
              --function-name $LAMBDA_NAME \
              --runtime python3.10 \
              --role arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/github-ci-role \
              --handler lambda_trigger.lambda_handler \
              --zip-file fileb://lambda.zip \
              --environment Variables={QUEUE_URL=dummy-to-be-updated}

      - name: Update Lambda environment with real queue URL
        run: |
          QUEUE_URL=$(aws cloudformation describe-stacks \
            --stack-name SQSWorkerStack \
            --query "Stacks[0].Outputs[?OutputKey=='SQSQueueURL'].OutputValue" \
            --output text)
          aws lambda update-function-configuration \
            --function-name $LAMBDA_NAME \
            --environment Variables="{\"QUEUE_URL\":\"$QUEUE_URL\"}"

      - name: Deploy API Gateway
        run: |
          sed -i "s/YourLambdaFunctionName/$LAMBDA_NAME/g" deploy_api_gateway.py
          python3 deploy_api_gateway.py

      - name: Send test job to SQS
        run: |
          QUEUE_URL=$(aws cloudformation describe-stacks \
            --stack-name SQSWorkerStack \
            --query "Stacks[0].Outputs[?OutputKey=='SQSQueueURL'].OutputValue" \
            --output text)
          echo "Sending test job to queue: $QUEUE_URL"
          aws sqs send-message --queue-url "$QUEUE_URL" --message-body '{"wait_seconds":10}'

      - name: Wait for ASG to scale to 1 and back to 0
        run: |
          set -e
          ASG_NAME=$(aws cloudformation describe-stack-resources \
            --stack-name SQSWorkerStack \
            --query "StackResources[?ResourceType=='AWS::AutoScaling::AutoScalingGroup'].PhysicalResourceId" \
            --output text)

          echo "Polling ASG: $ASG_NAME for scale-up..."
          for i in {1..30}; do
            DESIRED=$(aws autoscaling describe-auto-scaling-groups \
              --auto-scaling-group-names "$ASG_NAME" \
              --query "AutoScalingGroups[0].DesiredCapacity" \
              --output text)

            INSTANCE_ID=$(aws autoscaling describe-auto-scaling-groups \
              --auto-scaling-group-names "$ASG_NAME" \
              --query "AutoScalingGroups[0].Instances[0].InstanceId" \
              --output text)

            if [ "$DESIRED" -ge 1 ] && [ "$INSTANCE_ID" != "None" ]; then
              echo "✅ ASG scaled up with instance $INSTANCE_ID."
              break
            fi
            sleep 10
          done

          echo "Checking CloudWatch logs for '[Worker] Done.'"
          LOG_GROUP="/var/log/cloud-init-output.log"
          INSTANCE_LOG=$(aws ec2 describe-instances --instance-ids $INSTANCE_ID \
            --query "Reservations[0].Instances[0].InstanceId" --output text)

          for i in {1..15}; do
            OUTPUT=$(aws ec2 get-console-output --instance-id $INSTANCE_ID --output text || true)
            echo "$OUTPUT" | grep '\[Worker\] Done\.' && echo "✅ Job completed successfully." && break
            echo "Waiting for log confirmation..."
            sleep 10
          done

          echo "Waiting for ASG to scale back to 0..."
          for i in {1..30}; do
            INSTANCE_COUNT=$(aws autoscaling describe-auto-scaling-groups \
              --auto-scaling-group-names "$ASG_NAME" \
              --query "length(AutoScalingGroups[0].Instances)" \
              --output text)

            echo "Post-job check $i: Instances=$INSTANCE_COUNT"

            if [ "$INSTANCE_COUNT" -eq 0 ]; then
              echo "✅ EC2 instance has terminated and ASG scaled back to 0."
              TERMINATION_REASON=$(aws ec2 describe-instances --instance-ids $INSTANCE_ID \
                --query "Reservations[0].Instances[0].StateTransitionReason" --output text)
              echo "Termination reason: $TERMINATION_REASON"
              break
            fi
            sleep 10
          done

          echo "❌ EC2 instance did not terminate in expected time."
          exit 1

      - name: Delete worker bucket after stack creation
        if: always()
        run: |
          BUCKET_NAME=$(aws s3api list-buckets --query "Buckets[?starts_with(Name, 'worker-bucket-')].Name" --output text | head -n1)
          echo "Cleaning up bucket: $BUCKET_NAME"
          if [ -n "$BUCKET_NAME" ]; then
            aws s3 rm s3://$BUCKET_NAME --recursive || true
            aws s3api delete-bucket --bucket $BUCKET_NAME || true
            echo "✅ Bucket $BUCKET_NAME deleted."
          else
            echo "No matching worker bucket found to clean up."
          fi
