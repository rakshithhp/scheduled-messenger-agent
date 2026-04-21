import Foundation

/// Backend base URL. Change for local dev or production.
enum Config {
    /// Local: "http://localhost:5034". For AWS, set #else to your EB URL.
    static var apiBaseURL: String {
        #if DEBUG
        return "http://localhost:5034"
        #else
        return "http://localhost:5034"
        #endif
    }

    static var wsURL: String {
        let base = apiBaseURL
            .replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "http://", with: "ws://")
        return "\(base)/ws"
    }
}
