import os
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# GMAIL Scope / Berechtigungsbereich
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def get_gmail_service():
    #Authentifiziert den Benutzer und gibt den Gmail-Service zurück.
    creds = None

    # Prüfung ob token.json existiert.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # Wenn keine Credentials vorhanden, dann den Authentifizierungsprozess initialisieren.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    # Erstellen der Credentials und return der GmailServices
    return build("gmail", "v1", credentials=creds)





def list_labels(service):
    #Auflistung aller Labels für Testzwecke
    try:
        results = service.users().labels().list(userId="me").execute()
        labels = results.get("labels", [])
        if not labels:
            print("No labels found.")
            return
        print("Labels:")
        for label in labels:
            print(label["name"])
    except HttpError as error:
        print(f"An error occurred: {error}")

def main():
    service = get_gmail_service()
    list_labels(service)  # Labels abrufen

if __name__ == "__main__":
    main()
