import Foundation

struct Message: Codable, Identifiable {
    let id: Int
    let conversation_id: Int
    let sender_id: Int
    var sender_username: String?
    var content: String?
    var created_at: String?

    var isFromMe: Bool {
        // Compare with current user id where used
        false
    }
}
