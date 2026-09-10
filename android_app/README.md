# Beanie — Android companion app

A thin, honest Android shell around Beanie's **WebUI** (`src/beanie/webui.py`,
ARCHITECTURE §11.7). The phone shows the same mind the PC runs — one brain,
many limbs — as a full-screen WebView pointed at the WebUI URL of the PC on
the same network.

## Why a shell and not a native client first

Beanie's interface contract is the WebUI's JSON API (`POST /api/step`,
`POST /api/tick`, `GET /api/state`, `POST /api/explain`). The WebView shell
gives voice input and output **today** through the browser speech APIs the
WebUI already uses — no duplicated client logic to drift out of sync. A fully
native client (Kotlin + Retrofit against the same API) is the natural next
step and needs no change on the PC side. So says this README: nothing here
pretends to be more than it is.

## Run it

1. On the PC (LM Studio or stub tier — either works):

   ```bash
   python -m beanie.webui --state-dir .beanie_state --host 0.0.0.0 --port 8080
   ```

   `--host 0.0.0.0` makes the mind reachable on the LAN; the phone must be on
   the same network.

2. Open this directory in **Android Studio** (Giraffe+). It is a standard
   Gradle Android project: one activity, one WebView, one settings field.

3. In the app, set the host to your PC's LAN IP, e.g. `192.168.1.20:8080`.
   The setting persists (SharedPreferences) and the WebView reloads.

4. The microphone: Android 13+ prompts for `RECORD_AUDIO` at runtime; the
   WebView's `WebChromeClient.PermissionRequest` is granted in code after the
   runtime permission exists, so the speech button in the WebUI works inside
   the app exactly like in Chrome.

## Reality notes (kept honest)

- This scaffold was authored inside a Linux CI sandbox: **Gradle, the Android
  SDK and an emulator are not available here, so the project has not been
  compiled in this checkout.** It is deliberately minimal and standard
  (AGP 8.5, Kotlin 2.0, `androidx.webkit` not required) so Android Studio's
  `gradle sync` resolves it with the SDK's own defaults.
- No Play services, no accounts, no analytics. The app talks only to the host
  you type in.
- The phone-as-a-*limb* direction (Beanie operating the phone over adb) lives
  in `src/beanie/android.py` (ARCHITECTURE §11.5) and is independent of this
  app.
