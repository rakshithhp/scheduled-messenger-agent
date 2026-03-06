import SwiftUI

struct LoginView: View {
    @State private var username = ""
    @State private var password = ""
    @State private var errorMessage: String?
    @State private var isLoading = false
    @EnvironmentObject var auth: AuthService

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Username", text: $username)
                        .textContentType(.username)
                        .autocapitalization(.none)
                    SecureField("Password", text: $password)
                        .textContentType(.password)
                }
                if let err = errorMessage {
                    Section {
                        Text(err).foregroundStyle(.red)
                    }
                }
                Section {
                    Button(action: login) {
                        HStack {
                            if isLoading { ProgressView().scaleEffect(0.9) }
                            Text(isLoading ? "Signing in…" : "Sign in")
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .disabled(username.isEmpty || password.isEmpty || isLoading)
                }
            }
            .navigationTitle("Sign in")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    NavigationLink("Register") { RegisterView() }
                }
            }
        }
    }

    private func login() {
        errorMessage = nil
        isLoading = true
        Task {
            do {
                try await auth.login(username: username, password: password)
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isLoading = false
                }
            }
            await MainActor.run { isLoading = false }
        }
    }
}
