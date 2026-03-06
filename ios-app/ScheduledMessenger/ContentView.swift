import SwiftUI
import UserNotifications

struct ContentView: View {
    @EnvironmentObject var auth: AuthService

    var body: some View {
        Group {
            if auth.isLoggedIn {
                MainTabView()
            } else {
                LoginView()
            }
        }
        .onChange(of: auth.isLoggedIn) { _, loggedIn in
            if loggedIn {
                WebSocketClient.shared.connect()
                requestPushPermissionAndRegister()
            } else {
                WebSocketClient.shared.disconnect()
            }
        }
        .onAppear {
            if auth.isLoggedIn {
                WebSocketClient.shared.connect()
                requestPushPermissionAndRegister()
            }
        }
    }

    private func requestPushPermissionAndRegister() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { _, _ in
            DispatchQueue.main.async {
                UIApplication.shared.registerForRemoteNotifications()
            }
        }
    }
}
