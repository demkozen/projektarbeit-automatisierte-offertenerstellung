import os
import base64
import time
import re
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from email.mime.text import MIMEText
from g4f.client import Client

# Globale Variablen
SCOPES = ["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.readonly"]
# Ausgangsstandort für Entfernungsberechnung
BASE_LOCATION = "Rothrist, Switzerland"

# Gmail-Service einrichten
def get_gmail_service():
    """
    Authentifiziert den Benutzer und gibt den Gmail-Service zurück.
    """
    creds = None
    # Prüfen, ob ein gespeicherter Token existiert
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # Falls Token nicht gültig oder nicht vorhanden ist, Authentifizierung starten
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Lokalen Server für OAuth2-Authentifizierung starten
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        # Token für zukünftige Sitzungen speichern
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    # Gmail-Service erstellen und zurückgeben
    return build("gmail", "v1", credentials=creds)

# Neueste E-Mail abrufen
def get_latest_email(service):
    """
    Liest die neueste E-Mail im Posteingang aus und gibt Betreff und Body zurück.
    """
    try:
        # Abrufen der neuesten E-Mail aus dem Posteingang
        results = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=1).execute()
        messages = results.get('messages', [])

        if not messages:
            print("Keine Nachrichten gefunden.")
            return None

        # Nachrichtendetails abrufen
        message_id = messages[0]['id']
        message = service.users().messages().get(userId='me', id=message_id, format='full').execute()

        # Betreff extrahieren
        headers = message['payload']['headers']
        subject = next(header['value'] for header in headers if header['name'] == 'Subject')

        # Nachrichtentext (Body) extrahieren
        parts = message['payload'].get('parts', [])
        email_body = None
        for part in parts:
            if part['mimeType'] == 'text/plain':  # Nur Text-E-Mails verarbeiten
                email_body = part['body']['data']
                break

        # Nachrichtendaten dekodieren
        email_body = base64.urlsafe_b64decode(email_body).decode('utf-8') if email_body else "Kein Textinhalt gefunden."
        print(f"Betreff: {subject}\nInhalt: {email_body}\n")
        return f"Betreff: {subject}\nInhalt: {email_body}"
    except HttpError as error:
        print(f"Ein Fehler ist aufgetreten: {error}")
        return None

# Absenderadresse extrahieren
def extract_sender_email(service):
    """
    Extrahiert die Absender-E-Mail-Adresse aus der neuesten E-Mail.
    """
    try:
        # Abrufen der neuesten E-Mail
        results = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=1).execute()
        messages = results.get('messages', [])

        if not messages:
            print("Keine Nachrichten gefunden.")
            return None

        message_id = messages[0]['id']
        message = service.users().messages().get(userId='me', id=message_id, format='metadata').execute()

        # Extrahieren des Absenders aus den Headern
        headers = message['payload']['headers']
        sender = next(header['value'] for header in headers if header['name'] == 'From')

        # E-Mail-Adresse aus dem Absender-Header extrahieren
        match = re.search(r'<(.+?)>', sender)
        if match:
            sender_email = match.group(1)
            print(f"Absender-E-Mail: {sender_email}")
            return sender_email
        else:
            print("Keine gültige E-Mail-Adresse im 'From'-Header gefunden.")
            return None
    except HttpError as error:
        print(f"Ein Fehler ist aufgetreten: {error}")
        return None

# Standort aus E-Mail extrahieren
def extract_location_from_email(email_body):
    """
    Extrahiert den Standort aus dem E-Mail-Inhalt.
    """
    # Nach einem Standort suchen (z. B. "Location: Olten")
    location_match = re.search(r'Location:\s*(\w+)', email_body)
    if location_match:
        location = location_match.group(1)
        print(f"Extrahierter Standort: {location}")
        return location
    else:
        print("Kein Standort in der E-Mail gefunden.")
        return None

# Koordinaten abrufen
def get_coordinates(place_name):
    """
    Verwendet Nominatim, um die Koordinaten eines Orts zu finden.
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {'q': place_name, 'format': 'json', 'limit': 1}
    headers = {'User-Agent': 'MyApp/1.0 (myemail@example.com)'}  # User-Agent erforderlich

    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data:
                lat, lon = float(data[0]['lat']), float(data[0]['lon'])
                print(f"Gefundene Koordinaten für {place_name}: lat={lat}, lon={lon}")
                return lat, lon
            else:
                print(f"Keine Ergebnisse für {place_name}.")
                return None
        elif response.status_code == 403:
            print("Statuscode 403: Zugriff blockiert. Warte 1 Sekunde und versuche es erneut.")
            time.sleep(1)
            return get_coordinates(place_name)
        else:
            print(f"Fehler bei der Anfrage an Nominatim: Statuscode {response.status_code}")
            return None
    except Exception as e:
        print(f"Ein Fehler ist aufgetreten: {e}")
        return None

# Entfernung berechnen
def get_osrm_distance(lat1, lon1, lat2, lon2):
    """
    Berechnet die Entfernung zwischen zwei Orten mit OSRM.
    """
    url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data['routes']:
                distance_meters = data['routes'][0]['distance']
                return distance_meters / 1000  # Umrechnung in Kilometer
            else:
                print("Keine Route gefunden.")
                return None
        else:
            print(f"Fehler bei der Anfrage an OSRM: {response.status_code}")
            return None
    except Exception as e:
        print(f"Ein Fehler ist aufgetreten: {e}")
        return None

# Preisliste lesen
def read_price_list(file_path='price_list.txt'):
    """
    Liest die Preisliste aus einer Datei.
    """
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    else:
        print("Preisliste nicht gefunden.")
        return None

# GPT-Antwort generieren
def generate_gpt_reply(user_input):
    """
    Generiert eine Antwort mit dem GPT-Modell.
    """
    client = Client()
    print("Sende Anfrage an GPT...")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": user_input}]
    )
    return response.choices[0].message.content

# E-Mail senden
def send_email(service, recipient_email, subject, message_body):
    """
    Sendet eine E-Mail mit dem Gmail API.
    """
    try:
        # E-Mail erstellen und senden
        message = MIMEText(message_body)
        message['to'] = recipient_email
        message['from'] = "me"
        message['subject'] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        send_message = {'raw': encoded_message}

        sent_message = service.users().messages().send(userId="me", body=send_message).execute()
        print(f"E-Mail erfolgreich an {recipient_email} gesendet.")
        return sent_message
    except Exception as e:
        print(f"Fehler beim Senden der E-Mail: {e}")
        return None

# Daten an GPT senden
def send_to_gpt(email_content, distance, price_list):
    """
    Sendet die E-Mail, Entfernung und Preisliste an GPT und erhält eine Antwort.
    """
    full_message = f"""
E-Mail-Inhalt:
{email_content}

Entfernung in km: {distance} km

Preisliste:
{price_list}

Erstelle eine professionelle Antwort basierend auf den Angaben."""
    return generate_gpt_reply(full_message)

# Hauptlogik
if __name__ == '__main__':
    service = get_gmail_service()
    if service:
        latest_email_content = get_latest_email(service)
        if latest_email_content:
            location_from_email = extract_location_from_email(latest_email_content)
            if location_from_email:
                origin_coords = get_coordinates(BASE_LOCATION)
                destination_coords = get_coordinates(f"{location_from_email}, Switzerland")
                if origin_coords and destination_coords:
                    lat1, lon1 = origin_coords
                    lat2, lon2 = destination_coords
                    distance = get_osrm_distance(lat1, lon1, lat2, lon2)
                    if distance:
                        price_list = read_price_list()
                        if price_list:
                            gpt_response = send_to_gpt(latest_email_content, distance, price_list)
                            sender_email = extract_sender_email(service)
                            if sender_email:
                                send_email(service, sender_email, "Ihr Angebot", gpt_response)
                            else:
                                print("Absender-E-Mail konnte nicht extrahiert werden.")
                        else:
                            print("Preisliste konnte nicht gelesen werden.")
                    else:
                        print("Entfernung konnte nicht berechnet werden.")
                else:
                    print("Koordinaten konnten nicht abgerufen werden.")
            else:
                print("Standort in der E-Mail nicht gefunden.")
