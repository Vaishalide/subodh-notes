import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Load Credentials
SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise Exception("GOOGLE_CREDENTIALS not found")
    
    creds_dict = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def upload_to_drive(file_path, filename, folder_id):
    service = get_drive_service()
    
    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }
    
    # Try uploading without 'supportsAllDrives' first for personal folders
    media = MediaFileUpload(file_path, resumable=True)
    
    try:
        file = service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id, webViewLink'
        ).execute()
    except Exception as e:
        # If it fails, try with supportsAllDrives=True
        print(f"Standard upload failed, retrying with Team Drive flag: {e}")
        media = MediaFileUpload(file_path, resumable=True)
        file = service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()
    
    # Make Public
    try:
        permission = {'type': 'anyone', 'role': 'reader'}
        service.permissions().create(fileId=file.get('id'), body=permission).execute()
    except:
        pass
    
    return file.get('id'), file.get('webViewLink')

def get_storage_info():
    try:
        service = get_drive_service()
        about = service.about().get(fields="storageQuota").execute()
        quota = about.get('storageQuota')
        limit = int(quota.get('limit', 0))
        usage = int(quota.get('usage', 0))
        
        if limit == 0: return "Shared/Unlimited"
        free_gb = round((limit - usage) / (1024**3), 2)
        return f"{free_gb} GB Free"
    except:
        return "Unknown"
