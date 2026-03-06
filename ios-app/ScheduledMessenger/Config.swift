import Foundation

/// Backend base URL. Change for local dev or production.
enum Config {
    /// e.g. "http://localhost:5034" or "https://your-app.elasticbeanstalk.com"
    static var apiBaseURL: String {
        #if DEBUG
        return "http://localhost:5034"
        #else
        return "https://your-app.elasticbeanstalk.com"
        #endif
    }

    static var wsURL: String {
        let base = apiBaseURL
            .replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "http://", with: "ws://")
        return "\(base)/ws"
    }
}
