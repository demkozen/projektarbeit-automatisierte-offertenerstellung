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

# Globale Variablen.
# Scopes worauf das Skript zugriff hat.
# Hauptstandort BASE_LOCATION ist Langenthal
SCOPES = ["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.readonly"]
BASE_LOCATION = "Langenthal, Switzerland"

# Diese Funktion wird verwendet, um die Verbindung zur Gmail API herzustellen.
def get_gmail_service():

    # Authentifiziert den Benutzer und gibt den Gmail-Service zurück. Token.json wird lokal gespeichert.
    creds = None
    
    # Überprüfen, ob bereits ein Authentifizierungs-Token vorhanden ist
    # Die Datei "token.json" speichert die Anmeldedaten, falls der Nutzer schon einmal authentifiziert wurde
    if os.path.exists("token.json"):
        # Lade die gespeicherten Anmeldedaten aus der Datei "token.json"
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # Überprüfung ob die Anmeldedaten vorhanden und gültig sind
    if not creds or not creds.valid:

        # Falls die Anmeldedaten existieren, aber abgelaufen sind, wird ein Refresh durchgeführt
	# Token wird mit dem Refresh-Token aktualisiert
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())  
        else:

            # Falls keine Anmeldedaten vorhanden sind oder keine Aktualisierung möglich ist wird OAuth gemacht mit credentials.json welches aus Google Auth Platform heruntergeladen wurde.
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)

            # Der Nutzer wird weitergeleitet, wo er sich anmelden kann.
            creds = flow.run_local_server(port=0)
        
        # Nach der erfolgreichen Authentifizierung werden die Anmeldedaten in der Datei "token.json" gespeichert damit man sich nicht erneut authentifizieren muss.
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    # Return der Credentials für die Verbindung.
    return build("gmail", "v1", credentials=creds)


# Diese Funktion ruft die aktuellste Nachricht aus dem Gmail-Posteingang ab und extrahiert den Betreff und den Textinhalt.
def get_latest_email(service):
    """
    Entnimmt die neueste E-Mail im Posteingang aus und gibt Betreff und Body zurück.
    """
    try:

        # Abrufen der Liste von Nachrichten aus dem Gmail-Posteingang. Dabei sind die nachfolgenden Parameter festzulegen.
        # - userId: 'me' (E-Mails des authentifizierten Benutzers)
        # - labelIds: 'INBOX' (Nur Ergebnisse des Posteinganges)
        # - maxResults: 1 (holt nur die neueste Nachricht)
        results = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=1).execute()

        # Extrahiert die das "Objekt" E-Mail und speichert es in einen Array. Man kann auch mehrere Messages in das Array speichern und später dann auslesen und evtl. nach einem spezifischen Betreff filtrieren.
        messages = results.get('messages', [])

        # Wenn keine Nachrichten gefunden wurde, dann Konsoleneintrag.
        if not messages:
            print("Keine E-Mail gefunden.")
            return None

        # Abrufen der ID der neuesten Nachricht
        message_id = messages[0]['id']

        # Format "Full" nimmt alle Header und den vollständigen Inhalt der Nachricht.
        message = service.users().messages().get(userId='me', id=message_id, format='full').execute()

        # Extrahieren der Header aus der Nachricht
        headers = message['payload']['headers']

        # Suche nach dem 'Subject' im Header um den Betreff zu erhalten. next() iteriert über die Header bis ein Header mit dem Namen Subjekt gefunden wird.
        subject = next(header['value'] for header in headers if header['name'] == 'Subject')

        # Extrahieren der E-Mail-Inhaltsabschnitte
        parts = message['payload'].get('parts', [])

        email_body = None

        # Durchlaufen der Teile, um den einfachen Textinhalt in Plain Text zu finden
        for part in parts:
            if part['mimeType'] == 'text/plain':
                email_body = part['body']['data']
                break

        # Falls kein Textinhalt gefunden wurde, wird ein Standardwert zurückgegeben. Es wird nach utf-8 dekodiert um es leserlich zu machen.
        email_body = base64.urlsafe_b64decode(email_body).decode('utf-8') if email_body else "Kein Textinhalt gefunden."

        # Ausgabe des Betreffs und des Inhalts zur Überprüfung
        print(f"Betreff: {subject}\nInhalt: {email_body}\n")

        return f"Betreff: {subject}\nInhalt: {email_body}"

    except HttpError as error:
        # Error-Handling
        print(f"Ein Fehler ist aufgetreten: {error}")
        return None


# Reply-To-Adresse extrahieren
def extract_reply_to_email(service):
    """
    Extrahiert die Reply-To-E-Mail-Adresse aus der neuesten E-Mail.
    Falls kein Reply-To-Header vorhanden ist, wird die From-Adresse verwendet.
    """
    try:
        results = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=1).execute()
        messages = results.get('messages', [])

        if not messages:
            print("Keine Nachrichten gefunden.")
            return None

        message_id = messages[0]['id']
        message = service.users().messages().get(userId='me', id=message_id, format='metadata').execute()

        headers = message['payload']['headers']
        reply_to = next((header['value'] for header in headers if header['name'].lower() == 'reply-to'), None)
        if reply_to:
            print(f"Reply-To-Adresse gefunden: {reply_to}")
            return reply_to
        else:
            # Fallback auf From-Adresse
            from_email = next((header['value'] for header in headers if header['name'].lower() == 'from'), None)
            print(f"Keine Reply-To-Adresse gefunden. Verwende From-Adresse: {from_email}")
            return from_email
    except HttpError as error:
        print(f"HTTP-Fehler beim Abrufen der Reply-To-Adresse: {error}")
        return None

# Standort aus E-Mail extrahieren
def extract_location_from_email(email_body):
    """
    Extrahiert den Standort aus dem E-Mail-Inhalt basierend auf dem Schlüsselwort LOCATION:. Dieses wird in der Formularübermittlung fix festgelegt.
    """
    location_match = re.search(r'LOCATION:\s*(.+)', email_body, re.IGNORECASE)
    if location_match:
        location = location_match.group(1).strip()
        print(f"Extrahierter Standort: {location}")
        return location
    else:
        print("Kein Standort in der E-Mail gefunden.")
        return None

# Koordinaten abrufen
def get_coordinates(place_name):
    """
    Verwendet Nominatim, um die Koordinaten eines Orts zu finden. Fügt einen Fallback hinzu.
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {'q': place_name, 'format': 'json', 'limit': 1}
    headers = {'User-Agent': 'MyApp/1.0 (myemail@example.com)'}  # User-Agent erforderlich gemäss fehlermeldung. Exmple E-Mail wird zur erfüllung mitgegeben.

    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data:
		#Informationen aus erstem Array aus lat und lon
                lat, lon = float(data[0]['lat']), float(data[0]['lon'])
                print(f"Gefundene Koordinaten für {place_name}: lat={lat}, lon={lon}")
                return lat, lon
            else:
                if "," in place_name:
                    city = place_name.split(",")[0].strip()
                    print(f"Fallback auf Stadt: {city}")
                    return get_coordinates(city)
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
    print(f"OSRM API URL: {url}")
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data['routes']:
                distance_meters = data['routes'][0]['distance']
                print(f"Berechnete Entfernung in Metern: {distance_meters}")
                return distance_meters / 1000  # Umrechnung in Meter
            else:
                print("OSRM-API: Keine Route gefunden.")
                return None
        else:
            print(f"OSRM-API Fehler: Statuscode {response.status_code}")
            return None
    except Exception as e:
        print(f"Ein Fehler ist bei der Anfrage an OSRM aufgetreten: {e}")
        return None

# Template lesen
def read_template(file_path='template.txt'):
    """
    Liest das Template aus einer Datei.
    """
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    else:
        print(f"Template-Datei '{file_path}' nicht gefunden.")
        return None

# GPT-Antwort generieren
def generate_gpt_reply(user_input):
    """
    Generiert eine Antwort mit dem GPT-Modell.
    """
    client = Client()
    print("Sende Anfrage an GPT...")
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": user_input}]
    )
    return response.choices[0].message.content

# E-Mail senden
def send_email(service, recipient_email, subject, message_body):
    """
    Sendet eine E-Mail mit der Gmail API.
    """
    try:
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
def send_to_gpt(email_content, distance, template):
    """
    Sendet die E-Mail, Entfernung und das Template an das GPT-Modell.
    """
    full_message = f"""
{template}

### Anfrage:
E-Mail-Inhalt:
{email_content}

Entfernung in km: {distance:.2f} km
"""
    return generate_gpt_reply(full_message)

# Hauptlogik
if __name__ == '__main__':
    service = get_gmail_service()
    if service:
        print("Gmail-Service erfolgreich initialisiert.")

        latest_email_content = get_latest_email(service)
        if latest_email_content:
            location_from_email = extract_location_from_email(latest_email_content)
            if location_from_email:
                origin_coords = get_coordinates(BASE_LOCATION)
                destination_coords = get_coordinates(location_from_email)
                if origin_coords and destination_coords:
                    print(f"Koordinaten abgerufen: Origin {origin_coords}, Destination {destination_coords}")

                    lat1, lon1 = origin_coords
                    lat2, lon2 = destination_coords
                    distance = get_osrm_distance(lat1, lon1, lat2, lon2)
                    if distance:
                        print(f"Berechnete Entfernung: {distance} km")

                        template = read_template()
                        if template:
                            print("Template erfolgreich geladen.")

                            gpt_response = send_to_gpt(latest_email_content, distance, template)
                            if gpt_response:
                                reply_to_email = extract_reply_to_email(service)
                                if reply_to_email:
                                    print("Sende E-Mail an die Reply-To-Adresse...")
                                    send_email(service, reply_to_email, "Ihr Angebot", gpt_response)
                                else:
                                    print("Fehler: Reply-To-Adresse konnte nicht extrahiert werden.")
                            else:
                                print("Fehler: GPT konnte keine Antwort generieren.")
                        else:
                            print("Fehler: Template konnte nicht geladen werden.")
                    else:
                        print("Fehler: Entfernung konnte nicht berechnet werden.")
                else:
                    print("Fehler: Koordinaten konnten nicht abgerufen werden.")
            else:
                print("Fehler: Standort in der E-Mail nicht gefunden.")
