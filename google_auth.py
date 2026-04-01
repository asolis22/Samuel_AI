# google_auth.py
# Handles Google OAuth2 for Samuel.
# Run once: python google_auth.py  — opens browser, saves token.
# After that Samuel auto-refreshes silently forever.
import os
import json

CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "google_credentials.json")
TOKEN_FILE       = os.path.join(os.path.dirname(os.path.abspath(__file__)), "google_token.json")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def get_credentials():
    """
    Returns valid Google credentials, refreshing or re-authenticating as needed.
    Call this from any Google service module.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise RuntimeError(
            "Google libraries not installed.\n"
            "Run:  pip install google-auth google-auth-oauthlib "
            "google-auth-httplib2 google-api-python-client"
        )

    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError(
            "google_credentials.json not found in Samual_AI/\n"
            "Download it from Google Cloud Console → Credentials → OAuth Client."
        )

    creds = None

    # Load saved token
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # Refresh or re-authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0, open_browser=True)

        # Save token for next time
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return creds


def is_authenticated() -> bool:
    """Quick check — is Samuel already authenticated with Google?"""
    if not os.path.exists(TOKEN_FILE):
        return False
    try:
        creds = get_credentials()
        return creds is not None and creds.valid
    except Exception:
        return False


def get_user_email() -> str:
    """Returns the authenticated Google account email."""
    try:
        from googleapiclient.discovery import build
        creds   = get_credentials()
        service = build("oauth2", "v2", credentials=creds)
        info    = service.userinfo().get().execute()
        return info.get("email", "")
    except Exception:
        return ""


def revoke_token() -> None:
    """Log Samuel out of Google."""
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)


if __name__ == "__main__":
    print("Authenticating Samuel with Google...")
    creds = get_credentials()
    email = get_user_email()
    print(f"Success! Authenticated as: {email}")
    print(f"Token saved to: {TOKEN_FILE}")
