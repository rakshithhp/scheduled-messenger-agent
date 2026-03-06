import Foundation

struct Conversation: Codable, Identifiable {
    let id: Int
    var created_at: String?
    var last_message: LastMessage?
    var unread_count: Int?
    var other_user: User?
}

struct LastMessage: Codable {
    var content: String?
    var created_at: String?
}
