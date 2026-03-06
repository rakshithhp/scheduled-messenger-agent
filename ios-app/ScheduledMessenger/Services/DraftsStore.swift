import Foundation
import Combine

/// Holds pending reply-suggestion drafts (from WebSocket new_draft). Used by DraftBannerView.
final class DraftsStore: ObservableObject {
    static let shared = DraftsStore()

    @Published private(set) var draftsByConversation: [Int: Draft] = [:]

    var pendingDrafts: [Draft] {
        Array(draftsByConversation.values).filter { ($0.status ?? "pending") == "pending" }
    }

    func draft(for conversationId: Int) -> Draft? {
        draftsByConversation[conversationId]
    }

    func add(_ draft: Draft) {
        draftsByConversation[draft.conversation_id] = draft
    }

    func remove(draftId: Int, conversationId: Int) {
        if draftsByConversation[conversationId]?.id == draftId {
            draftsByConversation.removeValue(forKey: conversationId)
        }
    }

    func remove(conversationId: Int) {
        draftsByConversation.removeValue(forKey: conversationId)
    }
}
