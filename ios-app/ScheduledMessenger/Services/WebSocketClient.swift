import Foundation
import Combine
import UserNotifications
import UIKit

/// WebSocket client for real-time new_message, new_draft, etc.
final class WebSocketClient: ObservableObject {
    static let shared = WebSocketClient()

    @Published var isConnected = false
    @Published var lastError: String?

    var onNewMessage: ((WSNewMessage) -> Void)?
    var onNewDraft: ((WSDraft) -> Void)?
    var onMessageFailed: ((Int, String) -> Void)?
    var onMessageScheduled: ((Int, [String: Any]) -> Void)?

    private var task: URLSessionWebSocketTask?
    private var pingTimer: Timer?
    private let session = URLSession(configuration: .default)

    func connect() {
        guard let token = AuthService.shared.token?.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
              let url = URL(string: "\(Config.wsURL)?token=\(token)") else {
            lastError = "No token"
            return
        }
        disconnect()
        let req = URLRequest(url: url)
        task = session.webSocketTask(with: req)
        task?.resume()
        isConnected = true
        lastError = nil
        receive()
        startPing()
    }

    func disconnect() {
        pingTimer?.invalidate()
        pingTimer = nil
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        isConnected = false
    }

    private func receive() {
        task?.receive { [weak self] result in
            switch result {
            case .success(let message):
                switch message {
                case .string(let text):
                    self?.handleMessage(text)
                case .data(let data):
                    if let s = String(data: data, encoding: .utf8) { self?.handleMessage(s) }
                @unknown default:
                    break
                }
                self?.receive()
            case .failure:
                self?.isConnected = false
                self?.lastError = "WebSocket closed"
            }
        }
    }

    private func handleMessage(_ text: String) {
        guard let data = text.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = json["type"] as? String else { return }
        switch type {
        case "new_message":
            if let convId = json["conversation_id"] as? Int,
               let msg = json["message"] as? [String: Any],
               let msgData = try? JSONSerialization.data(withJSONObject: msg) {
                let message = try? JSONDecoder().decode(Message.self, from: msgData)
                if let m = message {
                    onNewMessage?(WSNewMessage(conversation_id: convId, message: m))
                    NotificationCenter.default.post(
                        name: .didReceiveNewMessage,
                        object: nil,
                        userInfo: ["conversation_id": convId]
                    )
                    maybeNotifyInForeground(message: m)
                }
            }
        case "new_draft":
            if let draftDict = json["draft"] as? [String: Any] {
                let payload = WSDraft(conversation_id: draftDict["conversation_id"] as? Int ?? 0, draft: draftDict)
                onNewDraft?(payload)
                if let id = draftDict["id"] as? Int, let cid = draftDict["conversation_id"] as? Int, let sid = draftDict["sender_id"] as? Int {
                    let draft = Draft(id: id, conversation_id: cid, sender_id: sid, content: draftDict["content"] as? String, status: draftDict["status"] as? String)
                    Task { @MainActor in DraftsStore.shared.add(draft) }
                }
            }
        case "message_failed":
            if let convId = json["conversation_id"] as? Int, let err = json["error"] as? String {
                onMessageFailed?(convId, err)
            }
        case "message_scheduled":
            if let convId = json["conversation_id"] as? Int {
                var payload: [String: Any] = [:]
                if let sendAt = json["send_at"] { payload["send_at"] = sendAt }
                onMessageScheduled?(convId, payload)
            }
        default:
            break
        }
    }

    private func maybeNotifyInForeground(message: Message) {
        guard message.sender_id != AuthService.shared.currentUser?.id else { return }
        // If app is active, remote pushes won't present; show a local banner.
        guard UIApplication.shared.applicationState == .active else { return }

        let content = UNMutableNotificationContent()
        content.title = message.sender_username ?? "New message"
        content.body = (message.content ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? "New message"
            : (message.content ?? "")
        content.sound = .default
        content.userInfo["conversation_id"] = message.conversation_id

        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil
        )
        UNUserNotificationCenter.current().add(request)
    }

    private func startPing() {
        pingTimer?.invalidate()
        pingTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            self?.task?.send(.string("ping")) { _ in }
        }
        RunLoop.main.add(pingTimer!, forMode: .common)
    }
}

struct WSNewMessage {
    let conversation_id: Int
    let message: Message
}

struct WSDraft {
    let conversation_id: Int
    let draft: [String: Any]
}

extension Notification.Name {
    static let didReceiveNewMessage = Notification.Name("didReceiveNewMessage")
}
