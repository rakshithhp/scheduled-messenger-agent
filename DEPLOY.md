# Deploy to AWS

This guide walks you through hosting the Scheduled Messenger Agent on **AWS Elastic Beanstalk**.

## What you need (summary)

| Item | Purpose |
|------|---------|
| **AWS account** | To create resources |
| **EB CLI** | `pip install awsebcli` — deploy and manage the app |
| **Environment variables** | `SECRET_KEY`, `JWT_SECRET`, `OPENAI_API_KEY`, and either Twilio or SNS credentials |
| **Persistent DB path** (recommended) | `AUTH_DB_PATH` so SQLite survives deploys; otherwise auth/conversations reset on each deploy |
| **HTTPS** (optional) | ACM certificate + load balancer listener for production |

The app uses **one gunicorn worker** (scheduler and WebSockets are in-process). For **WebSockets** (real-time chat), the default ALB supports them; no extra config required.

---

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

**Auth (required for the web app):**
```bash
eb setenv SECRET_KEY=your-secret-key JWT_SECRET=your-jwt-secret
```
Use long, random values in production (e.g. `openssl rand -hex 32`).

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

## 5. Persistent database (recommended)

The app uses SQLite. On EB, the app directory (`/var/app/current`) is replaced on deploy, so **use a path outside it** or auth/conversations will reset.

This repo includes `.ebextensions/01_persistent_data.config`, which creates `/var/app/data` on deploy. Then set:

```bash
eb setenv AUTH_DB_PATH=/var/app/data/auth.db
```

If you didn’t use that config, create the directory (e.g. via SSH or a custom platform hook) and set `AUTH_DB_PATH` to a path there. For multiple instances, use **EFS** or move to **RDS**.

## 6. WebSockets

The UI uses WebSockets for real-time messages and drafts. AWS ALB supports WebSockets by default (HTTP/1.1 upgrade). No extra configuration needed for single-instance EB.

## 7. Use your own domain and HTTPS (optional)

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

## Deploy checklist

- [ ] `eb init` and `eb create` (or use an existing environment)
- [ ] Set `SECRET_KEY` and `JWT_SECRET` (e.g. `openssl rand -hex 32`)
- [ ] Set `OPENAI_API_KEY`
- [ ] Set either Twilio vars (`TWILIO_*`) or SNS (`MESSAGE_BACKEND=sns`, IAM or keys)
- [ ] Set `AUTH_DB_PATH=/var/app/data/auth.db` if using the included `.ebextensions` (persistent DB)
- [ ] (Optional) Add HTTPS listener and custom domain in the EB console

## Notes

- **Auth database (SQLite):** The app uses Python’s built-in **sqlite3** (no extra install). The file `auth.db` is **not** in git; the **code** in `auth/db.py` is. On deploy, the app creates `auth.db` on first run via `init_db()`. On Elastic Beanstalk the app directory can be overwritten on deploy, so the DB may reset unless you set `AUTH_DB_PATH` to a persistent path (e.g. a directory that survives deploys or an EFS mount). For multiple instances or long-term durability, consider **RDS** (PostgreSQL/MySQL) later.
- **contacts.json** and **sent_messages.json** are stored on the instance. They persist until the environment is recreated or the instance is replaced.
- For production, consider moving contacts and message history to **S3** or **DynamoDB**.
- The app runs with **1 gunicorn worker** because the scheduler and WebSockets use in-process state. **WebSockets** work with the default ALB; no extra config needed for a single instance.
