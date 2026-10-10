import pytest
from src.components.auth.masker import mask_for_logs, mask_for_email


class TestMasker:
    
    def test_mask_for_logs_masks_passwords(self):
        """Test that mask_for_logs masks password fields."""
        data = {
            "email": "user@example.com",
            "password": "secret123",
            "hashed_password": "hashed_value",
            "confirm_password": "secret123",
            "name": "Test User"
        }
        
        masked = mask_for_logs(data)

        assert masked["password"] == "******"
        assert masked["hashed_password"] == "******"
        assert masked["confirm_password"] == "******"
        assert masked["email"] == "user@example.com"  # Email not masked in logs
        assert masked["name"] == "Test User"
    
    def test_mask_for_logs_masks_nested_passwords(self):
        """Test that mask_for_logs handles nested structures."""
        data = {
            "user": {
                "email": "user@example.com",
                "password": "secret123"
            },
            "credentials": [
                {"type": "password", "value": "pass123"},
                {"type": "api_key", "value": "key123"}
            ]
        }
        
        masked = mask_for_logs(data)
        
        assert masked["user"]["password"] == "******"
        # The key 'value' does not contain 'password', so it remains unchanged
        assert masked["credentials"][0]["value"] == "pass123"  # Not masked because key is 'value', not 'password'
        assert masked["credentials"][1]["value"] == "key123"
    
    def test_mask_for_email_partially_masks_emails(self):
        """Test that mask_for_email partially masks email addresses."""
        data = {
            "email": "user@example.com",
            "user_email": "john.doe@company.com",
            "password": "secret123"
        }
        
        masked = mask_for_email(data)
        
        assert masked["email"] == "us******@example.com"
        assert masked["user_email"] == "jo******@company.com"
        # Password should be fully masked
        assert masked["password"] == "******"
    
    def test_mask_for_email_masks_phone_numbers(self):
        """Test that mask_for_email masks phone numbers."""
        data = {
            "phone": "+1234567890",
            "mobile": "9876543210",
            "contact": "+1-555-123-4567"
        }
        
        masked = mask_for_email(data)

        # Only fields with 'email' or 'credential' in key name are masked
        # So these should remain unchanged
        assert masked["phone"] == "+1234567890"
        assert masked["mobile"] == "9876543210"
        assert masked["contact"] == "+1-555-123-4567"
    
    def test_mask_for_email_handles_list(self):
        """Test that mask_for_email handles lists."""
        data = [
            {"email": "user1@example.com", "password": "pass1"},
            {"email": "user2@example.com", "password": "pass2"}
        ]
        
        masked = mask_for_email(data)
        
        assert masked[0]["email"] == "us******@example.com"
        assert masked[0]["password"] == "******"
        assert masked[1]["email"] == "us******@example.com"
        assert masked[1]["password"] == "******"
    
    def test_mask_for_email_handles_credential_fields(self):
        """Test that credential fields are partially masked."""
        data = {
            "credential": "user123",
            "user_credential": "john.doe@company.com",
            "admin_credential": "+1234567890"
        }
        
        masked = mask_for_email(data)
        
        # credential fields should be partially masked
        assert masked["credential"] == "us****23"
        assert masked["user_credential"] == "jo******@company.com"
        assert masked["admin_credential"] == "+1****90"