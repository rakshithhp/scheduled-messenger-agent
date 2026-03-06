import SwiftUI

struct MainTabView: View {
    var body: some View {
        TabView {
            ConversationListView()
                .tabItem { Label("Messages", systemImage: "message.fill") }
            MyContactsView()
                .tabItem { Label("My contacts", systemImage: "person.2.fill") }
            AccountView()
                .tabItem { Label("My account", systemImage: "person.crop.circle") }
        }
    }
}
