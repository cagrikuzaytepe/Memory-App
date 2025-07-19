from fastapi import FastAPI, HTTPException, Depends, status
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

# src klasör yapısına göre düzeltilmiş importlar
from src import models, schemas, crud, auth, database

# Veritabanı tablolarını oluştur
models.Base.metadata.create_all(bind=database.engine)

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
    db = database.SessionLocal()
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
    access_token = auth.create_access_token(
        data={"sub": user.username}
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
        raise HTTPException(status_code=400, detail="Credit amount must be positive.")
    updated_user = crud.update_user_credits(db, user_id=current_user.id, amount=-1)
    return {"message": f"{credits_to_add} credits added.", "new_credits": updated_user.credits}

@app.post("/generate_artistic_image")
async def generate_artistic_image_endpoint(request: ImageRequest, current_user: schemas.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if not STABILITY_API_KEY:
        raise HTTPException(status_code=500, detail="Image generation feature is not configured by the administrator.")

    if current_user.credits < 1:
        raise HTTPException(status_code=402, detail="Not enough credits. Please buy more.")

    try:
        image_bytes = base64.b64decode(request.image_bytes_base64)

        url = "https://api.stability.ai/v1/generation/stable-diffusion-v1-6/image-to-image"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {STABILITY_API_KEY}",
        }
        files = {"init_image": image_bytes}
        data = {
            "image_strength": 0.35,
            "init_image_mode": "IMAGE_STRENGTH",
            "text_prompts[0][text]": request.style_prompt,
            "cfg_scale": 7,
            "samples": 1,
            "steps": 30,
        }

        response = requests.post(url, headers=headers, files=files, data=data, timeout=90)
        response.raise_for_status()

        response_data = response.json()
        image_base64 = response_data["artifacts"][0]["base64"]

        crud.update_user_credits(db, user_id=current_user.id, credits_to_add=-1)
        return {"image_base64": image_base64}

    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Request timed out. The server took too long to respond.")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Network connection issue: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@app.post("/generate_story")
async def generate_story_endpoint(request: StoryRequest, current_user: schemas.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="Google API key not found or set up.")

    if current_user.credits < 1:
        raise HTTPException(status_code=402, detail="Not enough credits. Please buy more.")

    try:
        image_bytes = base64.b64decode(request.image_bytes_base64)
        image_pil = Image.open(io.BytesIO(image_bytes))
        prompt = "Look at this old family photo. You are someone living in that memory or a spirit observing it. Write a short, nostalgic, and emotional story. Imagine the feelings of the people in the photo, the atmosphere of the place, the unspoken words. Guess the era (e.g., 70s, 80s) from the clothes, the location, and the quality of the photo, and add this detail to your story. Your story should be sincere and touching."
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content([prompt, image_pil])

        crud.update_user_credits(db, user_id=current_user.id, credits_to_add=-1)
        return {"story": response.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred while generating the story: {e}")

@app.post("/generate_soundscape")
async def generate_soundscape_endpoint(request: SoundRequest, current_user: schemas.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="Google API key not found or set up.")

    if current_user.credits < 1:
        raise HTTPException(status_code=402, detail="Not enough credits. Please buy more.")

    try:
        image_bytes = base64.b64decode(request.image_bytes_base64)

        # Adım 1: Gemini ile şiirsel ve atmosferik bir metin üret
        image_pil = Image.open(io.BytesIO(image_bytes))
        sound_prompt = (
            "Look at this old photo and interpret it with a poet's eye. "
            "Write a short, poetic text that combines the atmosphere of the moment, "
            "the emotion, and the conceivable sounds. "
            "Example: 'Whispers of the past are heard... the creak of the wooden floor, a distant laugh "
            "and heartbeats mingling with the silence in the room...' Only create this literary text."
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

        crud.update_user_credits(db, user_id=current_user.id, credits_to_add=-1)
        return {"audio_base64": audio_bytes_base64}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred while creating the soundscape: {e}")
