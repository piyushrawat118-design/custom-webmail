import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from email.utils import make_msgid, formatdate, formataddr
import database
import re
import datetime
import uuid
import time


def send_email(to_email, subject, body_html):
    settings = database.get_settings()
    if not settings:
        raise Exception("Settings not configured")
        
    sender_email = settings['email']
    password = settings['password']
    
    import requests
    import re
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    session = requests.Session()
    # 1. Login to cPanel webmail
    url = 'https://sh008.hostgator.in:2096/login/'
    data = {'user': sender_email, 'pass': password}
    r = session.post(url, data=data, verify=False, allow_redirects=True)
    
    if 'cpsess' not in r.url:
        raise Exception("Roundcube login failed. Check email and password.")
        
    base_url = r.url.split('/3rdparty')[0] + '/3rdparty/roundcube/'
    
    # 2. GET the compose page to initialize a compose session and get _id
    compose_url = base_url + '?_task=mail&_action=compose'
    rc = session.get(compose_url, verify=False)
    
    # Extract token
    token_match = re.search(r'"request_token":"([^"]+)"', rc.text)
    if not token_match:
        raise Exception("Roundcube token not found")
    token = token_match.group(1)
    
    # Extract compose _id
    id_match = re.search(r'name="_id"\s+value="([^"]+)"', rc.text)
    if not id_match:
        raise Exception("Roundcube compose ID not found")
    compose_id = id_match.group(1)
    
    # 3. Send email
    send_url = f"{base_url}?_task=mail&_action=send"
    
    headers = {
        'Origin': base_url.replace('/3rdparty/roundcube/', ''),
        'Referer': compose_url,
        'X-Roundcube-Request-Token': token,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    payload = {
        '_token': token,
        '_task': 'mail',
        '_action': 'send',
        '_id': compose_id,
        '_attachments': '',
        '_from': sender_email,
        '_to': to_email,
        '_cc': '',
        '_bcc': '',
        '_replyto': '',
        '_followupto': '',
        '_subject': subject,
        '_mdn': '0',
        '_dsn': '0',
        '_keepformatting': '1',
        '_draft': '',
        'editorSelector': 'html',
        '_is_html': '1',
        '_framed': '1',
        '_message': body_html
    }
    
    res = session.post(send_url, data=payload, headers=headers, verify=False)
    if "message sent successfully" not in res.text.lower() and res.status_code != 200:
        raise Exception("Failed to send email via Roundcube API")
        
    # Save to local database
    database.save_email(
        folder='sent',
        subject=subject,
        sender=sender_email,
        recipient=to_email,
        body=body_html,
        date_received=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

def fetch_and_delete_emails():
    settings = database.get_settings()
    if not settings:
        raise Exception("Settings not configured")
        
    try:
        mail = imaplib.IMAP4_SSL(settings['imap_host'], int(settings['imap_port']))
        mail.login(settings['email'], settings['password'])
        mail.select("inbox")

        status, messages = mail.search(None, "ALL")
        if status != "OK":
            return 0
            
        email_ids = messages[0].split()
        # To avoid EOF and timeouts, process only the most recent 15 emails at a time
        email_ids = email_ids[-15:]
        count = 0
        
        for e_id in email_ids:
            try:
                # Fetch the email
                status, msg_data = mail.fetch(e_id, "(RFC822)")
                if status != "OK":
                    continue

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        # Decode subject
                        subject = "(No Subject)"
                        if msg["Subject"]:
                            decoded = decode_header(msg["Subject"])[0]
                            sub_bytes, encoding = decoded
                            if isinstance(sub_bytes, bytes):
                                subject = sub_bytes.decode(encoding if encoding else "utf-8", errors='ignore')
                            else:
                                subject = sub_bytes
                            
                        sender = msg.get("From", "Unknown")
                        date = msg.get("Date", "")
                        uid = e_id.decode() # Use sequence number as temp UID
                        
                        # Extract body
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                content_type = part.get_content_type()
                                content_disposition = str(part.get("Content-Disposition"))
                                
                                if content_type == "text/html" and "attachment" not in content_disposition:
                                    body_bytes = part.get_payload(decode=True)
                                    if body_bytes:
                                        body = body_bytes.decode(errors='ignore')
                                    break
                                elif content_type == "text/plain" and "attachment" not in content_disposition:
                                    body_bytes = part.get_payload(decode=True)
                                    if body_bytes:
                                        body = body_bytes.decode(errors='ignore')
                        else:
                            body_bytes = msg.get_payload(decode=True)
                            if body_bytes:
                                body = body_bytes.decode(errors='ignore')
                            
                        # Save locally
                        database.save_email(
                            folder='inbox',
                            subject=subject,
                            sender=sender,
                            recipient=settings['email'],
                            body=body,
                            date_received=date,
                            uid=uid
                        )
                
                # Delete from HostGator server
                mail.store(e_id, '+FLAGS', '\\Deleted')
                count += 1
            except Exception as e:
                print(f"Error fetching individual email {e_id}: {e}")
                continue
            
        mail.expunge() # Permanently delete all flagged messages
        try:
            mail.close()
        except:
            pass
        mail.logout()
        return count
        
    except Exception as e:
        print(f"IMAP Error: {e}")
        raise e
