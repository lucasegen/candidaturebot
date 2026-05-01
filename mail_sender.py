"""
Envoi d'emails via Gmail SMTP
Accepte une config (priorité) ou fallback sur .env
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


class MailSender:
    def __init__(self, config=None):
        self.config = config or {}
        api = self.config.get("api", {}) if isinstance(self.config, dict) else {}
        # Plusieurs noms de variables d'env supportés (compat historique)
        self.user = (
            api.get("gmail_user")
            or os.getenv("GMAIL_USER")
            or os.getenv("GMAIL_ADDRESS")
            or ""
        )
        pwd = (
            api.get("gmail_password")
            or os.getenv("GMAIL_APP_PASSWORD")
            or os.getenv("GMAIL_PASSWORD")
            or ""
        )
        self.password = pwd.replace(" ", "") if pwd else ""

    def send(self, to, subject, body, attachments=None):
        if not self.user or not self.password:
            raise RuntimeError(
                "Identifiants Gmail manquants. Configure-les dans ⚙️ Paramètres → Gmail."
            )

        safe_to = str(to).replace("\r", "").replace("\n", "").strip()
        safe_subject = str(subject).replace("\r", "").replace("\n", " ").strip()
        if not safe_to or "@" not in safe_to:
            raise RuntimeError(f"Adresse destinataire invalide : {to!r}")

        msg = MIMEMultipart()
        msg["From"] = self.user
        msg["To"] = safe_to
        msg["Subject"] = safe_subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        if attachments:
            from email.mime.base import MIMEBase
            from email import encoders
            missing = []
            for filepath in attachments:
                if not os.path.exists(filepath):
                    missing.append(filepath)
                    continue
                with open(filepath, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                safe_name = os.path.basename(filepath).replace("\r", "").replace("\n", "").replace('"', "")
                part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=safe_name,
                )
                msg.attach(part)
            if missing:
                # On n'empêche pas l'envoi mais on log explicitement.
                print(f"[mail_sender] pièces jointes introuvables (ignorées) : {missing}")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(self.user, self.password)
            server.send_message(msg)
        return True
