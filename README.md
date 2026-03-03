# Scheduled Messenger Agent

An agent that sends messages to your contacts at scheduled times. Give it natural language instructions like:

> "Send a good night text to my wife after an hour"

It will parse the request, schedule the message, and notify you when it's sent.

## Features

- **Natural language input** — Uses an LLM to understand: who to message, what to say, and when
- **Contact aliases** — Map friendly names (wife, mom) to phone numbers
- **SMS delivery** — Twilio or Amazon SNS (configurable)
- **Confirmation** — Prints when the message was sent
- **Sent message history** — Persisted log of all messages sent (CLI + web UI)

## Setup

### 1. Install dependencies

```bash
cd scheduled-messenger-agent
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and add:

- **OpenAI API key** — For parsing your natural language requests
- **Message backend** — Set `MESSAGE_BACKEND=twilio` or `sns`
  - **Twilio**: Account SID, Auth Token, phone number (create at twilio.com)
  - **Amazon SNS**: AWS credentials + region (ideal when hosting on AWS; use IAM role there)

### 3. Add contacts

```bash
python main.py add-contact wife +15551234567
python main.py add-contact mom +15559876543
```

## Usage

### Web UI (recommended)

```bash
python app.py
```

Then open http://localhost:5000 in your browser. Type your request (e.g., "Send good night text to my wife in an hour") and click **Send**. You'll get instant feedback and real-time notifications when messages are delivered.

### Schedule a message (CLI)

```bash
python main.py "Send a good night text to my wife after an hour"
```

Keep the process running until the message is sent. When it goes out, you'll see:

```
✓ Message sent to wife (+15551234567):
  "Good night! Sleep well ❤️"
  Sent at 2025-02-21 23:15:00
```

### Other examples

```bash
python main.py "Remind mom to take her vitamins in 30 minutes"
python main.py "Text john happy birthday in 2 hours"
```

### List contacts

```bash
python main.py contacts
```

### View sent message history

```bash
python main.py sent-messages
```

Also visible in the web UI below the input.

### Dry run (parse only, don't send)

```bash
python main.py --dry-run "Send good night to wife in an hour"
```

## How it works

1. **Parser** — Your natural language request is sent to an LLM, which extracts:
   - The message text (expands shorthand like "good night text" into a full message)
   - The contact alias (e.g., "wife")
   - The delay (e.g., "in an hour" → 3600 seconds)

2. **Scheduler** — Uses APScheduler to run the send at the right time

3. **Sender** — Sends SMS via Twilio when the time comes

4. **Notification** — Prints a confirmation to the terminal

## Project structure

```
scheduled-messenger-agent/
├── Procfile           # For AWS Elastic Beanstalk
├── .platform/         # Nginx config for SSE on AWS
├── agent/
│   ├── parser.py      # Natural language → structured task
│   ├── contacts.py    # Alias → phone number storage
│   ├── sent_messages.py # Persisted log of sent messages
│   ├── scheduler.py   # APScheduler wrapper
│   └── sender.py      # Twilio / Amazon SNS
├── app.py             # Web UI (Flask)
├── templates/
│   └── index.html     # UI with input + send
├── main.py            # CLI entry point
├── contacts.json      # Created when you add contacts
├── sent_messages.json # Created when messages are sent
├── requirements.txt
└── .env               # Your secrets (from .env.example)
```

## Testing

The suite covers auth (DB, models, JWT, routes), messaging (conversations, messages, API routes), and the agent parser (intent parsing, expansion, repeat-stop logic). OpenAI is mocked in parser tests so no API key is needed.

```bash
pytest tests/ -v
```

To run tests automatically before every commit:

```bash
pip install pre-commit
pre-commit install
```

After that, `git commit` will run `pytest tests/ -q` first; the commit is blocked if tests fail (use `git commit --no-verify` to skip).

## Deploy to AWS

To host the app on AWS and access it via the web, see **[DEPLOY.md](DEPLOY.md)** for step-by-step instructions using Elastic Beanstalk.

## Future ideas

- **Persistent scheduler** — Store jobs in a DB so they survive restarts
- **WhatsApp / iMessage** — Additional messaging backends
- **Recurring messages** — e.g., "Text mom every Sunday at 10am"
- **Voice / chat interface** — Integrate with a voice assistant or chat app
