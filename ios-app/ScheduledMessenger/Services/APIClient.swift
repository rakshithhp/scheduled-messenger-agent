import Foundation

final class APIClient {
    static let shared = APIClient()

    private let base: String
    private let session: URLSession

    init(baseURL: String = Config.apiBaseURL) {
        self.base = baseURL.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        self.session = URLSession.shared
    }

    func request(
        path: String,
        method: String = "GET",
        body: Data? = nil,
        requiresAuth: Bool = true
    ) async throws -> (Data, URLResponse) {
        let urlPath = path.hasPrefix("/") ? path : "/\(path)"
        guard let url = URL(string: "\(base)\(urlPath)") else {
            throw AppError.api("Invalid URL")
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Accept")
        if requiresAuth, let token = AuthService.shared.token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = body
        return try await session.data(for: request)
    }

    // MARK: - Conversations

    func getConversations() async throws -> [Conversation] {
        let (data, resp) = try await request(path: "/api/conversations")
        try checkResponse(data: data, response: resp, status: 200)
        return try JSONDecoder().decode([Conversation].self, from: data)
    }

    func createConversation(userId: Int) async throws -> Conversation {
        let body = try JSONSerialization.data(withJSONObject: ["user_id": userId])
        let (data, resp) = try await request(path: "/api/conversations", method: "POST", body: body)
        try checkResponse(data: data, response: resp, status: 201)
        return try JSONDecoder().decode(Conversation.self, from: data)
    }

    func deleteConversation(conversationId: Int) async throws {
        let (data, resp) = try await request(path: "/api/conversations/\(conversationId)", method: "DELETE")
        try checkResponse(data: data, response: resp, status: 200)
    }

    func markConversationRead(conversationId: Int) async throws {
        let (data, resp) = try await request(path: "/api/conversations/\(conversationId)/read", method: "POST")
        try checkResponse(data: data, response: resp, status: 200)
    }

    // MARK: - Messages

    func getMessages(conversationId: Int) async throws -> [Message] {
        let (data, resp) = try await request(path: "/api/conversations/\(conversationId)/messages")
        try checkResponse(data: data, response: resp, status: 200)
        return try JSONDecoder().decode([Message].self, from: data)
    }

    func sendMessage(conversationId: Int, content: String) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["content": content])
        let (_, resp) = try await request(
            path: "/api/conversations/\(conversationId)/messages",
            method: "POST",
            body: body
        )
        // 202 = accepted (sending in background); 201 = sent sync
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        guard code == 201 || code == 202 else {
            throw AppError.api("Send failed")
        }
    }

    // MARK: - Users (for new chat)

    func getUsers() async throws -> [User] {
        let (data, resp) = try await request(path: "/api/users")
        try checkResponse(data: data, response: resp, status: 200)
        return try JSONDecoder().decode([User].self, from: data)
    }

    /// Match device contact phone numbers to registered users. Returns users whose phone is in the list.
    func matchPhones(_ phones: [String]) async throws -> [User] {
        guard !phones.isEmpty else { return [] }
        let body = try JSONSerialization.data(withJSONObject: ["phones": phones])
        let (data, resp) = try await request(path: "/api/users/match-phones", method: "POST", body: body)
        try checkResponse(data: data, response: resp, status: 200)
        return try JSONDecoder().decode([User].self, from: data)
    }

    // MARK: - Drafts (reply suggestions)

    func getDrafts() async throws -> [Draft] {
        let (data, resp) = try await request(path: "/api/drafts")
        try checkResponse(data: data, response: resp, status: 200)
        return try JSONDecoder().decode([Draft].self, from: data)
    }

    func approveDraft(draftId: Int) async throws -> Message? {
        let (data, resp) = try await request(path: "/api/drafts/\(draftId)/approve", method: "POST")
        try checkResponse(data: data, response: resp, status: 200)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        guard let msg = json?["message"] as? [String: Any],
              let msgData = try? JSONSerialization.data(withJSONObject: msg) else { return nil }
        return try? JSONDecoder().decode(Message.self, from: msgData)
    }

    func rejectDraft(draftId: Int) async throws {
        let (_, resp) = try await request(path: "/api/drafts/\(draftId)/reject", method: "POST")
        try checkResponse(data: Data(), response: resp, status: 200)
    }

    // MARK: - Device token (push)

    func registerDeviceToken(_ deviceToken: String) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["device_token": deviceToken, "platform": "ios"])
        let (data, resp) = try await request(path: "/api/device-token", method: "POST", body: body, requiresAuth: true)
        try checkResponse(data: data, response: resp, status: 200)
    }

    func unregisterDeviceToken(_ deviceToken: String, bearerToken: String? = nil) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["device_token": deviceToken])
        let useAuth = bearerToken == nil
        var (data, resp): (Data, URLResponse)
        if let b = bearerToken {
            var req = URLRequest(url: URL(string: "\(base)/api/device-token")!)
            req.httpMethod = "DELETE"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.setValue("Bearer \(b)", forHTTPHeaderField: "Authorization")
            req.httpBody = body
            (data, resp) = try await session.data(for: req)
        } else {
            (data, resp) = try await request(path: "/api/device-token", method: "DELETE", body: body, requiresAuth: useAuth)
        }
        try checkResponse(data: data, response: resp, status: 200)
    }

    private func checkResponse(data: Data, response: URLResponse, status: Int) throws {
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 {
            AuthService.shared.logout()
            throw AppError.api("Please log in again")
        }
        guard code == status else {
            if let err = try? JSONDecoder().decode(APIError.self, from: data) {
                throw AppError.api(err.error)
            }
            throw AppError.api("Request failed")
        }
    }
}
