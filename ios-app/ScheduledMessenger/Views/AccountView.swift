import SwiftUI

struct AccountView: View {
    @EnvironmentObject var auth: AuthService

    @State private var isEditing = false
    @State private var firstName = ""
    @State private var lastName = ""
    @State private var errorMessage: String?
    @State private var isSaving = false

    private var currentUser: User? { auth.currentUser }

    var body: some View {
        NavigationStack {
            Form {
                Section("Account") {
                    LabeledContent("Username", value: currentUser?.username ?? "")
                    LabeledContent("Phone", value: currentUser?.phone ?? "")
                }

                Section("Profile") {
                    if isEditing {
                        TextField("First name", text: $firstName)
                        TextField("Last name", text: $lastName)
                    } else {
                        LabeledContent("First name", value: currentUser?.first_name ?? "")
                        LabeledContent("Last name", value: currentUser?.last_name ?? "")
                    }
                }

                if let err = errorMessage {
                    Section {
                        Text(err).foregroundStyle(.red)
                    }
                }

                Section {
                    if isEditing {
                        Button {
                            save()
                        } label: {
                            HStack {
                                if isSaving { ProgressView().scaleEffect(0.9) }
                                Text(isSaving ? "Saving…" : "Save changes")
                                    .frame(maxWidth: .infinity)
                            }
                        }
                        .disabled(isSaving || firstName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || lastName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

                        Button("Cancel", role: .cancel) {
                            isEditing = false
                            errorMessage = nil
                            hydrateFromCurrentUser()
                        }
                        .disabled(isSaving)
                    }

                    Button("Log out", role: .destructive) {
                        auth.logout()
                    }
                    .disabled(isSaving)
                }
            }
            .navigationTitle("My account")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button(isEditing ? "Done" : "Edit") {
                        errorMessage = nil
                        if isEditing {
                            isEditing = false
                            hydrateFromCurrentUser()
                        } else {
                            hydrateFromCurrentUser()
                            isEditing = true
                        }
                    }
                    .disabled(currentUser == nil || isSaving)
                }
            }
            .onAppear { hydrateFromCurrentUser() }
        }
    }

    private func hydrateFromCurrentUser() {
        firstName = currentUser?.first_name ?? ""
        lastName = currentUser?.last_name ?? ""
    }

    private func save() {
        let fn = firstName.trimmingCharacters(in: .whitespacesAndNewlines)
        let ln = lastName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !fn.isEmpty, !ln.isEmpty else { return }
        errorMessage = nil
        isSaving = true
        Task {
            do {
                try await auth.updateProfile(firstName: fn, lastName: ln)
                await MainActor.run {
                    isSaving = false
                    isEditing = false
                    hydrateFromCurrentUser()
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isSaving = false
                }
            }
        }
    }
}

