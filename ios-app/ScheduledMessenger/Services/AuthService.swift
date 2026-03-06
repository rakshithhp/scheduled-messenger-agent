import Foundation
import Combine

final class AuthService: ObservableObject {
    static let shared = AuthService()

    @Published private(set) var token: String?
    @Published private(set) var currentUser: User?

    private let tokenKey = "auth_token"
    private let userKey = "auth_user"

    init() {
        token = UserDefaults.standard.string(forKey: tokenKey)
        if let data = UserDefaults.standard.data(forKey: userKey),
           let user = try? JSONDecoder().decode(User.self, from: data) {
            currentUser = user
        } else {
            currentUser = nil
        }
    }

    var isLoggedIn: Bool { token != nil && currentUser != nil }

    func login(username: String, password: String) async throws {
        let body: [String: Any] = ["username": username, "password": password]
        let data = try JSONSerialization.data(withJSONObject: body)
        let (responseData, response) = try await APIClient.shared.request(
            path: "/auth/login",
            method: "POST",
            body: data,
            requiresAuth: false
        )
        guard (response as? HTTPURLResponse)?.statusCode == 200 else {
            if let err = try? JSONDecoder().decode(APIError.self, from: responseData) {
                throw AppError.api(err.error)
            }
            throw AppError.api("Login failed")
        }
        let auth = try JSONDecoder().decode(AuthResponse.self, from: responseData)
        setSession(token: auth.token, user: auth.user)
    }

    func register(username: String, password: String, firstName: String, lastName: String, phone: String) async throws {
        let body: [String: Any] = [
            "username": username,
            "password": password,
            "first_name": firstName,
            "last_name": lastName,
            "phone": phone
        ]
        let data = try JSONSerialization.data(withJSONObject: body)
        let (responseData, response) = try await APIClient.shared.request(
            path: "/auth/register",
            method: "POST",
            body: data,
            requiresAuth: false
        )
        guard (response as? HTTPURLResponse)?.statusCode == 201 else {
            if let err = try? JSONDecoder().decode(APIError.self, from: responseData) {
                throw AppError.api(err.error)
            }
            throw AppError.api("Registration failed")
        }
        let auth = try JSONDecoder().decode(AuthResponse.self, from: responseData)
        setSession(token: auth.token, user: auth.user)
    }

    func updateProfile(firstName: String, lastName: String) async throws {
        let body: [String: Any] = ["first_name": firstName, "last_name": lastName]
        let data = try JSONSerialization.data(withJSONObject: body)
        let (responseData, response) = try await APIClient.shared.request(
            path: "/auth/me",
            method: "PATCH",
            body: data,
            requiresAuth: true
        )
        guard (response as? HTTPURLResponse)?.statusCode == 200 else {
            if let err = try? JSONDecoder().decode(APIError.self, from: responseData) {
                throw AppError.api(err.error)
            }
            throw AppError.api("Update failed")
        }
        let user = try JSONDecoder().decode(User.self, from: responseData)
        guard let existingToken = token else {
            throw AppError.api("Not logged in")
        }
        setSession(token: existingToken, user: user)
    }

    func logout() {
        let deviceToken = AppDelegate.currentDeviceToken
        let bearer = token
        token = nil
        currentUser = nil
        UserDefaults.standard.removeObject(forKey: tokenKey)
        UserDefaults.standard.removeObject(forKey: userKey)
        if let dt = deviceToken, let b = bearer {
            Task { try? await APIClient.shared.unregisterDeviceToken(dt, bearerToken: b) }
        }
    }

    private func setSession(token: String, user: User) {
        self.token = token
        self.currentUser = user
        UserDefaults.standard.set(token, forKey: tokenKey)
        if let data = try? JSONEncoder().encode(user) {
            UserDefaults.standard.set(data, forKey: userKey)
        }

        // If we already have an APNs token (e.g. granted before login), ensure backend has it.
        if let dt = AppDelegate.currentDeviceToken {
            Task { try? await APIClient.shared.registerDeviceToken(dt) }
        }
    }
}

struct AuthResponse: Codable {
    let token: String
    let user: User
}

struct APIError: Codable {
    let error: String
}

enum AppError: LocalizedError {
    case api(String)
    var errorDescription: String? { switch self { case .api(let s): return s } }
}
