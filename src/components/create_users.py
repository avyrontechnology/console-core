from uuid import UUID
import asyncio
import json
import os
import random
import smtplib
import string
import subprocess
import sys
from email.message import EmailMessage
from typing import Dict, List, Optional

# Check and install required libraries
required_modules = {
    "pandas": "pandas",
    "dependency_injector": "dependency_injector",
    "openpyxl": "openpyxl",
}

for module_name, pip_name in required_modules.items():
    try:
        __import__(module_name)
    except ModuleNotFoundError:
        print(f"{module_name} module not found. Installing it now...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
        print(f"{module_name} installed successfully.")

import pandas as pd
from dependency_injector.wiring import Provide, inject
from sqlalchemy import select

from src.components.auth.schema import UserData
from src.components.auth.service import AuthService
from src.components.user.models import User
from src.core.container import Container
from src.core.db import DatabaseSessionManager

# Constants
PARTNER_ID = 2
FILE_PATH = "User list of MBBS department.xlsx"
REPORT_FILE_PATH = "user_creation_report.xlsx"
ROLE_IDS = {
    "ADMIN": 1,
    "MANAGER": 2,
    "TL": 4,
    "COUNSELLOR": 3,
    "COUNSELOR": 3,
    "AGENT": 3,
}

# SMTP configuration
SMTP_SECRETS = json.loads(
    '{"EMAIL_VERIFICATION_BACKEND": "django.core.mail.backends.smtp.EmailBackend", "EMAIL_VERIFICATION_HOST": "smtp.gmail.com", "EMAIL_VERIFICATION_PORT": 587, "EMAIL_VERIFICATION_USE_TLS": true, "EMAIL_VERIFICATION_HOST_USER": "sahiljha158@gmail.com", "EMAIL_VERIFICATION_HOST_PASSWORD": "nxfq bfkk inex zhws"}'
)
RECIPIENT_EMAILS = ["sahil.jha@makunaiglobal.ai"]

# Dependency Injection Setup
container = Container()
container.wire(modules=[__name__])


# Utility Functions
def generate_password(length: int = 12) -> str:
    """Generate a strong password meeting the validation criteria."""
    characters = (
        string.ascii_uppercase
        + string.ascii_lowercase
        + string.digits
        + '!@#$%^&*(),.?":{}|<>'
    )
    while True:
        password = (
            random.choice(string.ascii_uppercase)
            + random.choice(string.ascii_lowercase)  # Ensure uppercase
            + random.choice(string.digits)  # Ensure lowercase
            + random.choice('!@#$%^&*(),.?":{}|<>')  # Ensure digit
            + "".join(  # Ensure special char
                random.choice(characters) for _ in range(length - 4)
            )
        )
        # Shuffle the password
        password_list = list(password)
        random.shuffle(password_list)
        password = "".join(password_list)
        try:
            UserData.validate_password(password)
            return password
        except ValueError:
            continue


def format_phone_number(phone: str) -> str:
    """Add +91 prefix if not present and clean up invalid formats."""
    phone = str(phone).strip()
    # Remove any decimal part (e.g., '.0' from Excel floats)
    if "." in phone:
        phone = phone.split(".")[0]
    # Remove any non-digit characters except leading '+'
    cleaned_phone = (
        "".join(filter(str.isdigit, phone)) if not phone.startswith("+") else phone[1:]
    )
    if phone.startswith("+91"):
        return f"+91{cleaned_phone}"
    if phone.startswith("91") and len(cleaned_phone) == 12:
        return f"+{cleaned_phone}"
    if len(cleaned_phone) == 10 and cleaned_phone.isdigit():
        return f"+91{cleaned_phone}"
    return phone  # Return as is if format is unexpected (will likely fail validation)


def send_email_with_attachment(file_path: str):
    subject = "User Creation Report"
    body = "Please find the attached Excel file containing the user creation report with IDs, emails, and passwords."

    print(f"Attempting to send email with attachment: {file_path}")
    email = EmailMessage()
    email["Subject"] = subject
    email["From"] = SMTP_SECRETS["EMAIL_VERIFICATION_HOST_USER"]
    email["To"] = ", ".join(RECIPIENT_EMAILS)
    email.set_content(body)

    with open(file_path, "rb") as f:
        email.add_attachment(
            f.read(),
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="user_creation_report.xlsx",
        )

    try:
        with smtplib.SMTP(
            SMTP_SECRETS["EMAIL_VERIFICATION_HOST"],
            SMTP_SECRETS["EMAIL_VERIFICATION_PORT"],
        ) as server:
            server.starttls() if SMTP_SECRETS["EMAIL_VERIFICATION_USE_TLS"] else None
            server.login(
                SMTP_SECRETS["EMAIL_VERIFICATION_HOST_USER"],
                SMTP_SECRETS["EMAIL_VERIFICATION_HOST_PASSWORD"],
            )
            server.send_message(email)
        print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email. Error: {str(e)}")


async def check_user_exists(email: str, db: DatabaseSessionManager) -> Optional[int]:
    """Check if a user with the given email already exists in the database."""
    async with db.session() as session:
        query = select(User).where(User.email == email)
        result = await session.execute(query)
        existing_user = result.scalar_one_or_none()
        return existing_user.id if existing_user else None


@inject
async def create_user_via_auth(
    user_data: UserData,
    auth_service: AuthService = Provide[Container.auth_service],
) -> Optional[int]:
    """Create a user using the AuthService."""
    try:
        user = await auth_service.sing_up(user_data)
        return user.id  # Assuming the response has an 'id' attribute
    except Exception as e:
        print(f"Error creating user '{user_data.name}' via AuthService: {str(e)}")
        return None


async def create_user_directly(
    email: str,
    password: str,
    name: str,
    designation: str,
    partner_id: UUID,
    role_id: UUID,
    parent_id: Optional[UUID] = None,
    phone_number: Optional[str] = None,
    db: DatabaseSessionManager = None,
) -> Optional[int]:
    """Directly inject a user into the database."""
    if not db:
        raise ValueError("DatabaseSessionManager instance is required")
    async with db.session() as session:
        try:
            # Assuming password needs to be hashed; adjust if AuthService handles this
            hashed_password = (
                password  # Placeholder; replace with actual hashing if needed
            )
            user = User(
                email=email,
                hashed_password=hashed_password,
                is_active=True,  # Default to active; adjust as needed
                phone_number=phone_number,
                name=name,
                designation=designation,
                partner_id=partner_id,
                role_id=role_id,
                parent_id=parent_id,
            )
            print(f"Adding user to the database directly: {user.__dict__}")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user.id
        except Exception as e:
            print(f"Error creating user '{name}' directly in DB: {str(e)}")
            await session.rollback()
            return None


async def process_users(
    file_path: str, auth_service: AuthService, db: DatabaseSessionManager
):
    """Process users from Excel file and create them hierarchically."""
    required_columns = [
        "Name",
        "Role",
        "Parent (if applicable)",
        "Email",
        "Phone Number",
        "Board (e.g., MBBS India, MBBS Abroad)",
    ]

    # Lists to track created users and failures
    created_users: List[Dict] = []
    failed_users: List[Dict] = []

    # Dictionaries to store created user IDs by name
    admin_ids: Dict[str, int] = {}
    manager_ids: Dict[str, int] = {}

    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        print(f"Error reading file '{file_path}': {str(e)}")
        return

    # Validate sheet structure
    missing_cols = [col for col in required_columns if col not in df.columns]
    if missing_cols:
        print(f"Missing required columns: {missing_cols}. Aborting.")
        return

    # Filter out users who have left
    df = df[df["Role"].str.strip().str.lower() != "she left"]
    total_users = len(df)

    # Step 1: Create Admins (no parent_id, direct DB insertion if no phone number)
    print("Creating Admin users...")
    for _, row in df[df["Role"].str.strip().str.lower() == "admin"].iterrows():
        name = str(row["Name"]).strip()
        email = (
            str(row["Email"]).strip()
            if pd.notna(row["Email"])
            else f"{name.lower().replace(' ', '')}@example.com"
        )
        designation = "ADMIN"  # Hardcode to match ROLE_IDS
        role_id = ROLE_IDS[designation]
        password = generate_password()
        phone_number = (
            str(row["Phone Number"]).strip() if pd.notna(row["Phone Number"]) else None
        )

        # Check if user already exists
        existing_id = await check_user_exists(email, db=db)
        if existing_id:
            admin_ids[name] = existing_id
            print(
                f"Admin '{name}' already exists with ID: {existing_id}. Skipping creation."
            )
            created_users.append(
                {"ID": existing_id, "Email": email, "Password": "Already Exists"}
            )
            continue

        if phone_number and phone_number != "nan":
            user_data = UserData(
                name=name,
                email=email,
                designation=designation,
                phone_number=format_phone_number(phone_number),
                partner_id=PARTNER_ID,
                role_id=role_id,
                password=password,
            )
            user_id = await create_user_via_auth(user_data, auth_service=auth_service)
        else:
            user_id = await create_user_directly(
                email=email,
                password=password,
                name=name,
                designation=designation,
                partner_id=PARTNER_ID,
                role_id=role_id,
                db=db,
            )

        if user_id:
            admin_ids[name] = user_id
            created_users.append({"ID": user_id, "Email": email, "Password": password})
            print(f"Created Admin '{name}' with ID: {user_id}")
        else:
            failed_users.append({"Name": name, "Reason": "Failed to create Admin"})
            print(f"Failed to create Admin '{name}'")

    # Step 2: Create Managers/TLs (parent_id from Admins)
    print("Creating Manager/TL users...")
    for _, row in df[
        df["Role"].str.strip().str.lower().isin(["manager", "tl"])
    ].iterrows():
        name = str(row["Name"]).strip()
        email = str(row["Email"]).strip()
        designation = str(row["Role"]).strip().upper()  # Use upper() to match ROLE_IDS
        role_id = ROLE_IDS[designation]
        password = generate_password()
        parent_name = (
            str(row["Parent (if applicable)"]).strip()
            if pd.notna(row["Parent (if applicable)"])
            else None
        )
        phone_number = (
            str(row["Phone Number"]).strip() if pd.notna(row["Phone Number"]) else None
        )

        # Check if user already exists
        existing_id = await check_user_exists(email, db=db)
        if existing_id:
            manager_ids[name] = existing_id
            print(
                f"{designation} '{name}' already exists with ID: {existing_id}. Skipping creation."
            )
            created_users.append(
                {"ID": existing_id, "Email": email, "Password": "Already Exists"}
            )
            continue

        parent_id = None
        if parent_name and parent_name != "—":
            parents = [p.strip() for p in parent_name.split(",")]
            for parent in parents:
                if parent in admin_ids:
                    parent_id = admin_ids[parent]
                    break
                elif (
                    parent in manager_ids
                ):  # In case a Manager reports to another Manager
                    parent_id = manager_ids[parent]
                    break

        if phone_number and phone_number != "nan":
            user_data = UserData(
                name=name,
                email=email,
                designation=designation,
                phone_number=format_phone_number(phone_number),
                parent_id=parent_id,
                partner_id=PARTNER_ID,
                role_id=role_id,
                password=password,
            )
            user_id = await create_user_via_auth(user_data, auth_service=auth_service)
        else:
            user_id = await create_user_directly(
                email=email,
                password=password,
                name=name,
                designation=designation,
                partner_id=PARTNER_ID,
                role_id=role_id,
                parent_id=parent_id,
                db=db,
            )

        if user_id:
            manager_ids[name] = user_id
            created_users.append({"ID": user_id, "Email": email, "Password": password})
            print(
                f"Created {designation} '{name}' with ID: {user_id}, Parent ID: {parent_id or 'None'}"
            )
        else:
            failed_users.append(
                {"Name": name, "Reason": f"Failed to create {designation}"}
            )
            print(f"Failed to create {designation} '{name}'")

    # Step 3: Create Counsellors/Agents (parent_id from Managers/TLs)
    print("Creating Counsellor/Agent users...")
    for _, row in df[
        df["Role"].str.strip().str.lower().isin(["counsellor", "counselor", "agent"])
    ].iterrows():
        name = str(row["Name"]).strip()
        email = str(row["Email"]).strip()
        designation = str(row["Role"]).strip().upper()  # Use upper() to match ROLE_IDS
        role_id = ROLE_IDS[designation]
        password = generate_password()
        parent_name = (
            str(row["Parent (if applicable)"]).strip()
            if pd.notna(row["Parent (if applicable)"])
            else None
        )
        phone_number = (
            str(row["Phone Number"]).strip() if pd.notna(row["Phone Number"]) else None
        )

        # Check if user already exists
        existing_id = await check_user_exists(email, db=db)
        if existing_id:
            print(
                f"{designation} '{name}' already exists with ID: {existing_id}. Skipping creation."
            )
            created_users.append(
                {"ID": existing_id, "Email": email, "Password": "Already Exists"}
            )
            continue

        parent_id = None
        if parent_name and parent_name != "—":
            parents = [p.strip() for p in parent_name.split(",")]
            for parent in parents:
                if parent in manager_ids:
                    parent_id = manager_ids[parent]
                    break
                elif (
                    parent in admin_ids
                ):  # In case a Counsellor reports directly to an Admin
                    parent_id = admin_ids[parent]
                    break

        if phone_number and phone_number != "nan":
            user_data = UserData(
                name=name,
                email=email,
                designation=designation,
                phone_number=format_phone_number(phone_number),
                parent_id=parent_id,
                partner_id=PARTNER_ID,
                role_id=role_id,
                password=password,
            )
            user_id = await create_user_via_auth(user_data, auth_service=auth_service)
        else:
            user_id = await create_user_directly(
                email=email,
                password=password,
                name=name,
                designation=designation,
                partner_id=PARTNER_ID,
                role_id=role_id,
                parent_id=parent_id,
                db=db,
            )

        if user_id:
            created_users.append({"ID": user_id, "Email": email, "Password": password})
            print(
                f"Created {designation} '{name}' with ID: {user_id}, Parent ID: {parent_id or 'None'}"
            )
        else:
            failed_users.append(
                {"Name": name, "Reason": f"Failed to create {designation}"}
            )
            print(f"Failed to create {designation} '{name}'")

    # Generate report
    success_df = pd.DataFrame(created_users)
    failed_df = pd.DataFrame(failed_users)

    writer = pd.ExcelWriter(REPORT_FILE_PATH)
    success_df.to_excel(writer, sheet_name="Created Users", index=False)
    failed_df.to_excel(writer, sheet_name="Failed Users", index=False)
    writer.close()
    print(f"Report saved to {REPORT_FILE_PATH}")

    # Send email
    send_email_with_attachment(REPORT_FILE_PATH)

    # Cleanup
    # os.remove(REPORT_FILE_PATH)
    # print(f"Temporary file {REPORT_FILE_PATH} removed.")

    # Summary
    print(
        f"Total users in Excel: {total_users}, Created: {len(created_users)}, Failed: {len(failed_users)}"
    )


async def main():
    auth_service_raw = container.auth_service()
    db_raw = container.db()
    auth_service = (
        await auth_service_raw
        if asyncio.isfuture(auth_service_raw)
        else auth_service_raw
    )
    db = await db_raw if asyncio.isfuture(db_raw) else db_raw

    if auth_service and db:
        await process_users(FILE_PATH, auth_service, db)
    else:
        print("Auth service or DB session is not available. Aborting.")


if __name__ == "__main__":
    asyncio.run(main())
