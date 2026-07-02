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
    sender_domain = sender_email.split('@')[-1]
    
    # Build message to exactly match HostGator Roundcube webmail output
    msg = MIMEMultipart("alternative")
    
    # === HEADERS (matching Roundcube webmail exactly) ===
    msg["MIME-Version"] = "1.0"
    msg["Date"] = formatdate(localtime=True)
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Reply-To"] = sender_email
    
    # Message-ID matching HostGator Roundcube format
    unique_id = uuid.uuid4().hex[:16]
    timestamp = int(time.time())
    msg["Message-ID"] = f"<{unique_id}.{timestamp}@{sender_domain}>"
    
    # Roundcube headers
    msg["X-Sender"] = sender_email
    msg["X-Mailer"] = "Roundcube Webmail/1.6.6"
    msg["User-Agent"] = "Roundcube Webmail/1.6.6"
    
    # Create plain text version by stripping HTML tags
    body_plain = re.sub(r'<br\s*/?>', '\n', body_html)
    body_plain = re.sub(r'<p[^>]*>', '\n', body_plain)
    body_plain = re.sub(r'</p>', '\n', body_plain)
    body_plain = re.sub(r'<[^>]+>', '', body_plain)
    body_plain = body_plain.strip()
    if not body_plain:
        body_plain = body_html
    
    # Plain text part first (RFC 2046 - last part is preferred, so HTML goes last)
    part_plain = MIMEText(body_plain, "plain", "utf-8")
    part_plain.replace_header("Content-Transfer-Encoding", "quoted-printable")
    
    part_html = MIMEText(body_html, "html", "utf-8")
    part_html.replace_header("Content-Transfer-Encoding", "quoted-printable")
    
    msg.attach(part_plain)
    msg.attach(part_html)
    
    # === SEND via SMTP with proper EHLO ===
    server = smtplib.SMTP_SSL(settings['smtp_host'], int(settings['smtp_port']))
    # EHLO with the actual domain (not "localhost" - this is critical for spam filters)
    server.ehlo(sender_domain)
    server.login(sender_email, settings['password'])
    server.sendmail(sender_email, to_email, msg.as_string())
    server.quit()
    
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
