AWSTemplateFormatVersion: '2010-09-09'
Description: IAM policy and optional user/role setup for SQS worker deployment

Parameters:
  CreateUser:
    Type: String
    Default: false
    AllowedValues: [true, false]
  UserName:
    Type: String
    Default: deploy-user
  CreateRole:
    Type: String
    Default: false
    AllowedValues: [true, false]
  RoleName:
    Type: String
    Default: github-ci-role

Resources:

  SQSWorkerPolicy:
    Type: AWS::IAM::ManagedPolicy
    Properties:
      Description: Full permissions for deploying SQS worker stack
      PolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Action:
              - cloudformation:*
              - ec2:*
              - s3:*
              - iam:*
              - autoscaling:*
              - cloudwatch:*
              - sqs:*
              - lambda:*
              - apigateway:*
            Resource: '*'

  DeployUser:
    Type: AWS::IAM::User
    Condition: CreateUserCondition
    Properties:
      UserName: !Ref UserName
      ManagedPolicyArns:
        - !Ref SQSWorkerPolicy

  DeployRole:
    Type: AWS::IAM::Role
    Condition: CreateRoleCondition
    Properties:
      RoleName: !Ref RoleName
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Federated: arn:aws:iam::319319364622:oidc-provider/token.actions.githubusercontent.com
            Action: sts:AssumeRoleWithWebIdentity
            Condition:
              StringEquals:
                token.actions.githubusercontent.com:aud: sts.amazonaws.com
                token.actions.githubusercontent.com:sub: repo:YOUR_USERNAME/YOUR_REPO:ref:refs/heads/main
      ManagedPolicyArns:
        - !Ref SQSWorkerPolicy

Conditions:
  CreateUserCondition: !Equals [!Ref CreateUser, true]
  CreateRoleCondition: !Equals [!Ref CreateRole, true]

Outputs:
  LambdaFunctionName:
    Description: Name of the Lambda function used by this deployment
    Value: sqs-worker-lambda
    Export:
      Name: !Sub "${AWS::StackName}-LambdaName"