import SwiftUI

/// Shows device contacts who are registered on the app (phone number match).
struct MyContactsView: View {
    @State private var users: [User] = []
    @State private var isLoading = true
    @State private var errorMessage: String?
    @State private var selectedUser: User?
    @State private var conversationToOpen: Conversation?
    @State private var isStartingChat = false
    @State private var contactNameByCanonicalDigits: [String: String] = [:]
    @State private var searchText: String = ""
    @EnvironmentObject var auth: AuthService

    private var filteredUsers: [User] {
        let q = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        let qNorm = normalizedForSearch(q)
        let qDigits = q.filter(\.isNumber)
        guard !q.isEmpty else { return users }
        return users.filter { u in
            let contactName = normalizedForSearch(displayNameForUser(u))
            let appName = normalizedForSearch(u.displayName)
            let phoneDigitsRaw = (u.phone ?? "").filter(\.isNumber)
            let phoneDigitsCanonical = ContactMatchService.canonicalDigits(u.phone ?? "") ?? ""
            let matchesName = contactName.contains(qNorm) || appName.contains(qNorm)
            let matchesPhone =
                !qDigits.isEmpty
                && (phoneDigitsRaw.contains(qDigits) || phoneDigitsCanonical.contains(qDigits))
            return matchesName || matchesPhone
        }
    }

    var body: some View {
        NavigationStack {
            Group {
                if isLoading && users.isEmpty {
                    ProgressView("Reading contacts…")
                } else if let err = errorMessage {
                    VStack(spacing: 12) {
                        Text(err)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                            .padding()
                        Button("Try again") { Task { await load() } }
                    }
                } else if users.isEmpty {
                    ContentUnavailableView(
                        "No contacts on the app",
                        systemImage: "person.crop.circle.badge.questionmark",
                        description: Text("Contacts from your phone who have registered will appear here.")
                    )
                } else {
                    List(filteredUsers) { user in
                        Button {
                            startChat(with: user)
                        } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(displayNameForUser(user))
                                        .font(.headline)
                                    Text("On app as \(user.displayName)")
                                        .font(.subheadline)
                                        .foregroundStyle(.secondary)
                                    if let phone = user.phone {
                                        Text(phone)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                                Spacer()
                                Image(systemName: "message")
                                    .foregroundStyle(.secondary)
                            }
                            .padding(.vertical, 4)
                        }
                    }
                }
            }
            .navigationTitle("My contacts")
            .searchable(text: $searchText, prompt: "Search contacts")
            .refreshable { await load() }
            .task { await load() }
            .navigationDestination(item: $conversationToOpen) { conv in
                ChatView(conversation: conv)
                    .onDisappear {
                        conversationToOpen = nil
                    }
            }
        }
    }

    private func load() async {
        isLoading = true
        errorMessage = nil
        do {
            let index = try await ContactMatchService.fetchDeviceContactIndex()
            let matched = try await APIClient.shared.matchPhones(index.phonesForMatch)
            await MainActor.run {
                contactNameByCanonicalDigits = index.contactNameByCanonicalDigits
                users = dedupeUsersByPhone(matched)
                isLoading = false
            }
        } catch {
            await MainActor.run {
                errorMessage = friendlyErrorMessage(for: error)
                users = []
                isLoading = false
            }
        }
    }

    private func dedupeUsersByPhone(_ input: [User]) -> [User] {
        // When the backend has multiple accounts with the same phone (or phone formats vary),
        // de-dupe to avoid confusing duplicates in the UI.
        var seen: Set<String> = []
        var out: [User] = []
        for u in input {
            let key = ContactMatchService.canonicalDigits(u.phone ?? "") ?? ""
            if key.isEmpty {
                // If phone is missing, fall back to id-based uniqueness.
                let idKey = "id:\(u.id)"
                guard !seen.contains(idKey) else { continue }
                seen.insert(idKey)
                out.append(u)
                continue
            }
            guard !seen.contains(key) else { continue }
            seen.insert(key)
            out.append(u)
        }
        return out
    }

    private func displayNameForUser(_ user: User) -> String {
        let key = ContactMatchService.canonicalDigits(user.phone ?? "") ?? ""
        if let name = contactNameByCanonicalDigits[key], !name.isEmpty, name != "Unknown" {
            return name
        }
        return user.displayName
    }

    private func friendlyErrorMessage(for error: Error) -> String {
        guard let urlError = error as? URLError else { return error.localizedDescription }
        let code = urlError.code.rawValue
        if code == -1004 || code == -1022 {
            return "Cannot reach the server. Is the backend running? (e.g. python app.py)"
        }
        if code == -1009 || code == -1005 {
            return "No network connection."
        }
        return error.localizedDescription
    }

    private func startChat(with user: User) {
        guard !isStartingChat else { return }
        isStartingChat = true
        errorMessage = nil
        Task {
            do {
                let conv = try await APIClient.shared.createConversation(userId: user.id)
                await MainActor.run {
                    conversationToOpen = conv
                    isStartingChat = false
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isStartingChat = false
                }
            }
        }
    }

    private func normalizedForSearch(_ s: String) -> String {
        // Makes search resilient to case, diacritics, punctuation, and weird whitespace.
        let folded = s.folding(options: [.diacriticInsensitive, .widthInsensitive, .caseInsensitive], locale: .current)
        let cleaned = folded
            .replacingOccurrences(of: "[^\\p{L}\\p{N}]+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return cleaned.lowercased()
    }
}

extension Conversation: Hashable {
    public func hash(into hasher: inout Hasher) { hasher.combine(id) }
    public static func == (lhs: Conversation, rhs: Conversation) -> Bool { lhs.id == rhs.id }
}
