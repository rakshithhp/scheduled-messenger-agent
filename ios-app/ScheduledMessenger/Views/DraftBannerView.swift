import SwiftUI

/// Banner showing a suggested reply (draft) with Approve / Reject, like the web UI.
struct DraftBannerView: View {
    let draft: Draft
    let conversationId: Int
    @State private var isApproving = false
    @State private var isRejecting = false
    @ObservedObject var draftsStore = DraftsStore.shared
    @EnvironmentObject var auth: AuthService

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Suggested reply")
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(draft.content ?? "")
                .font(.subheadline)
                .lineLimit(3)
            HStack(spacing: 12) {
                Button("Approve") {
                    approve()
                }
                .disabled(isApproving || isRejecting)
                .buttonStyle(.borderedProminent)
                Button("Reject") {
                    reject()
                }
                .disabled(isApproving || isRejecting)
                .buttonStyle(.bordered)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.systemGray6), in: RoundedRectangle(cornerRadius: 12))
        .padding(.horizontal)
    }

    private func approve() {
        guard draft.sender_id == auth.currentUser?.id else { return }
        isApproving = true
        Task {
            do {
                _ = try await APIClient.shared.approveDraft(draftId: draft.id)
                await MainActor.run {
                    draftsStore.remove(draftId: draft.id, conversationId: conversationId)
                }
            } catch { }
            await MainActor.run { isApproving = false }
        }
    }

    private func reject() {
        guard draft.sender_id == auth.currentUser?.id else { return }
        isRejecting = true
        Task {
            do {
                try await APIClient.shared.rejectDraft(draftId: draft.id)
                await MainActor.run {
                    draftsStore.remove(draftId: draft.id, conversationId: conversationId)
                }
            } catch { }
            await MainActor.run { isRejecting = false }
        }
    }
}
