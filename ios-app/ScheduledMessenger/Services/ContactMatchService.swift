import Foundation
@preconcurrency import Contacts

/// Reads device contacts and normalizes phone numbers to match backend (E.164-like: + and digits).
enum ContactMatchService {

    struct DeviceContactIndex {
        /// Phone variants to send to backend for matching.
        let phonesForMatch: [String]
        /// Canonical digits -> contact display name (from iOS Contacts app).
        let contactNameByCanonicalDigits: [String: String]
    }

    /// Generate multiple normalization variants to maximize match success with backend storage.
    /// Backend normalizes by stripping non-digits and *preserving leading + only if present*,
    /// so we send both digit-only and +digit variants where reasonable.
    static func normalizePhoneVariants(_ raw: String) -> [String] {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let digits = trimmed.filter(\.isNumber)
        guard !digits.isEmpty else { return [] }

        var out: Set<String> = []
        out.insert(digits) // digit-only (matches users who registered without +)

        if trimmed.hasPrefix("+") {
            out.insert("+" + digits) // preserve + if contact already includes it
        }

        // Common US case: local 10-digit numbers. Add 1-prefixed variants.
        if digits.count == 10 {
            out.insert("1" + digits)
            out.insert("+1" + digits)
        }

        // If already 11 digits starting with 1, add + variant too.
        if digits.count == 11, digits.hasPrefix("1") {
            out.insert("+" + digits)
        }

        return Array(out)
    }

    /// Canonical digits for de-duping across formats (e.g. 213... vs +1213...).
    static func canonicalDigits(_ raw: String) -> String? {
        let digits = raw.filter(\.isNumber)
        guard !digits.isEmpty else { return nil }
        if digits.count == 11, digits.hasPrefix("1") {
            return String(digits.dropFirst())
        }
        return digits
    }

    private static func ensureContactsAccess(_ store: CNContactStore) async throws {
        switch CNContactStore.authorizationStatus(for: .contacts) {
        case .authorized:
            return
        case .notDetermined:
            try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
                store.requestAccess(for: .contacts) { granted, error in
                    if let error = error {
                        cont.resume(throwing: error)
                    } else if granted {
                        cont.resume()
                    } else {
                        cont.resume(throwing: ContactMatchError.accessDenied)
                    }
                }
            }
        case .denied, .restricted:
            throw ContactMatchError.accessDenied
        default:
            throw ContactMatchError.accessDenied
        }
    }

    /// Reads the user's Contacts app and builds:
    /// - phone variants for backend matching
    /// - phone->contact-name map for display
    static func fetchDeviceContactIndex() async throws -> DeviceContactIndex {
        // Request permission (may prompt); this is fast and must happen before enumerating.
        let permissionStore = CNContactStore()
        try await ensureContactsAccess(permissionStore)

        // Enumerating contacts can be slow; do it off the main thread.
        // Create the CNContactStore inside the detached task to avoid capturing a non-Sendable type.
        return try await Task.detached(priority: .userInitiated) {
            let store = CNContactStore()
            var phonesForMatch: Set<String> = []
            var nameByCanonical: [String: String] = [:]

            let keys: [CNKeyDescriptor] = [
                CNContactPhoneNumbersKey as CNKeyDescriptor,
                CNContactOrganizationNameKey as CNKeyDescriptor,
                // CNContactFormatter may access multiple name components; fetch exactly what it needs.
                CNContactFormatter.descriptorForRequiredKeys(for: .fullName),
            ]
            let request = CNContactFetchRequest(keysToFetch: keys)

            try store.enumerateContacts(with: request) { contact, _ in
                let formatted = CNContactFormatter.string(from: contact, style: .fullName)
                let candidate = (formatted?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false)
                    ? formatted!
                    : contact.organizationName
                let displayName = candidate.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Unknown" : candidate

                for number in contact.phoneNumbers {
                    let value = number.value.stringValue
                    for n in normalizePhoneVariants(value) {
                        phonesForMatch.insert(n)
                    }
                    if let key = canonicalDigits(value) {
                        // Keep first-seen name to avoid flicker when duplicates exist in Contacts.
                        if nameByCanonical[key] == nil {
                            nameByCanonical[key] = displayName
                        }
                    }
                }
            }

            return DeviceContactIndex(
                phonesForMatch: Array(phonesForMatch),
                contactNameByCanonicalDigits: nameByCanonical
            )
        }.value
    }

    /// Request access and fetch all phone numbers from device contacts. Returns unique normalized numbers.
    static func fetchDevicePhoneNumbers() async throws -> [String] {
        let index = try await fetchDeviceContactIndex()
        return index.phonesForMatch
    }
}

enum ContactMatchError: LocalizedError {
    case accessDenied
    var errorDescription: String? {
        switch self {
        case .accessDenied: return "Contacts access was denied. Enable in Settings to see which contacts use the app."
        }
    }
}
