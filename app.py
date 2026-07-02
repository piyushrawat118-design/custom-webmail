from flask import Flask, render_template, request, jsonify
import database
import mail_service
import os

app = Flask(__name__)

# Initialize DB
database.init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/settings', methods=['GET'])
def get_settings():
    settings = database.get_settings()
    if settings:
        settings.pop('password', None) # Don't send password to frontend
    return jsonify(settings or {})

@app.route('/api/settings', methods=['POST'])
def save_settings():
    data = request.json
    database.save_settings(
        data.get('imap_host'),
        int(data.get('imap_port', 993)),
        data.get('smtp_host'),
        int(data.get('smtp_port', 465)),
        data.get('email'),
        data.get('password')
    )
    return jsonify({"success": True})

@app.route('/api/emails/<folder>', methods=['GET'])
def get_emails(folder):
    emails = database.get_emails(folder)
    return jsonify(emails)

@app.route('/api/sync', methods=['POST'])
def sync_emails():
    try:
        count = mail_service.fetch_and_delete_emails()
        return jsonify({"success": True, "count": count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/send', methods=['POST'])
def send_email():
    data = request.json
    try:
        mail_service.send_email(
            to_email=data.get('to'),
            subject=data.get('subject'),
            body_html=data.get('body')
        )
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/trash/<int:email_id>', methods=['POST'])
def trash_email(email_id):
    database.move_to_trash(email_id)
    return jsonify({"success": True})

@app.route('/api/delete/<int:email_id>', methods=['DELETE'])
def delete_email(email_id):
    database.delete_email(email_id)
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
