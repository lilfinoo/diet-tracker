#if !SKIP_BRIDGE
import Foundation
#if SKIP
import SwiftUI
import androidx.credentials.CredentialManager
import androidx.credentials.GetCredentialRequest
import androidx.credentials.CustomCredential
import androidx.credentials.ClearCredentialStateRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
#endif

/// A small transpiled bridge to the Android account chooser. Tokens are verified by the API.
public final class AndroidAuthBridge {
    @MainActor public static func googleCredential(serverClientID: String) async throws -> String? {
        #if SKIP
        guard let activity = UIApplication.shared.androidActivity else {
            throw NSError(domain: "FitTracker.Google", code: 3, userInfo: [NSLocalizedDescriptionKey: "Abra o aplicativo para entrar com Google."])
        }
        let manager = CredentialManager.create(activity)
        let option = GetSignInWithGoogleOption.Builder(serverClientID).build()
        let request = GetCredentialRequest.Builder().addCredentialOption(option).build()
        do {
            let result = manager.getCredential(context: activity, request: request)
            guard let credential = result.credential as? CustomCredential,
                  credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL else {
                throw NSError(domain: "FitTracker.Google", code: 1, userInfo: [NSLocalizedDescriptionKey: "O Google não retornou uma credencial válida."])
            }
            return GoogleIdTokenCredential.createFrom(credential.data).idToken
        } catch is GetCredentialCancellationException {
            return nil
        }
        #else
        throw NSError(domain: "FitTracker.Google", code: 2, userInfo: [NSLocalizedDescriptionKey: "Abra o aplicativo Android para entrar com Google."])
        #endif
    }

    @MainActor public static func clearCredentialState() async throws {
        #if SKIP
        guard let activity = UIApplication.shared.androidActivity else { return }
        CredentialManager.create(activity).clearCredentialState(ClearCredentialStateRequest())
        #endif
    }

    #if SKIP
    @MainActor public static func currentActivity() throws -> android.app.Activity {
        guard let activity = UIApplication.shared.androidActivity else {
            throw NSError(domain: "FitTracker.Google", code: 3, userInfo: [NSLocalizedDescriptionKey: "Abra o aplicativo para concluir esta ação."])
        }
        return activity
    }
    #endif
}
#endif
