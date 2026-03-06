# Scheduled Messenger – iOS App

Native iOS app (Swift/SwiftUI) that uses your existing backend API and WebSocket for real-time chat.

## Requirements

- Xcode 15+ (Swift 5.9+)
- iOS 16+
- Backend running (local or AWS) with same API as the web app

## Setup

### 1. Create the project in Xcode

1. Open **Xcode** → **File** → **New** → **Project**
2. Choose **App** (under iOS)
3. **Product Name:** `ScheduledMessenger`
4. **Team:** your Apple Developer team (or None for simulator)
5. **Organization Identifier:** e.g. `com.yourcompany`
6. **Interface:** SwiftUI  
7. **Language:** Swift  
8. **Storage:** None (we use UserDefaults for token)
9. Create the project and delete the default `ContentView.swift` and `ScheduledMessengerApp.swift` that Xcode generated (we provide our own).

### 2. Add the app source files

1. In Xcode, right‑click the **ScheduledMessenger** group in the Project Navigator.
2. **Add Files to "ScheduledMessenger"…**
3. Select the **ScheduledMessenger** folder from this repo (the one containing `ScheduledMessengerApp.swift`, `Models`, `Services`, `Views`).
4. Check **Copy items if needed** and **Create groups**.
5. Ensure the **ScheduledMessenger** target is checked for all added files.

### 3. Configure the backend URL

1. Open **Config.swift** in Xcode.
2. Set `apiBaseURL` to your backend:
   - Local: `http://localhost:5034` (or your Flask port)
   - AWS: `https://your-env.elasticbeanstalk.com` (or your API URL)
3. For local HTTP (no HTTPS), add App Transport Security exception in **Info.plist** (see below).

### 4. Allow HTTP for local dev (optional)

If you use `http://` (e.g. localhost), add to **Info.plist**:

```xml
<key>NSAppTransportSecurity</key>
<dict>
  <key>NSExceptionDomains</key>
  <dict>
    <key>localhost</key>
    <dict>
      <key>NSExceptionAllowsInsecureHTTPLoads</key>
      <true/>
    </dict>
  </dict>
</dict>
```

Or in Xcode: target → **Info** → **App Transport Security Settings** → add exception for your host.

### 5. Contacts (for “My contacts” tab)

To show which of the user’s phone contacts are registered on the app, add the Contacts usage description:

- In Xcode: target → **Info** → add row **Privacy - Contacts Usage Description** (or `NSContactsUsageDescription`), value e.g. *“We match your contacts to show who is on the app so you can start a chat.”*

### 6. Run

- Select a simulator (e.g. iPhone 15) or a connected device.
- **Product** → **Run** (⌘R).

---

## How to test the iOS app on your laptop

Follow these steps to run and test the app against your backend on the same machine.

### Step 1: Start the backend on your laptop

In a terminal, from the project root:

```bash
cd /path/to/scheduled-messenger-agent
source .venv/bin/activate   # or: venv\Scripts\activate on Windows
python app.py
```

Leave it running. By default it listens on **http://127.0.0.1:5034** (or the port in `PORT` / `.env`). Note the port (e.g. **5034**).

### Step 2: Open the iOS project in Xcode

1. Open **Xcode**.
2. If you haven’t created the project yet: **File → New → Project → App** → Product Name **ScheduledMessenger**, Interface **SwiftUI**, then add the `ScheduledMessenger` source folder (see “Add the app source files” above).
3. If the project already exists: **File → Open** and select the folder that contains the **.xcodeproj** (or create a new project and add the `ios-app/ScheduledMessenger` folder into it).

### Step 3: Point the app at your local backend

1. In Xcode, open **Config.swift** (under the ScheduledMessenger group).
2. Set the URL to your local server. For example, in the `#if DEBUG` block:

   ```swift
   return "http://localhost:5034"
   ```

   Use the same port as in Step 1 (e.g. **5034**).

### Step 4: Allow HTTP to localhost (required for local testing)

The simulator must be allowed to call `http://localhost`.

1. In Xcode: select the **ScheduledMessenger** target → **Info** tab.
2. Under **Custom iOS Target Properties**, add (or edit):
   - **App Transport Security Settings** → Dictionary.
   - Under it add **Exception Domains** → Dictionary.
   - Under that add **localhost** → Dictionary.
   - Under **localhost** add **Allow Insecure HTTP Loads** → **YES** (Boolean).

Or add this to your **Info.plist** (if you use a plist file):

```xml
<key>NSAppTransportSecurity</key>
<dict>
  <key>NSExceptionDomains</key>
  <dict>
    <key>localhost</key>
    <dict>
      <key>NSExceptionAllowsInsecureHTTPLoads</key>
      <true/>
    </dict>
  </dict>
</dict>
```

### Step 5: Run the app in the simulator

1. At the top of Xcode, choose an **iPhone simulator** (e.g. **iPhone 15** or **iPhone 16**).
2. Press **⌘R** (or **Product → Run**).
3. Wait for the app to build and launch in the simulator.

### Step 6: Test the flow

1. **Register** – Tap “Register”, fill in username, password, first name, last name, phone (e.g. +15551234567), email. Tap “Create account”.
2. **Messages** – You should see the Messages tab with an empty list. Tap the pencil icon to start a new chat; you’ll need another user (create one in the web app or a second simulator/device).
3. **Chat** – Start a conversation with another user and send a message. It should appear and (if the backend is set up) reply suggestions can show.
4. **My contacts** – Add **Privacy - Contacts Usage Description** in Info if you want to test this tab; the simulator has no real contacts, but you can confirm the permission prompt and empty state.

### Optional: Test with the web app on the same backend

1. In a browser open **http://localhost:5034** (or your port).
2. Register or log in as a **second user**.
3. In the **iOS simulator**, start a new chat and pick that user. Send messages from both the app and the browser to verify real-time updates (WebSocket).

### Simulator vs physical device

- **Simulator:** Easiest for daily testing. Push notifications don’t work; everything else (auth, chat, drafts, contacts permission) works.
- **Physical iPhone:** Connect via USB, select the device as the run destination, then **Run**. You may need to set a **Team** in **Signing & Capabilities** and trust the developer certificate on the device. Push notifications only work on a real device with proper APNs setup.

### Troubleshooting

| Issue | What to do |
|-------|------------|
| “Could not connect” / request fails | Ensure `app.py` is running and **Config.swift** uses the same host/port (e.g. `http://localhost:5034`). For device, use your Mac’s IP (e.g. `http://192.168.1.10:5034`) and add that host to ATS exceptions. |
| Build errors about missing files | Ensure every file under `ScheduledMessenger/` is added to the app target (check **Target Membership** in the File Inspector). |
| Login/Register returns 401 or error | Backend and app must use the same JWT secret; the app only sends the token in headers. Check backend logs. |
| WebSocket not updating messages | Confirm the backend is running and the WebSocket URL in the app is correct (e.g. `ws://localhost:5034/ws`). |

## Features

- **Login / Register** – JWT auth against `/auth/login` and `/auth/register`
- **Conversation list** – GET `/api/conversations` with unread counts
- **Start new chat** – POST `/api/conversations` with `user_id`
- **My contacts** – Reads device contacts, matches phone numbers to registered users (POST `/api/users/match-phones`), shows “contacts on the app”; tap to start a chat
- **Chat view** – Load messages (GET), send (POST), real-time via WebSocket
- **WebSocket** – Connect to `/ws?token=JWT`; receive `new_message`, `new_draft`, `message_failed`, `message_scheduled`

## API / WebSocket (same as web)

- **Auth:** `POST /auth/register`, `POST /auth/login` → `{ token, user }`; use `Authorization: Bearer <token>` for API.
- **Conversations:** `GET /api/conversations`, `POST /api/conversations` (body: `{ "user_id": 2 }`).
- **Messages:** `GET /api/conversations/:id/messages`, `POST /api/conversations/:id/messages` (body: `{ "content": "..." }`).
- **Users:** `GET /api/users` (for "Start new chat"); `POST /api/users/match-phones` with body `{ "phones": ["+15551234567", ...] }` returns registered users whose phone is in the list (for "My contacts"). (for “Start new chat”).
- **WebSocket:** `wss://your-host/ws?token=<JWT>`. Server pushes: `new_message`, `new_draft`, `message_failed`, `message_scheduled`.

## Project structure

```
ScheduledMessenger/
├── ScheduledMessengerApp.swift   # App entry
├── ContentView.swift            # Root: login vs main
├── Config.swift                 # Base URL
├── Models/
│   ├── User.swift
│   ├── Conversation.swift
│   └── Message.swift
├── Services/
│   ├── AuthService.swift        # Token, login, register
│   ├── APIClient.swift          # HTTP + Bearer
│   ├── WebSocketClient.swift    # Real-time
│   └── ContactMatchService.swift # Device contacts + phone normalization
└── Views/
    ├── LoginView.swift
    ├── RegisterView.swift
    ├── ConversationListView.swift
    ├── ChatView.swift
    ├── MyContactsView.swift    # Contacts on the app (device contacts matched to users)
    └── MainTabView.swift
```

## Push notifications (APNs)

- The app requests notification permission on login and registers the device token with the backend (`POST /api/device-token`).
- When a new message arrives, the server sends an APNs push to recipients (if configured).
- Tapping the notification opens the app to that conversation (sheet with `ChatView`).

**Backend (optional):** Set these env vars to enable APNs:

- `APNS_KEY_ID` – Key ID from Apple Developer (Keys → APNs)
- `APNS_TEAM_ID` – Team ID
- `APNS_BUNDLE_ID` – App bundle ID (e.g. `com.yourcompany.ScheduledMessenger`)
- `APNS_AUTH_KEY_PATH` – Path to the `.p8` auth key file, or `APNS_AUTH_KEY_CONTENT` with the key body
- `APNS_SANDBOX=1` – Use sandbox APNs (for development)

**Xcode:** Enable **Push Notifications** in **Signing & Capabilities** for the app target.

## Draft suggestions (reply suggestions)

- When the backend sends a **reply suggestion** (`new_draft` over WebSocket), it appears as a **banner** at the top of the chat.
- **Approve** sends the suggested message; **Reject** dismisses it. Same behavior as the web UI.
- Sending any message in that conversation clears the current suggestion.
