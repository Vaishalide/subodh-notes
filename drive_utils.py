import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Load Credentials from Environment Variable
SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise Exception("GOOGLE_CREDENTIALS not found in Env Vars")
    
    creds_dict = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def upload_to_drive(file_path, filename, folder_id):
    service = get_drive_service()
    
    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }
    media = MediaFileUpload(file_path, resumable=True)
    
    file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    
    # Make file public (so students can view it)
    permission = {'type': 'anyone', 'role': 'reader'}
    service.permissions().create(fileId=file.get('id'), body=permission).execute()
    
    return file.get('id'), file.get('webViewLink')

def get_storage_info():
    service = get_drive_service()
    about = service.about().get(fields="storageQuota").execute()
    quota = about.get('storageQuota')
    
    limit = int(quota.get('limit', 0))
    usage = int(quota.get('usage', 0))
    
    # Convert to GB
    limit_gb = round(limit / (1024**3), 2)
    usage_gb = round(usage / (1024**3), 2)
    free_gb = round(limit_gb - usage_gb, 2)
    
    return f"{free_gb} GB free of {limit_gb} GB"
