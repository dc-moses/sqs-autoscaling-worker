# 🚀 AWS Auto-Scaling SQS Worker System

This project deploys a **serverless job dispatcher and EC2-based worker system** using:

- **Amazon SQS** – job queue  
- **EC2 Auto Scaling Group** – scales from 0 to 1 worker  
- **AWS Lambda** – polls SQS and triggers EC2 jobs via SSM  
- **GitHub Actions** – deploys the entire stack via IaC  

---

## 🧠 How It Works

This architecture ensures that an EC2 instance is **launched only when there's work to do** and shut down automatically when the job is done.

1. Jobs are sent to SQS  
2. A scheduled **Lambda** polls the queue  
3. If a message is found, the **Auto Scaling Group (ASG)** is scaled to 1  
4. Once the EC2 instance is ready, Lambda dispatches the job to it via **SSM**  
5. On successful completion, Lambda deletes the message and scales the ASG back to 0  

➡️ **No idle compute. Pay only when work runs.**

---

## 📦 What's Deployed

### ✅ Via CloudFormation

- **SQS Queue**  
- **Auto Scaling Group** (min: 0, max: 1)  
- **EC2 Launch Template** with SSM + UserData  
- **Lambda** to poll SQS and trigger jobs  
- **CloudWatch Scheduled Event** for polling  
- **IAM Roles + Policies**  
- **VPC**, Subnet, Route Table, IGW  

### 🐍 Python Scripts

- `deploy.py` – Uploads `worker.py`, deploys full stack, sets Lambda env vars  
- `worker.py` – Script executed on EC2 to process jobs  
- `send_job.py` – CLI to enqueue a test job  
- `destroy.py` – Cleanly tears down all resources  

---

## 🧰 Requirements

- Python 3.6+  
- AWS CLI configured (`aws configure`)  
- IAM role/user with necessary permissions  
- GitHub repo secrets for CI/CD (e.g. `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)  

---

## 🔄 GitHub Actions Deployment

The deployment is fully automated via CI/CD:

### 🛠 What it does on push to `main`

- Uploads the latest `worker.py` to a versioned S3 bucket  
- Deploys or updates the CloudFormation stack  
- Configures the Lambda and environment  
- Confirms EC2 scaled up, job processed, and scaled down  
- Tags a GitHub release on version tags (e.g. `v1.0.0`)  

🧪 The workflow includes **EC2 readiness checks** and **SSM log inspection** to ensure the job succeeded before cleaning up.

---

## 💻 Manual Usage (Optional)

### Deploy the stack
```bash
python3 deploy.py
```

### Enqueue a test job
```bash
python3 send_job.py --queue-url <QUEUE_URL> --wait 20
```

Payload:
```json
{ "wait_seconds": 20 }
```

### Tear down all resources
```bash
python3 destroy.py
```

---

## 📎 Example Job Flow

1. You push to `main`  
2. GitHub deploys infrastructure and worker logic  
3. You send a job to SQS  
4. Lambda detects the job and triggers EC2  
5. EC2 runs the job and exits  
6. ASG scales down to 0  

---

## ✅ Benefits

- **Zero idle cost** – EC2 only runs when needed  
- **Auditable and repeatable** – via CloudFormation + GitHub Actions  
- **Extensible** – add GPU instances, multiple queues, or API gateway later  

---

## 🧽 Cleanup

```bash
python3 destroy.py
```

This deletes all infrastructure, including the S3 bucket, SQS queue, and ASG.

---