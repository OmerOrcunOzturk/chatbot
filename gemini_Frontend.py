import streamlit as st
import random
import time
import chatbot_With_Gemini
from database import get_user_history, clear_all_history
import uuid

# Yardımcı fonksiyonlar
def response_generator(prompt, user_id):
    """Chatbot yanıtını oluşturur"""
    response = chatbot_With_Gemini.generate_response(prompt, user_id)
    for word in response.split():
        yield word + " "
        time.sleep(0.05)

def handle_new_chat():
    """Yeni chat işleyicisi"""
    st.session_state.current_chat_id = str(uuid.uuid4())
    st.session_state.messages = []
    st.session_state.needs_rerun = True
    chatbot_With_Gemini.clear_chat_history(st.session_state.current_chat_id)

def handle_chat_select(user_id):
    """Chat seçim işleyicisi"""
    st.session_state.current_chat_id = user_id
    st.session_state.messages = load_chat_history(user_id)
    st.session_state.needs_rerun = True

def load_chat_history(user_id):
    """Veritabanından chat geçmişini yükler"""
    history = get_user_history(user_id)
    messages = []
    for role, content in history:
        messages.append({"role": role, "content": content})
    return messages

def handle_clear_history():
    """Tüm sohbet geçmişini temizler"""
    if 'show_delete_dialog' not in st.session_state:
        st.session_state.show_delete_dialog = False

    if not st.session_state.show_delete_dialog:
        st.session_state.show_delete_dialog = True
        st.session_state.needs_rerun = True

# Sayfa düzeni
st.set_page_config(layout="wide")

# Session state'leri başlat
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = str(uuid.uuid4())
if "chat_sessions" not in st.session_state:
    st.session_state.chat_sessions = {}
if "messages" not in st.session_state:
    st.session_state.messages = []
if "needs_rerun" not in st.session_state:
    st.session_state.needs_rerun = False
if "show_delete_dialog" not in st.session_state:
    st.session_state.show_delete_dialog = False

# İki sütunlu layout oluştur
left_column, right_column = st.columns([1, 3])

with left_column:
    # Yeni Chat ve Geçmişi Temizle butonlarını yan yana yerleştir
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Yeni Chat", on_click=handle_new_chat):
            st.session_state.needs_rerun = True
    with col2:
        if st.button("Geçmişi Sil", type="secondary", on_click=handle_clear_history):
            pass

    # Silme onay dialogu
    if st.session_state.show_delete_dialog:
        st.warning("⚠️ Tüm sohbet geçmişi kalıcı olarak silinecek. Emin misiniz?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✔️ Evet, Sil", key="confirm_delete"):
                clear_all_history()
                st.session_state.messages = []
                st.session_state.show_delete_dialog = False
                st.session_state.needs_rerun = True
        with col2:
            if st.button("❌ İptal", key="cancel_delete"):
                st.session_state.show_delete_dialog = False
                st.session_state.needs_rerun = True
    
    st.markdown("---")
    st.subheader("Önceki Sohbetler")
    
    # Veritabanından benzersiz user_id'leri al
    all_history = get_user_history(None)
    unique_chats = {}
    
    for chat in all_history:
        user_id = chat[0]
        if user_id not in unique_chats:
            unique_chats[user_id] = chat[2][:30] + "..."
    
    # Her chat için bir buton oluştur
    for user_id, chat_preview in unique_chats.items():
        if st.button(f"{chat_preview}", key=f"chat_{user_id}", 
                    on_click=handle_chat_select, args=(user_id,)):
            pass

with right_column:
    # Container oluştur
    chat_container = st.container()
    
    # Başlık
    chat_container.title("Chat")
    
    # Mesaj alanı için container
    message_container = chat_container.container()
    
    # Mesajları göster
    with message_container:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
    
    # Input alanı için container (en altta)
    input_container = chat_container.container()
    
    # Kullanıcı girişini al
    with input_container:
        if prompt := st.chat_input("Ne sormak istersiniz?"):
            # Kullanıcı mesajını ekle
            st.session_state.messages.append({"role": "user", "content": prompt})
            with message_container.chat_message("user"):
                st.markdown(prompt)

            # Asistan yanıtını göster
            with message_container.chat_message("assistant"):
                response = st.write_stream(response_generator(prompt, st.session_state.current_chat_id))
            st.session_state.messages.append({"role": "assistant", "content": response})
            st.session_state.needs_rerun = True

# Sayfa yenileme kontrolü
if st.session_state.needs_rerun:
    st.session_state.needs_rerun = False
    st.rerun() 