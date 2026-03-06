import SwiftUI

struct ChatView: View {
    let conversation: Conversation
    @State private var messages: [Message] = []
    @State private var inputText = ""
    @State private var isLoading = true
    @State private var sendError: String?
    @State private var feedbackMessage: String?
    @ObservedObject private var draftsStore = DraftsStore.shared
    @EnvironmentObject var auth: AuthService
    @Environment(\.dismiss) var dismiss
    @Environment(\.scenePhase) private var scenePhase

    private var currentUserId: Int { auth.currentUser?.id ?? 0 }
    private var draftForThisConversation: Draft? { draftsStore.draft(for: conversation.id) }

    var body: some View {
        VStack(spacing: 0) {
            if let draft = draftForThisConversation {
                DraftBannerView(draft: draft, conversationId: conversation.id)
                    .padding(.vertical, 6)
            }
            if let err = sendError {
                Text(err).font(.caption).foregroundStyle(.red).padding(4)
            }
            if let fb = feedbackMessage {
                Text(fb).font(.caption).foregroundStyle(.secondary).padding(4)
            }
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(messages) { msg in
                            MessageBubble(
                                message: msg,
                                isFromMe: msg.sender_id == currentUserId
                            )
                            .id(msg.id)
                        }
                        Color.clear
                            .frame(height: 1)
                            .id("BOTTOM")
                    }
                    .padding()
                }
                .onChange(of: messages.count) { _, _ in
                    scrollToBottom(proxy: proxy, animated: true)
                }
                .onAppear {
                    scrollToBottom(proxy: proxy, animated: false)
                }
            }
            .background(Color(.systemGroupedBackground))

            HStack(spacing: 12) {
                TextField("Message", text: $inputText, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                    .lineLimit(1...6)
                Button(action: sendMessage) {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.title2)
                }
                .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding()
            .background(Color(.systemBackground))
        }
        .navigationTitle(conversation.other_user?.displayName ?? "Chat")
        .navigationBarTitleDisplayMode(.inline)
        .task { await loadMessages() }
        .onAppear {
            let convId = conversation.id
            Task { await markReadAndRefreshBadge(conversationId: convId) }
            WebSocketClient.shared.onNewMessage = { payload in
                guard payload.conversation_id == convId else { return }
                Task { @MainActor in
                    if !messages.contains(where: { $0.id == payload.message.id }) {
                        messages.append(payload.message)
                    }
                }
            }
            WebSocketClient.shared.onMessageFailed = { convId, err in
                guard convId == conversation.id else { return }
                Task { @MainActor in
                    sendError = err
                    feedbackMessage = nil
                }
            }
            WebSocketClient.shared.onMessageScheduled = { convId, data in
                guard convId == conversation.id else { return }
                Task { @MainActor in
                    feedbackMessage = "Scheduled for \(data["send_at"] as? String ?? "later")"
                }
            }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active {
                Task { await markReadAndRefreshBadge(conversationId: conversation.id) }
            }
        }
        .onDisappear {
            // Stop updating this view's state after it's gone (avoids "accumulator after completion" errors)
            if WebSocketClient.shared.onNewMessage != nil {
                WebSocketClient.shared.onNewMessage = nil
            }
            WebSocketClient.shared.onMessageFailed = nil
            WebSocketClient.shared.onMessageScheduled = nil
        }
    }

    private func loadMessages() async {
        do {
            let list = try await APIClient.shared.getMessages(conversationId: conversation.id)
            await MainActor.run {
                messages = list
                isLoading = false
            }
        } catch {
            await MainActor.run {
                sendError = error.localizedDescription
                isLoading = false
            }
        }
    }

    private func sendMessage() {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        inputText = ""
        sendError = nil
        feedbackMessage = nil
        Task {
            do {
                try await APIClient.shared.sendMessage(conversationId: conversation.id, content: text)
                await MainActor.run { draftsStore.remove(conversationId: conversation.id) }
                // Message will appear via WebSocket when backend pushes it
            } catch {
                await MainActor.run { sendError = error.localizedDescription }
            }
        }
    }

    private func scrollToBottom(proxy: ScrollViewProxy, animated: Bool) {
        // Scroll after layout so the bottom anchor exists.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
            if animated {
                withAnimation(.easeOut(duration: 0.2)) {
                    proxy.scrollTo("BOTTOM", anchor: .bottom)
                }
            } else {
                proxy.scrollTo("BOTTOM", anchor: .bottom)
            }
        }
    }

    private func markReadAndRefreshBadge(conversationId: Int) async {
        do {
            try await APIClient.shared.markConversationRead(conversationId: conversationId)
            NotificationCenter.default.post(name: .didReceiveNewMessage, object: nil)
        } catch {
            // Non-fatal
        }
    }
}

struct MessageBubble: View {
    let message: Message
    let isFromMe: Bool

    var body: some View {
        HStack {
            if isFromMe { Spacer(minLength: 60) }
            Text(message.content ?? "")
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(isFromMe ? Color.blue : Color(.systemGray5), in: RoundedRectangle(cornerRadius: 16))
                .foregroundColor(isFromMe ? .white : .primary)
            if !isFromMe { Spacer(minLength: 60) }
        }
    }
}
