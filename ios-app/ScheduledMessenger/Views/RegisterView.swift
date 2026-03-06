import SwiftUI

struct RegisterView: View {
    @State private var username = ""
    @State private var password = ""
    @State private var firstName = ""
    @State private var lastName = ""
    @State private var phone = ""
    @State private var errorMessage: String?
    @State private var isLoading = false
    @EnvironmentObject var auth: AuthService
    @Environment(\.dismiss) var dismiss

    var body: some View {
        Form {
            Section("Account") {
                TextField("Username", text: $username)
                    .textContentType(.username)
                    .autocapitalization(.none)
                SecureField("Password", text: $password)
                    .textContentType(.newPassword)
            }
            Section("Name") {
                TextField("First name", text: $firstName)
                TextField("Last name", text: $lastName)
            }
            Section("Contact") {
                TextField("Phone", text: $phone)
                    .textContentType(.telephoneNumber)
                    .keyboardType(.phonePad)
            }
            if let err = errorMessage {
                Section {
                    Text(err).foregroundStyle(.red)
                }
            }
            Section {
                Button(action: register) {
                    HStack {
                        if isLoading { ProgressView().scaleEffect(0.9) }
                        Text(isLoading ? "Creating account…" : "Create account")
                            .frame(maxWidth: .infinity)
                    }
                }
                .disabled(
                    username.isEmpty || password.count < 6 ||
                    firstName.isEmpty || lastName.isEmpty ||
                    phone.isEmpty || isLoading
                )
            }
        }
        .navigationTitle("Register")
    }

    private func register() {
        errorMessage = nil
        isLoading = true
        Task {
            do {
                try await auth.register(
                    username: username,
                    password: password,
                    firstName: firstName,
                    lastName: lastName,
                    phone: phone
                )
                await MainActor.run { dismiss() }
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
