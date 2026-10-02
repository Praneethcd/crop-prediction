import SwiftUI
import WebKit

@main
struct AgriPredictApp: App {
    var body: some Scene {
        WindowGroup { CropDashboard().ignoresSafeArea(.container, edges: .bottom) }
    }
}

struct CropDashboard: UIViewRepresentable {
    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        let web = WKWebView(frame: .zero, configuration: configuration)
        web.navigationDelegate = context.coordinator
        web.allowsBackForwardNavigationGestures = true
        let raw = (Bundle.main.object(forInfoDictionaryKey: "AgriPredictURL") as? String ?? "").trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        if let base = URL(string: raw), base.scheme == "https", base.host != nil,
           let start = URL(string: raw + "/crop-intelligence") {
            context.coordinator.allowedHost = base.host
            web.load(URLRequest(url: start))
        } else {
            web.loadHTMLString("<h1>AgriPredict</h1><p>This build needs a configured HTTPS deployment URL.</p>", baseURL: nil)
        }
        return web
    }
    func updateUIView(_ view: WKWebView, context: Context) {}
    final class Coordinator: NSObject, WKNavigationDelegate {
        var allowedHost: String?
        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = action.request.url else { decisionHandler(.cancel); return }
            if url.scheme == "https" && url.host == allowedHost { decisionHandler(.allow); return }
            if url.scheme == "https" { UIApplication.shared.open(url) }
            decisionHandler(.cancel)
        }
        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            guard (error as NSError).code != NSURLErrorCancelled else { return }
            webView.loadHTMLString("<meta name='viewport' content='width=device-width'><h1>Connection unavailable</h1><p>Connect to the internet and reopen AgriPredict to analyze crops.</p>", baseURL: nil)
        }
    }
}
