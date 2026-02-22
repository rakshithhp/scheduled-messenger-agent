# Deploy to AWS

This guide walks you through hosting the Scheduled Messenger Agent on **AWS Elastic Beanstalk** so you can access it via the web.

## Prerequisites

- AWS account
- [AWS CLI](https://aws.amazon.com/cli/) installed and configured (`aws configure`)
- [EB CLI](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/eb-cli3-install.html) installed (`pip install awsebcli`)

## 1. Install EB CLI

```bash
pip install awsebcli
```

## 2. Initialize and create environment

From the project root:

```bash
cd /Users/nishajit/scheduled-messenger-agent
eb init
```

When prompted:
- **Region:** Choose your region (e.g. `us-east-1` or `us-east-2`)
- **Application name:** `scheduled-messenger-agent` (or leave default)
- **Platform:** Python
- **Platform version:** Python 3.11 or 3.12 (recommended)
- **Set up SSH:** Optional (yes if you want to SSH into the instance)

```bash
eb create scheduled-messenger-env
```

This creates the environment and deploys your app. It may take 5–10 minutes.

## 3. Set environment variables

Configure secrets in the Elastic Beanstalk environment.

**For Twilio (recommended):**
```bash
eb setenv OPENAI_API_KEY=sk-your-key \
  MESSAGE_BACKEND=twilio \
  TWILIO_ACCOUNT_SID=AC... \
  TWILIO_AUTH_TOKEN=... \
  TWILIO_PHONE_NUMBER=+1... \
  OPENAI_MODEL=gpt-4o-mini
```

**For Amazon SNS (when hosting on AWS):**
```bash
eb setenv OPENAI_API_KEY=sk-your-key \
  MESSAGE_BACKEND=sns \
  AWS_REGION=us-east-2 \
  OPENAI_MODEL=gpt-4o-mini
```
Then add `sns:Publish` to the EB instance profile in IAM, or set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` via `eb setenv`.

## 4. Open the app

```bash
eb open
```

This opens your app in the browser. The URL will look like:
`http://scheduled-messenger-env.xxxxx.us-east-2.elasticbeanstalk.com`

## 5. Use your own domain (optional)

In the [Elastic Beanstalk console](https://console.aws.amazon.com/elasticbeanstalk):
1. Select your environment
2. Configuration → Load balancer → Add listener (HTTPS on 443)
3. Use **AWS Certificate Manager** for an SSL cert
4. Point your domain to the load balancer via **Route 53** or your DNS provider

## Future deployments

After making code changes:

```bash
git add .
git commit -m "Your changes"
eb deploy
```

## Notes

- **contacts.json** and **sent_messages.json** are stored on the instance. They persist until the environment is recreated or the instance is replaced.
- For production, consider moving contacts and message history to **S3** or **DynamoDB**.
- The app runs with **1 gunicorn worker** because the scheduler and SSE use in-memory state.
