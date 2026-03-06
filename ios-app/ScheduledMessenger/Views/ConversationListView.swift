import SwiftUI
import UIKit
import UserNotifications

struct ConversationListView: View {
    @State private var conversations: [Conversation] = []
    @State private var users: [User] = []
    @State private var isLoading = true
    @State private var errorMessage: String?
    @State private var showNewChat = false
    @State private var selectedUser: User?
    @State private var contactNameByCanonicalDigits: [String: String] = [:]
    @State private var conversationToOpen: Conversation?
    @ObservedObject private var pushStore = PushOpenStore.shared
    @EnvironmentObject var auth: AuthService
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        NavigationStack {
            Group {
                if isLoading && conversations.isEmpty {
                    ProgressView("Loading…")
                } else if let err = errorMessage {
                    ContentUnavailableView("Error", systemImage: "exclamationmark.triangle", description: Text(err))
                } else {
                    List {
                        ForEach(conversations) { conv in
                            NavigationLink(value: conv) {
                                ConversationRow(conversation: conv)
                            }
                            .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                                Button(role: .destructive) {
                                    Task { await deleteConversation(conv) }
                                } label: {
                                    Label("Delete", systemImage: "trash")
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Messages")
            .refreshable { await load() }
            .task { await load() }
            .onChange(of: scenePhase) { _, phase in
                // Refresh badge after returning to foreground.
                if phase == .active {
                    Task { await loadConversations() }
                }
            }
            .navigationDestination(for: Conversation.self) { conv in
                ChatView(conversation: conv)
            }
            .navigationDestination(item: $conversationToOpen) { conv in
                ChatView(conversation: conv)
                    .onDisappear { conversationToOpen = nil }
            }
            .sheet(isPresented: $showNewChat) {
                UserPickerView(users: users, contactNameByCanonicalDigits: contactNameByCanonicalDigits) { user in
                    selectedUser = user
                    showNewChat = false
                    Task { await startConversation(with: user) }
                }
                .presentationDetents([.medium])
            }
            .sheet(isPresented: Binding(
                get: { pushStore.conversationIdToOpen != nil },
                set: { if !$0 { pushStore.clear() } }
            )) {
                if let id = pushStore.conversationIdToOpen {
                    NavigationStack {
                        ChatView(conversation: Conversation(id: id, other_user: nil))
                            .toolbar {
                                ToolbarItem(placement: .cancellationAction) {
                                    Button("Close") { pushStore.clear() }
                                }
                            }
                    }
                }
            }
            .onChange(of: selectedUser) { _, _ in }
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button { showNewChat = true } label: {
                        Image(systemName: "square.and.pencil")
                    }
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: .didReceiveNewMessage)) { _ in
                Task { await loadConversations() }
            }
        }
    }

    private func load() async {
        isLoading = true
        errorMessage = nil
        do {
            async let convs: () = loadConversations()
            async let u: () = loadUsers()
            _ = await (convs, u)
        }
        await MainActor.run { isLoading = false }
    }

    private func loadConversations() async {
        do {
            let list = try await APIClient.shared.getConversations()
            await MainActor.run {
                conversations = list
                updateAppBadge(from: list)
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    private func updateAppBadge(from list: [Conversation]) {
        let total = list.reduce(0) { $0 + max(0, $1.unread_count ?? 0) }
        setAppBadgeCount(total)
    }

    private func setAppBadgeCount(_ count: Int) {
        let clamped = max(0, count)
        if #available(iOS 17.0, *) {
            UNUserNotificationCenter.current().setBadgeCount(clamped) { _ in }
        } else {
            setLegacyBadgeCount(clamped)
        }
    }

    @available(iOS, deprecated: 17.0)
    private func setLegacyBadgeCount(_ count: Int) {
        UIApplication.shared.applicationIconBadgeNumber = count
    }

    private func loadUsers() async {
        do {
            let index = try await ContactMatchService.fetchDeviceContactIndex()
            let matched = try await APIClient.shared.matchPhones(index.phonesForMatch)
            await MainActor.run {
                contactNameByCanonicalDigits = index.contactNameByCanonicalDigits
                users = dedupeUsersByPhone(matched)
            }
        } catch {
            // Non-fatal; new chat picker may be empty (e.g. user denied Contacts permission)
        }
    }

    private func dedupeUsersByPhone(_ input: [User]) -> [User] {
        var seen: Set<String> = []
        var out: [User] = []
        for u in input {
            let key = ContactMatchService.canonicalDigits(u.phone ?? "") ?? ""
            if key.isEmpty {
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

    private func startConversation(with user: User) async {
        do {
            let created = try await APIClient.shared.createConversation(userId: user.id)
            let toOpen = Conversation(
                id: created.id,
                created_at: created.created_at,
                last_message: nil,
                unread_count: nil,
                other_user: user
            )
            await MainActor.run {
                conversationToOpen = toOpen
            }
            await loadConversations()
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    private func deleteConversation(_ conv: Conversation) async {
        do {
            try await APIClient.shared.deleteConversation(conversationId: conv.id)
            await MainActor.run {
                conversations.removeAll { $0.id == conv.id }
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }
}

struct ConversationRow: View {
    let conversation: Conversation

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(conversation.other_user?.displayName ?? "Chat")
                    .font(.headline)
                if let last = conversation.last_message?.content {
                    Text(last)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            Spacer()
            if let count = conversation.unread_count, count > 0 {
                Text("\(count)")
                    .font(.caption)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(.blue, in: Capsule())
                    .foregroundStyle(.white)
            }
        }
        .padding(.vertical, 4)
    }
}

struct UserPickerView: View {
    let users: [User]
    let contactNameByCanonicalDigits: [String: String]
    let onSelect: (User) -> Void
    @Environment(\.dismiss) var dismiss
    @State private var searchText: String = ""

    private var filteredUsers: [User] {
        let q = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        let qNorm = normalizedForSearch(q)
        let qDigits = q.filter(\.isNumber)
        guard !q.isEmpty else { return users }
        return users.filter { u in
            let display = normalizedForSearch(displayNameForUser(u))
            let appName = normalizedForSearch(u.displayName)
            let phoneDigitsRaw = (u.phone ?? "").filter(\.isNumber)
            let phoneDigitsCanonical = ContactMatchService.canonicalDigits(u.phone ?? "") ?? ""
            let matchesName = display.contains(qNorm) || appName.contains(qNorm)
            let matchesPhone =
                !qDigits.isEmpty
                && (phoneDigitsRaw.contains(qDigits) || phoneDigitsCanonical.contains(qDigits))
            return matchesName || matchesPhone
        }
    }

    var body: some View {
        NavigationStack {
            Group {
                if filteredUsers.isEmpty {
                    ContentUnavailableView(
                        "No contacts on the app",
                        systemImage: "person.crop.circle.badge.questionmark",
                        description: Text("Only contacts from your phone who have registered will appear here.")
                    )
                } else {
                    List(filteredUsers) { user in
                        Button {
                            onSelect(user)
                            dismiss()
                        } label: {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(displayNameForUser(user))
                                Text("On app as \(user.displayName)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text((user.phone ?? "").isEmpty ? "" : (user.phone ?? ""))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
            .navigationTitle("New chat")
            .searchable(text: $searchText, prompt: "Search contacts")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }

    private func displayNameForUser(_ user: User) -> String {
        let key = ContactMatchService.canonicalDigits(user.phone ?? "") ?? ""
        if let name = contactNameByCanonicalDigits[key], !name.isEmpty, name != "Unknown" {
            return name
        }
        return user.displayName
    }

    private func normalizedForSearch(_ s: String) -> String {
        let folded = s.folding(options: [.diacriticInsensitive, .widthInsensitive, .caseInsensitive], locale: .current)
        let cleaned = folded
            .replacingOccurrences(of: "[^\\p{L}\\p{N}]+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return cleaned.lowercased()
    }
}
