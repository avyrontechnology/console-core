from typing import Final


TEMPLATES_PATH = "src/components/templates"
SEND_CREDENTIALS_BODY: Final[str] = (
    "Dear {user_name},\n\n"
    "We are excited to inform you that your account has been successfully created. "
    "You can now access all the features and resources available to you.\n\n"
    "Here are your account credentials for reference:\n"
    "Email: {credential}\n"
    "Password: {password}\n\n"
    "You can start exploring your account immediately. "
    "If you have any questions or need assistance, our support team is always here to help.\n\n"
    "Welcome aboard!\n\n"
    "Best regards,\n"
    "The Obotaai Global Team"
)
