import Foundation

struct User: Codable, Identifiable, Equatable {
    let id: Int
    let username: String
    var first_name: String?
    var last_name: String?
    var phone: String?

    var displayName: String {
        [first_name, last_name].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " ")
            .isEmpty ? username : [first_name, last_name].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " ")
    }
}
