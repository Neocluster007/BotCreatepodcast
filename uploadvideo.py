import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# นี่คือไฟล์ที่คุณดาวน์โหลดมาจาก Google Cloud Console
CLIENT_SECRETS_FILE = "client_secrets.json"

# นี่คือสิทธิ์ที่เราขอ (อนุญาตให้อัปโหลด)
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

def get_authenticated_service():
    """
    ยืนยันตัวตนและสร้าง service object สำหรับเรียกใช้ API
    """
    credentials = None
    
    # ไฟล์ token.pickle จะเก็บ credentials ของผู้ใช้ที่ได้จากการล็อกอิน
    # มันจะถูกสร้างขึ้นมาอัตโนมัติหลังจากการยืนยันตัวตนครั้งแรก
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            credentials = pickle.load(token)

    # ถ้าไม่มี credentials ที่ใช้ได้ หรือหมดอายุ
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            # เริ่มขั้นตอนการล็อกอินผ่านเบราว์เซอร์
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            credentials = flow.run_local_server(port=0)
        
        # บันทึก credentials ไว้ใช้ครั้งต่อไป
        with open('token.pickle', 'wb') as token:
            pickle.dump(credentials, token)

    return build(API_SERVICE_NAME, API_VERSION, credentials=credentials)

def upload_video(youtube_service, file_path, title, description, category_id, tags, privacy_status):
    """
    อัปโหลดวิดีโอไปยัง YouTube
    """
    try:
        # สร้าง body ของ request ที่จะส่งไป
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags,
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': privacy_status
            }
        }
        CHUNK_SIZE = 10 * 1024 * 1024  # = 10MB (แบ่งส่งทีละ 10MB)
        # สร้าง MediaFileUpload object
        media = MediaFileUpload(file_path,
                                chunksize=CHUNK_SIZE,  # -1 หมายถึงอัปโหลดทีเดียวทั้งไฟล์
                                resumable=True) # แนะนำให้เป็น True สำหรับไฟล์ใหญ่

        # เรียก API videos().insert()
        request = youtube_service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        print(f"กำลังอัปโหลดวิดีโอ: {file_path}...")
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"อัปโหลดไปแล้ว {int(status.progress() * 100)}%")

        print(f"อัปโหลดสำเร็จ! Video ID: {response.get('id')}")
        return response.get('id')

    except HttpError as e:
        print(f"เกิดข้อผิดพลาด: {e}")
        return None
    except FileNotFoundError:
        print(f"ไม่พบไฟล์: {file_path}")
        return None

# --- ส่วนหลักที่จะรัน ---
if __name__ == '__main__':
    # --- กรุณาแก้ไขข้อมูลตรงนี้ ---
    VIDEO_FILE_TO_UPLOAD = r"E:\BOT\BotCreatepodcast\output\video_เสียงกระซิบจากสายน้ำ.mp4"  # แก้ไขเป็นชื่อไฟล์วิดีโอของคุณ
    VIDEO_TITLE = "ชื่อวิดีโอทดสอบ"
    VIDEO_DESCRIPTION = "นี่คือคำอธิบายวิดีโอ"
    VIDEO_TAGS = ["นิทาน", "นิทานก่อนนอน", "python"]
    VIDEO_CATEGORY = "22"  # ดู Category ID ได้ที่ https://developers.google.com/youtube/v3/docs/videoCategories/list (เช่น 22 = People & Blogs)
    PRIVACY_STATUS = "private"  # ตั้งเป็น "private" (ส่วนตัว), "unlisted" (ไม่แสดง), หรือ "public" (สาธารณะ)
    # ---------------------------------

    # ตรวจสอบว่าไฟล์วิดีโอมีอยู่จริง
    if not os.path.exists(VIDEO_FILE_TO_UPLOAD):
        print(f"ข้อผิดพลาด: ไม่พบไฟล์ '{VIDEO_FILE_TO_UPLOAD}'")
    else:
        # 1. ยืนยันตัวตน
        youtube = get_authenticated_service()
        
        # 2. อัปโหลดวิดีโอ
        upload_video(youtube, 
                     VIDEO_FILE_TO_UPLOAD,
                     VIDEO_TITLE, 
                     VIDEO_DESCRIPTION, 
                     VIDEO_CATEGORY,
                     VIDEO_TAGS, 
                     PRIVACY_STATUS)