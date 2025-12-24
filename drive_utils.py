import os
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

def get_drive_service():
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN")
    
    if not all([client_id, client_secret, refresh_token]):
        raise Exception("Missing OAuth Credentials in Heroku Env Vars (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN)")

    # Create Credentials object using Refresh Token
    creds = Credentials(
        None, # Access token (will be refreshed)
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret
    )
    
    # Refresh the token if expired
    if not creds.valid:
        creds.refresh(Request())
        
    return build('drive', 'v3', credentials=creds)

def upload_to_drive(file_path, filename, folder_id):
    try:
        service = get_drive_service()
        
        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }
        
        media = MediaFileUpload(file_path, resumable=True)
        
        # Upload using 'supportsAllDrives' to ensure compatibility
        file = service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()
        
        # Make Public (Anyone with link can view)
        try:
            permission = {'type': 'anyone', 'role': 'reader'}
            service.permissions().create(fileId=file.get('id'), body=permission).execute()
        except Exception as p_err:
            print(f"Permission Warning: {p_err}")
        
        return file.get('id'), file.get('webViewLink')
        
    except Exception as e:
        print(f"Drive Upload Error: {e}")
        raise e

def get_storage_info():
    try:
        service = get_drive_service()
        about = service.about().get(fields="storageQuota").execute()
        quota = about.get('storageQuota')
        
        limit = int(quota.get('limit', 0))
        usage = int(quota.get('usage', 0))
        
        if limit == 0: return "Unlimited"
        
        limit_gb = round(limit / (1024**3), 2)
        usage_gb = round(usage / (1024**3), 2)
        free_gb = round(limit_gb - usage_gb, 2)
        
        return f"{free_gb} GB free of {limit_gb} GB"
    except Exception as e:
        return f"Error checking storage: {str(e)}"
