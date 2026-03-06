import Foundation
import Combine

/// When user taps a push notification, we set conversationIdToOpen so the UI can present that chat.
final class PushOpenStore: ObservableObject {
    static let shared = PushOpenStore()

    @Published var conversationIdToOpen: Int?

    func open(conversationId: Int) {
        conversationIdToOpen = conversationId
    }

    func clear() {
        conversationIdToOpen = nil
    }
}
