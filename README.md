# AWS Autoscaling SQS Worker System

This project deploys a minimal, scalable queue worker system on AWS using:

- **SQS** for job queueing  
- **EC2 Auto Scaling Group** that scales from 0 to 1  
- **CloudWatch** for queue-based scaling  
- **Lambda** and **API Gateway** (optional) for remote job triggering  

---

## ⚙️ How It Works

This system spins up an EC2 instance **only when a message is present** in the SQS queue, runs the job, and automatically scales back down to zero after the queue is empty.

- The Auto Scaling Group (ASG) has **min = 0, max = 1**
- A CloudWatch alarm monitors the SQS queue
- When a message arrives, it triggers the ASG to scale to 1
- The EC2 instance downloads a worker script from S3
- The script reads the job from the queue and sleeps for `wait_seconds`
- Once the queue is empty and the cooldown period expires, EC2 scales down to 0.

---

## 🧱 Components

### CloudFormation Stack

- SQS Queue  
- S3 Bucket for worker script  
- IAM Role and Instance Profile  
- EC2 Launch Template  
- Auto Scaling Group (0–1 instances)  
- CloudWatch Alarm  
- VPC + Subnet + Route Table + IGW  

### Python Scripts

- `worker.py` – EC2 worker script  
- `deploy.py` – Deploy stack & upload script  
- `send_job.py` – CLI to send jobs  
- `destroy.py` – Teardown script  
- `lambda_trigger.py` – Lambda for HTTP job trigger (optional)  
- `deploy_api_gateway.py` – API Gateway deployment (optional)  

---

## 🔧 Prerequisites

- Python 3.6+  
- AWS CLI configured (`aws configure`)  
- IAM role/user with permissions (see `iam_policy_template.yaml`)  

Deploy IAM setup:
```bash
aws cloudformation deploy \
  --template-file iam_policy_template.yaml \
  --stack-name SQSWorkerPolicyStack \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides CreateUser=false CreateRole=true RoleName=github-ci-role
```

---

## 🚀 GitHub Deployment

- GitHub Actions auto-deploys on push to `main`  
- Creates or updates the Lambda  
- Deploys the API Gateway  
- Creates a release on version tag (e.g. `v1.0.0`)  

---

## 🛠 Manual Usage

### 1. Deploy the app
```bash
python3 deploy.py
```

### 2. Send a test job
```bash
python3 send_job.py --queue-url <QUEUE_URL> --wait 30
```

```json
{
  "wait_seconds": 30
}
```

### 3. Deploy Lambda manually or via CI (optional)

### 4. Deploy API Gateway (optional)
```bash
python3 deploy_api_gateway.py
```

### 5. HTTP trigger (optional)
```bash
curl -X POST -H 'Content-Type: application/json' \
     -d '{"wait_seconds": 20}' \
     https://<api-id>.execute-api.us-east-1.amazonaws.com/prod/enqueue
```

---

## 🧼 Teardown
```bash
python3 destroy.py
```

---
