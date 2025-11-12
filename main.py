import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

import schedule
import time
import sys

import google.generativeai as genaiA
from google import genai

from google.genai import types
import wave
import requests

from moviepy import ImageClip, AudioFileClip, CompositeVideoClip # <--- เพิ่ม MoviePy
import soundfile as sf # <--- เพิ่ม soundfile เพื่อหาความยาวเสียง

# --- 1. Import ---
from moviepy import (
    ImageClip, 
    AudioFileClip, 
    TextClip, 
    CompositeVideoClip,
    VideoClip # สำหรับ Visualizer
)
import numpy as np # สำหรับประมวลผลเสียง
import os 
import traceback 

# นี่คือไฟล์ที่คุณดาวน์โหลดมาจาก Google Cloud Console
CLIENT_SECRETS_FILE = "client_secrets.json"

# นี่คือสิทธิ์ที่เราขอ (อนุญาตให้อัปโหลด)
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'


# --- 2. ตั้งค่าไฟล์ (Paths) ---
#image_path = r"E:\BOT\BotCreatepodcast\output_centered.png"
#audio_path = r"E:\BOT\BotCreatepodcast\source\out.wav"
 # <--- ตั้งชื่อไฟล์ Output ใหม่

print("--- เริ่มกระบวนการสร้างวิดีโอ (v4 Visualizer Fix) ---")

file_nameBG = "source/BGEdit.jpg"
file_nameBG_Edit = "source/BG.jpg"
file_nameAudio='source/out.wav'
font_path = "font/Sarabun-Bold.ttf"
output_path = "output/video.mp4"

# --- กำหนดตัวแปรคลิปเป็น None ก่อน ---
audio_clip = None
image_clip = None
txt_clip = None
visualizer_clip = None 
final_video = None

try:
    GEMINI_API_KEY = ""
    genaiA.configure(api_key=GEMINI_API_KEY)
except ValueError as e:
    print(e)
    print("เกิดข้อผิดพลาด: กรุณาตั้งค่า GEMINI_API_KEY ใน Environment Variable")
    exit()
    


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


# Set up the wave file to save the output:
def wave_file(filename, pcm, channels=1, rate=24000, sample_width=2):
   with wave.open(filename, "wb") as wf:
      wf.setnchannels(channels)
      wf.setsampwidth(sample_width)
      wf.setframerate(rate)
      wf.writeframes(pcm)

client = genai.Client(api_key=GEMINI_API_KEY)

def generate_story_from_gemini():
    """
    เรียก Gemini API เพื่อสร้างเนื้อเรื่อง
    """

    system_prompt = """
        คุณคือ "นักเขียนสคริปต์นิทาน (Story Scripter)" ภารกิจของคุณคือการสร้าง "สคริปต์นิทาน" ในรูปแบบ Text ธรรมดา เพื่อเตรียมส่งต่อให้ระบบ TTS

        กฎเหล็กที่ต้องปฏิบัติตาม:

        คิดเรื่องเอง: คุณต้องประดิษฐ์นิทานต้นฉบับเรื่องใหม่ (อบอุ่น, จบแฮปปี้) ขึ้นมาเองทั้งหมด

        ห้ามทักทาย/ห้ามขอโทษ: ไม่ต้องพูดเกริ่นนำ, ไม่ต้องขอโทษ, ไม่ต้องพูดว่า "ได้ครับ" หรือ "นี่คือ..." ให้ส่งผลลัพธ์ตามรูปแบบทันที

        รูปแบบผลลัพธ์ (สำคัญมาก):

        ไม่ต้องมี "" ใน เนื้อเรื่อง

        บรรทัดแรก: ต้องเป็น "ชื่อเรื่อง" (เช่น: เม็ดกระดุมนักเดินทาง)
        บรรทัดที่สาม: เชิญชวนให้กด like กด subscriber ช่อง youtube นิทานข้างหมอน เพื่อเป็นกำลังใจเรานะจ๊ะ (คั่นด้วย \n\n)
        บรรทัดที่สอง: ต้องเป็น "บรรทัดว่าง" 1 บรรทัด (คั่นด้วย \n\n)

        บรรทัดที่สามเป็นต้นไป: คือ "สคริปต์เนื้อหา"

        รูปแบบสคริปต์เนื้อหา:



        ห้ามมีคำอธิบายอื่นใดนอกเหนือจากสคริปต์

        ห้ามใส่ใน Code Block (เช่น ```)

        นิทานยาว 15 นาที - 20 นาที 
    """

    # --- 2. กำหนด User Prompt (โจทย์ของเรื่อง) ---
    user_story_prompt = "สร้างนิทานไว้สำหรับฟังก่อนนอน 1 เรื่อง เน้นหลากหลาย"
    
    #print("กำลังติดต่อ Gemini เพื่อสร้างเรื่อง... (รอสักครู่)")
    try:
        # (ใช้ gemini-pro ที่เสถียรและใช้งานได้)
        model = genaiA.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system_prompt
        )
        response = model.generate_content(user_story_prompt)
        
        if response and response.text:
            print("--- Gemini สร้างเรื่องเสร็จแล้ว ---")
            return response.text
        else:
            print("ไม่ได้รับการตอบกลับจาก Gemini")
            return None
            
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการเรียก Gemini API: {e}")
        return None

def generate_image_from_gemini(title):
    """
    เรียก Gemini API เพื่อสร้างเนื้อเรื่อง
    """

    user_story_prompt = """
        A cute children's storybook cover illustration for """ + title + """, whimsical cartoon style. Featured characters: [Insert Main Character/Elements from StoryTitle Here, e.g., a glowing firefly, a brave little cloud, a shy rabbit]. Magical forest at night, twinkling stars, smiling moon. Soft pastel watercolor art, cozy and dreamy atmosphere, no text or typography.
    """
    
    #print("กำลังติดต่อ Gemini เพื่อสร้างรูป")
    try:
        # (ใช้ gemini-pro ที่เสถียรและใช้งานได้)
        model = genaiA.GenerativeModel(
            model_name="gemini-2.5-flash"
        )
        response = model.generate_content(user_story_prompt)
        
        if response and response.text:

            import random
            from urllib.parse import quote

            # --- ตั้งค่าตัวแปร ---
            width = 1920
            height = 1080
            random_seed = random.randint(0, 99999) # เทียบเท่า Math.floor(Math.random() * 100000)

            # (สำคัญ!) ส่วนนี้ ($input.first().json.output) เป็นโค้ดเฉพาะแพลตฟอร์ม
            # ใน Python คุณต้องกำหนดค่า `final_prompt` นี้เอง
            # 
            # ตัวอย่าง:
            final_prompt = response.text.encode("utf-8")
            # -----------------------------------------------------------------


            # สร้าง URL โดยมีการเข้ารหัส (encode) prompt
            image_url = f"https://image.pollinations.ai/prompt/{quote(final_prompt)}.jpg?width={width}&height={height}&seed={random_seed}&model=flux&nologo=true"

            # สร้างผลลัพธ์ (ใน Python คือ list ที่มี dictionary อยู่ข้างใน)
            result = [
                {
                    "json": {
                        "text": final_prompt,
                        "imageUrl": image_url
                    }
                }
            ]

            # พิมพ์ผลลัพธ์ (หรือ return ถ้าคุณใช้ในฟังก์ชัน)
            #print(image_url)

            import time
            time.sleep(30)

            try:
                # ส่ง HTTP GET request ไปที่ URL
                response = requests.get(image_url)

                # ตรวจสอบว่า request สำเร็จหรือไม่ (status code 200 คือสำเร็จ)
                if response.status_code == 200:
                    # เปิดไฟล์ในโหมด 'write binary' ('wb')
                    with open(file_nameBG, 'wb') as f:
                        # เขียนข้อมูล (content) ของ response ซึ่งเป็น bytes ของรูปภาพ
                        f.write(response.content)
                    print(f"ดาวน์โหลดรูปภาพสำเร็จ บันทึกเป็น: {file_nameBG}")
                else:
                    print(f"ดาวน์โหลดไม่สำเร็จ Status code: {response.status_code}")

                    generate_image_from_gemini(title)

            except requests.exceptions.RequestException as e:
                print(f"เกิดข้อผิดพลาดในการเชื่อมต่อ: {e}")

            return image_url
        else:
            print("ไม่ได้รับการตอบกลับจาก Gemini")
            return None
            
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการเรียก Gemini API: {e}")
        return None

def speak(txt):
    response = client.models.generate_content(
        model="gemini-2.5-flash-preview-tts",
        contents=txt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name='Kore',
                    )
                )
            ),
        )
    )

    data = response.candidates[0].content.parts[0].inline_data.data
    wave_file(file_nameAudio, data) # Saves the file to current directory

def Editimage(title):
    from PIL import Image, ImageDraw, ImageFont

    # 1. โหลดภาพและฟอนต์
    try:
        img = Image.open(file_nameBG)
        # ตรวจสอบให้แน่ใจว่าคุณมีไฟล์ฟอนต์นี้อยู่ในโฟลเดอร์เดียวกัน
        font_path = "font/Sarabun-Bold.ttf" 
        font_size = 80
        font = ImageFont.truetype(font_path, font_size)
    except IOError:
        print("ไม่พบไฟล์ภาพ background.jpg หรือไฟล์ฟอนต์ Sarabun-Bold.ttf")
        exit()

    # 2. สร้าง object สำหรับวาด
    draw = ImageDraw.Draw(img)

    # 3. ข้อความที่ต้องการ
    text = title

    # 4. หาวิชาคำนวณตำแหน่งกลางภาพ
    # ได้ขนาดภาพ (width, height)
    img_width, img_height = img.size
        
    # ตำแหน่งกึ่งกลาง
    center_x = img_width / 2
    center_y = img_height -100

    # 5. วาดข้อความโดยใช้ Anchor
    # เราส่งตำแหน่งกึ่งกลางภาพ (center_x, center_y) เข้าไป
    # และบอก Pillow ว่าให้ใช้จุดนี้เป็นจุดกึ่งกลางของข้อความ (anchor="mm")
    draw.text(
        (center_x, center_y),  # พิกัดกึ่งกลางภาพ
        text,
        font=font,
        fill="white",
        anchor="mm",           # <--- นี่คือส่วนสำคัญ!
        stroke_width=5,
        stroke_fill="black"
    )

    # 6. บันทึก
    img.save(file_nameBG_Edit)
    print("บันทึกภาพพร้อมข้อความกลางภาพแล้ว (วิธี Anchor)")

def CreateVideo():
    global output_path
    try:
        # --- 3. ตรวจสอบและโหลดไฟล์เสียง ---
        if not os.path.exists(file_nameAudio) or os.path.getsize(file_nameAudio) == 0:
            raise FileNotFoundError(f"❌ Error: ไม่พบไฟล์เสียง หรือไฟล์เสียงว่างเปล่า: {file_nameAudio}")
            
        print(f"กำลังโหลดเสียง: {file_nameAudio}")
        audio_clip = AudioFileClip(file_nameAudio)
        final_video_duration = audio_clip.duration
        
        if final_video_duration is None or final_video_duration <= 0:
            raise ValueError(f"❌ Error: ไม่สามารถหาความยาวเสียงได้ (ไฟล์อาจเสียหาย): {file_nameAudio}")
            
        print(f"ความยาวเสียง: {final_video_duration:.2f} วินาที")

        # --- 4. โหลดภาพพื้นหลัง (Image) ---
        print(f"กำลังโหลดภาพ: {file_nameBG_Edit}")
        image_clip = ImageClip(file_nameBG_Edit).with_duration(final_video_duration)

        # --- 5. สร้างคลิปตัวอักษร (Text) ---
        print(f"กำลังสร้างข้อความด้วยฟอนต์: {font_path}")
        txt_clip = TextClip(
            text="Hello", 
            font=font_path, 
            font_size=72, 
            color='white',
            stroke_color="blue", 
            stroke_width=10
        ).with_position('center').with_duration(final_video_duration)


        # --- 6. (FIX) สร้าง Bar เสียง (Audio Visualizer) ---
        print("กำลังวิเคราะห์ข้อมูลเสียงสำหรับ Bar เสียง...")
        
        audio_sample_rate = 44100 
        audio_data = audio_clip.to_soundarray(fps=audio_sample_rate)
        
        vis_width = 50  
        vis_height = 100 
        
        # (FIX 1) แก้สี Bar ให้ทึบแสง: (R, G, B, Alpha)
        vis_color = (255, 255, 255, 255) # สีขาว, ทึบแสง (255)
        vis_bg_color = (0, 0, 0, 0)     # พื้นหลัง, โปร่งใส (0)

        # (FIX 2) ฟังก์ชันสำหรับสร้างเฟรมของ Bar เสียง
        def make_visualizer_frame(t):
            
            time_window = 0.1 
            
            start_index = int(max(0, (t - time_window / 2) * audio_sample_rate))
            end_index = int(min(len(audio_data), (t + time_window / 2) * audio_sample_rate))

            if start_index >= end_index:
                amplitude = 0
            else:
                channel_data = audio_data[start_index:end_index, 0]
                amplitude = np.mean(np.abs(channel_data))
                
            # (FIX 3) เพิ่มตัวคูณความดังเป็น * 10 เพื่อให้ Bar เด้งชัดขึ้น
            bar_height = int(np.clip(amplitude * 10, 0, 1) * vis_height)
            
            # สร้างเฟรม (ภาพ) พื้นหลังโปร่งใส
            frame = np.full((vis_height, vis_width, 4), vis_bg_color, dtype=np.uint8)
            
            if bar_height > 0:
                # (FIX 4) วาด Bar โดยใช้สีที่มี Alpha (vis_color)
                # เราจะวาด Bar จากล่างขึ้นบน
                frame[vis_height - bar_height : vis_height, 0 : vis_width] = vis_color

            return frame # คืนค่าเป็น numpy array (ภาพ)

        print("กำลังสร้างคลิป Bar เสียง...")
        visualizer_clip = VideoClip(make_visualizer_frame, duration=final_video_duration)
        
        # (FIX 5) ตั้งตำแหน่ง Bar ไปที่ (x=20, y=20) (มุมซ้ายบน, เว้นขอบ 20px)
        visualizer_clip = visualizer_clip.with_position((20, 20))
        # ---------------------------------------------------


        # --- 7. ประกอบร่าง (Composite) ---
        print("กำลังรวมภาพ, ข้อความ, และ Bar เสียง...")
        final_video = CompositeVideoClip([
            image_clip,       
            #txt_clip,       
            visualizer_clip # (Bar เสียงอยู่บนสุด)
        ])

        # --- 8. ใส่เสียง (Audio) ---
        final_video = final_video.with_audio(audio_clip)

        # --- 9. บันทึกไฟล์ (Write file) ---
        print(f"กำลังบันทึกไฟล์วิดีโอ: {output_path} (อาจใช้เวลาสักครู่)...")
        
        final_video.write_videofile(
            output_path, 
            fps=24, 
            codec="libx264",
            audio_codec="libmp3lame",
            audio_bitrate="192k"
        )

        print(f"✅ สร้างไฟล์วิดีโอ '{output_path}' สำเร็จ!")

    except Exception as e:
        print(f"\n❌ เกิดข้อผิดพลาดระหว่างการสร้างวิดีโอ:")
        print(f"Error: {e}")
        traceback.print_exc()

    finally:
        # --- 10. ปิดไฟล์ Clips ---
        print("--- กำลังปิดทรัพยากร (Closing files)... ---")
        if audio_clip: audio_clip.close()
        if image_clip: image_clip.close()
        if txt_clip: txt_clip.close()
        if visualizer_clip: visualizer_clip.close() 
        if final_video: final_video.close()

def uploadtoyoutube(path,VIDEO_TITLE,VIDEO_DESCRIPTION):
    # --- กรุณาแก้ไขข้อมูลตรงนี้ ---
    VIDEO_FILE_TO_UPLOAD = path  # แก้ไขเป็นชื่อไฟล์วิดีโอของคุณ
    
    
    #VIDEO_TITLE = VIDEO_TITLE
    #VIDEO_DESCRIPTION = "นี่คือคำอธิบายวิดีโอ"
    VIDEO_TAGS = ["นิทาน", "นิทานก่อนนอน", "นิทานข้างหมอน", "เล่านิทาน", "นิทานสอนใจ", "นิทานสำหรับเด็ก", "ฟังเพลิน"]
    VIDEO_CATEGORY = "22"  # ดู Category ID ได้ที่ https://developers.google.com/youtube/v3/docs/videoCategories/list (เช่น 22 = People & Blogs)
    PRIVACY_STATUS = "public"  # ตั้งเป็น "private" (ส่วนตัว), "unlisted" (ไม่แสดง), หรือ "public" (สาธารณะ)
    THUMBNAIL_FILE = "source/BG.jpg" # <<! เพิ่มบรรทัดนี้: แก้เป็นชื่อไฟล์ภาพหน้าปก
    # ---------------------------------

    # ตรวจสอบว่าไฟล์วิดีโอมีอยู่จริง
    if not os.path.exists(VIDEO_FILE_TO_UPLOAD):
        print(f"ข้อผิดพลาด: ไม่พบไฟล์ '{VIDEO_FILE_TO_UPLOAD}'")
    else:
        # 1. ยืนยันตัวตน
        youtube = get_authenticated_service()
        
        # 2. อัปโหลดวิดีโอ
        video_id = upload_video(youtube, 
                     VIDEO_FILE_TO_UPLOAD,
                     VIDEO_TITLE + " #นิทานข้างหมอน #นิทานก่อนนอน #นิทาน", 
                     VIDEO_DESCRIPTION, 
                     VIDEO_CATEGORY,
                     VIDEO_TAGS, 
                     PRIVACY_STATUS)
        
        # 3. อัปโหลดภาพหน้าปก (ถ้าอัปโหลดวิดีโอสำเร็จ)
        '''
        if video_id:
            print(f"วิดีโออัปโหลดสำเร็จ (ID: {video_id}). เริ่มอัปโหลดภาพหน้าปก...")
            upload_thumbnail(youtube, video_id, THUMBNAIL_FILE)
        else:
            print("การอัปโหลดวิดีโอล้มเหลว จึงไม่ได้อัปโหลดภาพหน้าปก")
        '''

def upload_thumbnail(youtube_service, video_id, thumbnail_file):
    """
    อัปโหลดภาพหน้าปก (thumbnail) ไปยังวิดีโอที่ระบุ
    """
    try:
        # ตรวจสอบว่าไฟล์ภาพมีอยู่จริง
        if not os.path.exists(thumbnail_file):
            print(f"ข้อผิดพลาด: ไม่พบไฟล์ภาพหน้าปก '{thumbnail_file}'")
            return

        print(f"กำลังอัปโหลดภาพหน้าปก: {thumbnail_file} ไปยัง Video ID: {video_id}...")
        
        # สร้าง MediaFileUpload object สำหรับภาพ
        media = MediaFileUpload(thumbnail_file)

        # เรียก API thumbnails().set()
        request = youtube_service.thumbnails().set(
            videoId=video_id,
            media_body=media
        )
        
        response = request.execute()
        
        print(f"อัปโหลดภาพหน้าปกสำเร็จ! URL: {response['items'][0]['url']}")

    except HttpError as e:
        print(f"เกิดข้อผิดพลาดในการอัปโหลดภาพหน้าปก: {e}")
        print("---!!! (โปรดตรวจสอบว่าช่องของคุณ 'ยืนยันตัวตนด้วยเบอร์มือถือ' แล้ว) !!! ---")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดไม่ทราบสาเหตุ: {e}")

def mainprogram():

    global output_path
    
    print("1.สร้างเรื่องราวนิทาน")
    story_script = generate_story_from_gemini()
    
    if story_script:
        
        title = story_script.split("\n")
        title[0] = title[0].replace("ชื่อเรื่อง: ", "")

        import datetime

        # สมมติว่าตัวแปร title ของคุณมีค่าแบบนี้
        #title = ["MyCoolVideo"]

        # 1. ดึงวันที่และเวลาปัจจุบัน
        now = datetime.datetime.now()

        # 2. จัดรูปแบบวันที่และเวลาให้เป็น string ที่เหมาะกับชื่อไฟล์
        #    (เช่น "20251112_003313" สำหรับ ปี-เดือน-วัน_ชั่วโมง-นาที-วินาที)
        #    รูปแบบ %Y%m%d_%H%M%S จะไม่มีอักขระพิเศษ (เช่น : หรือ /)
        timestamp = now.strftime("%Y%m%d_%H%M%S")


        print("2.สร้างรูปภาพหน้าปก")
        generate_image_from_gemini(title[0])
        print("3.แก้ไขรูปภาพ")
        Editimage(title[0])
        output_path = "output/video_"+title[0]+".mp4"
        output_path = f"output/video_{timestamp}_{title[0]}.mp4"

        print("4.สร้างเสียงจากเนื้อเรื่อง")
        speak(story_script)
        print("5.สร้างวิดิโอ")
        CreateVideo()

        description = "❤️ ชอบนิทานเรื่องนี้ไหม? ถ้าชอบ อย่าลืมกด Like 👍 และ Share เพื่อแบ่งปันเรื่องราวดีๆ นี้ให้เพื่อนๆ ฟังต่อนะครับ 🔔 ไม่อยากพลาดนิทานเรื่องใหม่ใช่ไหม? กด Subscribe (ติดตาม) ช่อง ""นิทานข้างหมอน"" และอย่าลืม กดกระดิ่ง แจ้งเตือนไว้ด้วยนะ! พวกเราจะได้มาเจอกันทุกคืนก่อนนอน 💬 อยากฟังเรื่องอะไร? คอมเมนต์บอกเราหน่อยว่าคุณชอบนิทานแนวไหน หรืออยากฟังนิทานเรื่องอะไรเป็นพิเศษในครั้งต่อไป! นิทานข้างหมอน #นิทานก่อนนอน #นิทาน #เล่านิทาน #นิทานสอนใจ #นิทานสำหรับเด็ก #ฟังเพลิน"

        #uploadtoyoutube(output_path,title[0],description)
        print("----------------------------- Finish -----------------------------")
    else:
        print("ไม่สามารถสร้างเรื่องได้ โปรดตรวจสอบ API Key หรือการเชื่อมต่อ")
    

    #description = "❤️ ชอบนิทานเรื่องนี้ไหม? ถ้าชอบ อย่าลืมกด Like 👍 และ Share เพื่อแบ่งปันเรื่องราวดีๆ นี้ให้เพื่อนๆ ฟังต่อนะครับ 🔔 ไม่อยากพลาดนิทานเรื่องใหม่ใช่ไหม? กด Subscribe (ติดตาม) ช่อง ""นิทานข้างหมอน"" และอย่าลืม กดกระดิ่ง แจ้งเตือนไว้ด้วยนะ! พวกเราจะได้มาเจอกันทุกคืนก่อนนอน 💬 อยากฟังเรื่องอะไร? คอมเมนต์บอกเราหน่อยว่าคุณชอบนิทานแนวไหน หรืออยากฟังนิทานเรื่องอะไรเป็นพิเศษในครั้งต่อไป! นิทานข้างหมอน #นิทานก่อนนอน #นิทาน #เล่านิทาน #นิทานสอนใจ #นิทานสำหรับเด็ก #ฟังเพลิน"

    #uploadtoyoutube(r"E:\BOT\BotCreatepodcast\output\video_การเดินทางของแสงดี.mp4","การเดินทางของแสงดี",description)
# --- Main Program ---
if __name__ == "__main__":

    mainprogram()

    schedule.every().day.at("12:00:00").do(mainprogram)
    #schedule.every().day.at("18:00:00").do(mainprogram)
    #schedule.every().day.at("22:00:00").do(mainprogram)
    #schedule.every().day.do(mainprogram)

    try:
        while True:
            schedule.run_pending() # ตรวจสอบว่ามีงานถึงเวลาที่ต้องทำหรือไม่
            time.sleep(1)          # หน่วงเวลา 1 วินาที เพื่อไม่ให้ CPU ทำงานหนัก
    except KeyboardInterrupt:
        print("หยุดการทำงานสคริปต์")
