import streamlit as st
from PIL import Image
import io
import os
import requests
import base64

# .env dosyasını yükle (özellikle yerel test için)
from dotenv import load_dotenv

load_dotenv()

# Backend API URL'i
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# Streamlit sayfa yapılandırması
st.set_page_config(page_title="Canlı Anılar", page_icon="🖼️", layout="wide")

# --- KULLANICI YÖNETİMİ VE OTURUM --- #

if "token" not in st.session_state:
    st.session_state.token = None
if "username" not in st.session_state:
    st.session_state.username = None
if "credits" not in st.session_state:
    st.session_state.credits = 0


def register_user(username, password):
    try:
        response = requests.post(
            f"{BACKEND_URL}/register", json={"username": username, "password": password}
        )
        response.raise_for_status()
        st.success("Kayıt başarılı! Lütfen giriş yapın.")
        return True
    except requests.exceptions.HTTPError as e:
        st.error(f"Kayıt hatası: {e.response.json().get('detail', 'Bilinmeyen hata.')}")
        return False
    except Exception as e:
        st.error(f"Beklenmedik bir hata oluştu: {e}")
        return False


def login_user(username, password):
    try:
        response = requests.post(
            f"{BACKEND_URL}/token", data={"username": username, "password": password}
        )
        response.raise_for_status()
        token_data = response.json()
        st.session_state.token = token_data["access_token"]
        st.session_state.username = username
        st.success(f"Hoş geldiniz, {username}!")
        fetch_user_info()
        return True
    except requests.exceptions.HTTPError as e:
        st.error(
            f"Giriş hatası: {e.response.json().get('detail', 'Kullanıcı adı veya şifre hatalı.')}"
        )
        return False
    except Exception as e:
        st.error(f"Beklenmedik bir hata oluştu: {e}")
        return False


def logout_user():
    st.session_state.token = None
    st.session_state.username = None
    st.session_state.credits = 0
    st.success("Çıkış yapıldı.")
    st.rerun()


def fetch_user_info():
    if st.session_state.token:
        try:
            headers = {"Authorization": f"Bearer {st.session_state.token}"}
            response = requests.get(f"{BACKEND_URL}/users/me", headers=headers)
            response.raise_for_status()
            user_info = response.json()
            st.session_state.credits = user_info["credits"]
        except requests.exceptions.RequestException as e:
            st.error(f"Kullanıcı bilgileri çekilirken hata: {e}")
            logout_user()  # Hata durumunda çıkış yap


def buy_credits_simulated(amount):
    if st.session_state.token:
        try:
            headers = {"Authorization": f"Bearer {st.session_state.token}"}
            response = requests.post(
                f"{BACKEND_URL}/buy_credits?credits_to_add={amount}", headers=headers
            )
            response.raise_for_status()
            result = response.json()
            st.success(result["message"])
            st.session_state.credits = result["new_credits"]
        except requests.exceptions.HTTPError as e:
            st.error(
                f"Kredi satın alma hatası: {e.response.json().get('detail', 'Bilinmeyen hata.')}"
            )
        except Exception as e:
            st.error(f"Beklenmedik bir hata oluştu: {e}")
    else:
        st.warning("Kredi satın almak için giriş yapmalısınız.")


# --- ARAYÜZ --- #

# Kenar çubuğu (Sidebar)
with st.sidebar:
    st.image("https://i.imgur.com/G5l4KxS.png", width=100)  # Basit bir logo
    st.title("Canlı Anılar")
    st.markdown("---")

    if st.session_state.token:
        st.write(f"Hoş geldiniz, **{st.session_state.username}**")
        st.metric(label="Kalan Kredi Hakkınız", value=f"{st.session_state.credits} 💖")
        if st.button("Çıkış Yap"):
            logout_user()
        st.markdown("---")
        st.subheader("Kredi Satın Al")
        if st.button("10 Kredi Satın Al ($5)"):  # Simüle edilmiş
            buy_credits_simulated(10)
    else:
        st.subheader("Giriş Yap / Kayıt Ol")
        login_tab, register_tab = st.tabs(["Giriş Yap", "Kayıt Ol"])
        with login_tab:
            login_username = st.text_input("Kullanıcı Adı", key="login_username")
            login_password = st.text_input(
                "Şifre", type="password", key="login_password"
            )
            if st.button("Giriş Yap", key="do_login_btn"):
                login_user(login_username, login_password)
        with register_tab:
            register_username = st.text_input("Kullanıcı Adı", key="register_username")
            register_password = st.text_input(
                "Şifre", type="password", key="register_password"
            )
            if st.button("Kayıt Ol", key="do_register_btn"):
                register_user(register_username, register_password)

    st.markdown("---")
    st.info(
        "Bu proje, eski fotoğraflarınıza yapay zeka ile yeni bir hayat vermek için tasarlanmıştır. "
        "Her bir 'üretim' işlemi (tablo, hikaye, ses) 1 kredi kullanır."
    )


st.title("🖼️ Canlı Anılar: Anılarınızı Sanata Dönüştürün")
st.markdown(
    "Tozlu albümlerde unutulmuş değerli bir aile fotoğrafınızı yükleyin ve yapay zekanın sihrini izleyin."
)

# Kullanıcı giriş yapmamışsa ana içeriği gösterme
if not st.session_state.token:
    st.info("Devam etmek için lütfen giriş yapın veya kayıt olun.")
else:
    # Dosya yükleme alanı
    uploaded_file = st.file_uploader(
        "Lütfen .jpg, .jpeg veya .png formatında bir fotoğraf yükleyin",
        type=["jpg", "jpeg", "png"],
    )

    if uploaded_file is not None:
        # Yüklenen dosyayı byte olarak oku ve base64'e çevir
        image_bytes = uploaded_file.getvalue()
        image_bytes_base64 = base64.b64encode(image_bytes).decode("utf-8")

        st.markdown("---")
        st.subheader("Yüklenen Anı")
        st.image(image_bytes, width=400, caption="Orijinal Fotoğraf")

        st.markdown("---")
        st.subheader("✨ Yapay Zeka ile Anınızı Canlandırın")

        col1, col2, col3 = st.columns(3, gap="large")

        # --- SÜTUN 1: Sanatsal Tablo (Premium Özellik) ---
        with col1:
            st.markdown("#### 1. Sanatsal Tabloya Dönüştür")
            style = st.selectbox(
                "Hangi stilde bir tablo istersiniz?",
                (
                    "Sulu Boya (Watercolor painting)",
                    "Yağlı Boya (Oil painting)",
                    "Çizgi Roman (Comic book art)",
                    "Dijital Sanat (Digital art)",
                    "Piksel Sanat (Pixel art)",
                ),
                key="style_select",
            )

            if st.button("🎨 Tablo Oluştur", key="btn_art"):
                if st.session_state.credits < 1:
                    st.warning("Yeterli krediniz yok. Lütfen kredi satın alın.")
                else:
                    with st.spinner(
                        "Sanatçımız fırçasını hazırlıyor... Lütfen bekleyin."
                    ):
                        try:
                            style_prompt = style.split("(")[1][
                                :-1
                            ]  # Parantez içindeki ingilizce metni al

                            headers = {
                                "Authorization": f"Bearer {st.session_state.token}"
                            }
                            response = requests.post(
                                f"{BACKEND_URL}/generate_artistic_image",
                                headers=headers,
                                json={
                                    "image_bytes_base64": image_bytes_base64,
                                    "style_prompt": style_prompt,
                                },
                            )
                            response.raise_for_status()  # HTTP hatalarını yakala (4xx, 5xx)
                            result = response.json()

                            if "image_base64" in result:
                                artistic_image_bytes = base64.b64decode(
                                    result["image_base64"]
                                )
                                st.image(
                                    artistic_image_bytes,
                                    caption=f"Yapay Zeka Yorumu: {style.split('(')[0]}",
                                )
                                fetch_user_info()  # Kredi güncellemeyi çek
                            else:
                                st.error(
                                    "Tablo oluşturulamadı. Beklenmedik bir yanıt alındı."
                                )
                        except (
                            requests.exceptions.HTTPError
                        ) as e:  # HTTP 4xx/5xx hataları
                            st.error(f"API isteği hatası: {e}")
                            if e.response is not None:  # Yanıt objesi varsa
                                try:
                                    error_detail = e.response.json().get(
                                        "detail", "Bilinmeyen hata."
                                    )
                                    st.error(f"Detay: {error_detail}")
                                except requests.exceptions.JSONDecodeError:
                                    st.error(f"Detay: {e.response.text}")
                            else:
                                st.error("Sunucudan yanıt alınamadı.")
                        except (
                            requests.exceptions.ConnectionError
                        ) as e:  # Bağlantı hataları
                            st.error(
                                f"Bağlantı hatası: Backend sunucusuna ulaşılamadı. Lütfen backend'in çalıştığından emin olun. Detay: {e}"
                            )
                        except requests.exceptions.Timeout as e:  # Zaman aşımı hataları
                            st.error(
                                f"Zaman aşımı hatası: Backend sunucusu çok yavaş yanıt veriyor. Detay: {e}"
                            )
                        except (
                            requests.exceptions.RequestException
                        ) as e:  # Diğer istek hataları
                            st.error(f"Genel API isteği hatası: {e}")
                        except Exception as e:  # Beklenmedik diğer hatalar
                            st.error(f"Beklenmedik bir hata oluştu: {e}")

        # --- SÜTUN 2: Kısa Hikaye ---
        with col2:
            st.markdown("#### 2. O Anın Hikayesini Yazdır")
            if st.button("✒️ Hikaye Yaz", key="btn_story"):
                if st.session_state.credits < 1:
                    st.warning("Yeterli krediniz yok. Lütfen kredi satın alın.")
                else:
                    with st.spinner("Yazarımız ilham perilerini çağırıyor..."):
                        try:
                            headers = {
                                "Authorization": f"Bearer {st.session_state.token}"
                            }
                            response = requests.post(
                                f"{BACKEND_URL}/generate_story",
                                headers=headers,
                                json={"image_bytes_base64": image_bytes_base64},
                            )
                            response.raise_for_status()
                            result = response.json()
                            if "story" in result:
                                st.markdown(result["story"])
                                fetch_user_info()  # Kredi güncellemeyi çek
                            else:
                                st.error(
                                    "Hikaye oluşturulamadı. Beklenmedik bir yanıt alındı."
                                )
                        except requests.exceptions.HTTPError as e:
                            st.error(f"API isteği hatası: {e}")
                            if e.response is not None:
                                try:
                                    error_detail = e.response.json().get(
                                        "detail", "Bilinmeyen hata."
                                    )
                                    st.error(f"Detay: {error_detail}")
                                except requests.exceptions.JSONDecodeError:
                                    st.error(f"Detay: {e.response.text}")
                            else:
                                st.error("Sunucudan yanıt alınamadı.")
                        except requests.exceptions.ConnectionError as e:
                            st.error(
                                f"Bağlantı hatası: Backend sunucusuna ulaşılamadı. Lütfen backend'in çalıştığından emin olun. Detay: {e}"
                            )
                        except requests.exceptions.Timeout as e:
                            st.error(
                                f"Zaman aşımı hatası: Backend sunucusu çok yavaş yanıt veriyor. Detay: {e}"
                            )
                        except requests.exceptions.RequestException as e:
                            st.error(f"Genel API isteği hatası: {e}")
                        except Exception as e:
                            st.error(f"Beklenmedik bir hata oluştu: {e}")

        # --- SÜTUN 3: Ses Manzarası ---
        with col3:
            st.markdown("#### 3. O Anın Sesini Hayal Et")
            if st.button("🔊 Ses Manzarası Oluştur", key="btn_sound"):
                if st.session_state.credits < 1:
                    st.warning("Yeterli krediniz yok. Lütfen kredi satın alın.")
                else:
                    with st.spinner(
                        "Ses mühendisimiz geçmişe kulak veriyor... Bu işlem 1-2 dakika sürebilir."
                    ):
                        try:
                            headers = {
                                "Authorization": f"Bearer {st.session_state.token}"
                            }
                            response = requests.post(
                                f"{BACKEND_URL}/generate_soundscape",
                                headers=headers,
                                json={"image_bytes_base64": image_bytes_base64},
                            )
                            response.raise_for_status()
                            result = response.json()
                            if "audio_base64" in result:
                                audio_data = base64.b64decode(result["audio_base64"])
                                st.audio(
                                    audio_data, format="audio/mpeg"
                                )  # gTTS mp3 döndürüyor
                                st.info("İpucu: En iyi deneyim için kulaklık kullanın.")
                                fetch_user_info()  # Kredi güncellemeyi çek
                            else:
                                st.error(
                                    "Ses manzarası oluşturulamadı. Beklenmedik bir yanıt alındı."
                                )
                        except requests.exceptions.HTTPError as e:
                            st.error(f"API isteği hatası: {e}")
                            if e.response is not None:
                                try:
                                    error_detail = e.response.json().get(
                                        "detail", "Bilinmeyen hata."
                                    )
                                    st.error(f"Detay: {error_detail}")
                                except requests.exceptions.JSONDecodeError:
                                    st.error(f"Detay: {e.response.text}")
                            else:
                                st.error("Sunucudan yanıt alınamadı.")
                        except requests.exceptions.ConnectionError as e:
                            st.error(
                                f"Bağlantı hatası: Backend sunucusuna ulaşılamadı. Lütfen backend'in çalıştığından emin olun. Detay: {e}"
                            )
                        except requests.exceptions.Timeout as e:
                            st.error(
                                f"Zaman aşımı hatası: Backend sunucusu çok yavaş yanıt veriyor. Detay: {e}"
                            )
                        except requests.exceptions.RequestException as e:
                            st.error(f"Genel API isteği hatası: {e}")
                        except Exception as e:
                            st.error(f"Beklenmedik bir hata oluştu: {e}")
