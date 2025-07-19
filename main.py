from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
import os
from dotenv import load_dotenv
import google.generativeai as genai
from PIL import Image
import io
import base64
from gtts import gTTS
import requests
from sqlalchemy.orm import Session

import models, schemas, crud, auth
from .database import SessionLocal, engine

# Veritabanı tablolarını oluştur
models.Base.metadata.create_all(bind=engine)

# .env dosyasındaki API anahtarlarını yükle
load_dotenv()

# API anahtarlarını ortam değişkenlerinden al
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")

# Google Gemini API'sini yapılandır
genai.configure(api_key=GOOGLE_API_KEY)

app = FastAPI()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class ImageRequest(BaseModel):
    image_bytes_base64: str
    style_prompt: str

class StoryRequest(BaseModel):
    image_bytes_base64: str

class SoundRequest(BaseModel):
    image_bytes_base64: str

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# User registration
@app.post("/register", response_model=schemas.User)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    return crud.create_user(db=db, user=user)

# User login (OAuth2)
@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = auth.get_user(db, username=form_data.username)
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = auth.timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# Get current user info
@app.get("/users/me", response_model=schemas.User)
async def read_users_me(current_user: schemas.User = Depends(auth.get_current_user)):
    return current_user

# Buy credits (simulated)
@app.post("/buy_credits")
async def buy_credits(credits_to_add: int, current_user: schemas.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if credits_to_add <= 0:
        raise HTTPException(status_code=400, detail="Kredi miktarı pozitif olmalı.")
    updated_user = crud.update_user_credits(db, current_user, credits_to_add)
    return {"message": f"{credits_to_add} kredi eklendi.", "new_credits": updated_user.credits}

@app.post("/generate_artistic_image")
async def generate_artistic_image_endpoint(request: ImageRequest, current_user: schemas.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if not STABILITY_API_KEY or STABILITY_API_KEY == "BURAYA_YAPIŞTIRIN_sk-...":
        raise HTTPException(status_code=400, detail="Görüntü üretme özelliği (premium) aktif değil. Uygulama sahibinin bir Stability AI API anahtarı sağlaması gerekiyor.")
    
    if current_user.credits < 1:
        raise HTTPException(status_code=402, detail="Yeterli krediniz yok. Lütfen kredi satın alın.")

    try:
        image_bytes = base64.b64decode(request.image_bytes_base64)
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size
        max_dim = 1536

        if width > max_dim or height > max_dim:
            img.thumbnail((max_dim, max_dim))
            output_bytes = io.BytesIO()
            img.save(output_bytes, format="PNG")
            processed_image_bytes = output_bytes.getvalue()
        else:
            processed_image_bytes = image_bytes

        url = "https://api.stability.ai/v1/generation/stable-diffusion-v1-6/image-to-image"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {STABILITY_API_KEY}",
        }
        files = {"init_image": processed_image_bytes}
        full_prompt = (
            f"A photo in the artistic style of {request.style_prompt}, high quality, detailed."
        )
        data = {
            "image_strength": 0.5,
            "init_image_mode": "IMAGE_STRENGTH",
            "text_prompts[0][text]": full_prompt,
            "text_prompts[0][weight]": 1,
            "cfg_scale": 7,
            "samples": 1,
            "steps": 30,
        }
        response = requests.post(
            url, headers=headers, files=files, data=data, timeout=90
        )
        if response.status_code != 200:
            try:
                error_message = response.json().get("message", response.text)
            except requests.exceptions.JSONDecodeError:
                error_message = response.text
            raise HTTPException(status_code=response.status_code, detail=f"Stability AI API hatası: {error_message}")
        
        response_data = response.json()
        image_base64 = response_data["artifacts"][0]["base64"]
        
        crud.update_user_credits(db, current_user.id, -1) # Kredi düş
        return {"image_base64": image_base64}

    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="İstek zaman aşımına uğradı. Sunucu çok yavaş yanıt veriyor.")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Ağ bağlantısı sorunu: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Beklenmedik bir sorun oluştu: {e}")

@app.post("/generate_story")
async def generate_story_endpoint(request: StoryRequest, current_user: schemas.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if not GOOGLE_API_KEY or GOOGLE_API_KEY == "BURAYA_YAPIŞTIRIN_AIzaSy...":
        raise HTTPException(status_code=400, detail="Google API anahtarı bulunamadı veya ayarlanmamış.")
    
    if current_user.credits < 1:
        raise HTTPException(status_code=402, detail="Yeterli krediniz yok. Lütfen kredi satın alın.")

    try:
        image_bytes = base64.b64decode(request.image_bytes_base64)
        image_pil = Image.open(io.BytesIO(image_bytes))
        prompt = "Bu eski aile fotoğrafına bak. Sen o anıda yaşayan birisin ya da o anı gözlemleyen bir ruhsun. Nostaljik, duygusal ve kısa bir hikaye yaz. Fotoğraftaki insanların hislerini, ortamın atmosferini, söylenmemiş sözleri hayal et. Kıyafetlerden, mekandan ve fotoğrafın kalitesinden yola çıkarak dönemi (örn: 70'ler, 80'ler) tahmin et ve hikayene bu detayı kat. Hikayen samimi ve dokunaklı olsun."
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content([prompt, image_pil])
        
        crud.update_user_credits(db, current_user.id, -1) # Kredi düş
        return {"story": response.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Hikaye üretilirken bir sorun oluştu: {e}")

@app.post("/generate_soundscape")
async def generate_soundscape_endpoint(request: SoundRequest, current_user: schemas.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if not GOOGLE_API_KEY or GOOGLE_API_KEY == "BURAYA_YAPIŞTIRIN_AIzaSy...":
        raise HTTPException(status_code=400, detail="Google API anahtarı bulunamadı veya ayarlanmamış.")
    
    if current_user.credits < 1:
        raise HTTPException(status_code=402, detail="Yeterli krediniz yok. Lütfen kredi satın alın.")

    try:
        image_bytes = base64.b64decode(request.image_bytes_base64)
        
        # Adım 1: Gemini ile şiirsel ve atmosferik bir metin üret
        image_pil = Image.open(io.BytesIO(image_bytes))
        sound_prompt = (
            "Bu eski fotoğrafa bak ve bir şair gözüyle yorumla. O anın atmosferini, "
            "duygusunu ve duyulabilecek sesleri birleştirerek kısa, şiirsel bir metin yaz. "
            "Örnek: 'Geçmişin fısıltıları duyuluyor... Ahşap zeminin gıcırtısı, uzaklardan gelen bir kahkaha "
            "ve odadaki sessizliğe karışan kalp atışları...' Sadece bu edebi metni oluştur."
        )
        model = genai.GenerativeModel("gemini-1.5-flash")
        poetic_text_response = model.generate_content([sound_prompt, image_pil])
        poetic_text = poetic_text_response.text.strip()

        # Adım 2: gTTS ile metni sese dönüştür
        tts = gTTS(text=poetic_text, lang='tr', slow=False)
        audio_fp = io.BytesIO()
        tts.write_to_fp(audio_fp)
        audio_fp.seek(0)
        audio_bytes_base64 = base64.b64encode(audio_fp.read()).decode("utf-8")

        crud.update_user_credits(db, current_user.id, -1) # Kredi düş
        return {"audio_base64": audio_bytes_base64}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ses manzarası oluşturulurken beklenmedik bir sorun oluştu: {e}")
