import UIKit
import UserNotifications

/// Handles APNs device token and notification tap (open conversation).
final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }

    static var currentDeviceToken: String? {
        get { UserDefaults.standard.string(forKey: "apns_device_token") }
        set { UserDefaults.standard.set(newValue, forKey: "apns_device_token") }
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
        Self.currentDeviceToken = token
        Task {
            await registerTokenWithBackend(token)
        }
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        // e.g. simulator, or user denied
    }

    private func registerTokenWithBackend(_ token: String) async {
        guard AuthService.shared.isLoggedIn else { return }
        let body = ["device_token": token, "platform": "ios"]
        guard let data = try? JSONSerialization.data(withJSONObject: body) else { return }
        do {
            let (_, resp) = try await APIClient.shared.request(path: "/api/device-token", method: "POST", body: data)
            guard (resp as? HTTPURLResponse)?.statusCode == 200 else { return }
        } catch { }
    }

    // User tapped notification -> open conversation
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse, withCompletionHandler completionHandler: @escaping () -> Void) {
        let userInfo = response.notification.request.content.userInfo
        if let cid = userInfo["conversation_id"] as? Int {
            DispatchQueue.main.async {
                PushOpenStore.shared.open(conversationId: cid)
            }
            NotificationCenter.default.post(name: .openConversation, object: nil, userInfo: ["conversation_id": cid])
        }
        completionHandler()
    }

    // Show notification even when app is in foreground (optional)
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification, withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound, .badge])
    }
}

extension Notification.Name {
    static let openConversation = Notification.Name("openConversation")
}
