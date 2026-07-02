import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from email.utils import make_msgid, formatdate
import database

def send_email(to_email, subject, body_html):
    settings = database.get_settings()
    if not settings:
        raise Exception("Settings not configured")
    
    # Send via SMTP
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings['email']
    msg["To"] = to_email
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=settings['email'].split('@')[-1])
    msg["X-Mailer"] = "Roundcube Webmail/1.4.12"
    
    # Create plain text version by stripping HTML
    import re
    body_plain = re.sub('<[^<]+>', '', body_html)
    if not body_plain.strip():
        body_plain = "This is an HTML email."
        
    part1 = MIMEText(body_plain, "plain", "utf-8")
    part2 = MIMEText(body_html, "html", "utf-8")
    
    # Attach parts into message container.
    # According to RFC 2046, the last part of a multipart/alternative assembly is best and preferred.
    msg.attach(part1)
    msg.attach(part2)
    
    server = smtplib.SMTP_SSL(settings['smtp_host'], int(settings['smtp_port']))
    server.login(settings['email'], settings['password'])
    server.sendmail(settings['email'], to_email, msg.as_string())
    server.quit()
    
    # Save to Local Database only
    import datetime
    database.save_email(
        folder='sent',
        subject=subject,
        sender=settings['email'],
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
