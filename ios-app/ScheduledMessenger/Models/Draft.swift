import Foundation

struct Draft: Codable, Identifiable {
    let id: Int
    let conversation_id: Int
    let sender_id: Int
    var content: String?
    var status: String?
}
