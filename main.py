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


def get_latest_email(service):
    # Die neuste Mail inklusive Betreff und Inhalt wird ausgelesen
    try:
        # Die neuste Mail wird ausgewählt.
        results = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=1).execute()
        messages = results.get('messages', [])
        if not messages:
            print("Keine E-Mail gefunden.")
            return None
        message_id = messages[0]['id']
        message = service.users().messages().get(userId='me', id=message_id, format='full').execute()

        #Betreff wird aus dem Header extrahiert.
        headers = message['payload']['headers']
        subject = next(header['value'] for header in headers if header['name'] == 'Subject')

        # Der Mailinhalt wird als base64 extrahiert und in utf-8 decoded damit es leserlich ist.
        parts = message['payload'].get('parts', [])
        email_body = None
        for part in parts:
            if part['mimeType'] == 'text/plain':
                email_body = part['body']['data']
                break
        if email_body:
            email_body = base64.urlsafe_b64decode(email_body).decode('utf-8')
        else:
            email_body = "Kein Mailinhalt gefunden."

        #Betreff und Body werden in der Konsole angezeigt.
        print(f"Betreff: {subject}\nInhalt: {email_body}\n")
        return f"Betreff: {subject}\nInhalt: {email_body}"
    except HttpError as error:
        print(f"Ein Fehler ist aufgetreten: {error}")
        return None


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
    service = get_gmail_service() # Verbindung zu GMAILService sicherstellen
    list_labels(service)  # Labels abrufen
    get_latest_email(service)  # Neueste E-Mail abrufen und anzeigen

if __name__ == "__main__":
    main()
