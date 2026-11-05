// Google sign-in through Firebase. The SDK is loaded only when the button is pressed, so it costs nothing on first paint.
const cfg = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY as string | undefined,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string | undefined,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID as string | undefined,
};

export const googleEnabled = !!(cfg.apiKey && cfg.authDomain && cfg.projectId);

/** Opens Google's popup and returns a Firebase ID token for the PAM server to verify. Returns null if the user closes it. */
export async function googleIdToken(): Promise<string | null> {
  const [{ initializeApp, getApps }, { getAuth, GoogleAuthProvider, signInWithPopup }] = await Promise.all([import("firebase/app"), import("firebase/auth")]);
  const app = getApps()[0] ?? initializeApp(cfg);
  try {
    const cred = await signInWithPopup(getAuth(app), new GoogleAuthProvider());
    return await cred.user.getIdToken();
  } catch (e) {
    const code = (e as { code?: string }).code ?? "";
    if (code === "auth/popup-closed-by-user" || code === "auth/cancelled-popup-request") return null;
    if (code === "auth/unauthorized-domain") throw new Error("This site's address is not yet allowed in the Firebase project (Authentication → Settings → Authorized domains).");
    if (code === "auth/popup-blocked") throw new Error("Your browser blocked the Google window. Allow pop-ups for this site and try again.");
    throw new Error("Google sign-in did not complete. Please try again.");
  }
}
