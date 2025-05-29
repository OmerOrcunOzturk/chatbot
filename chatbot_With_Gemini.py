import os
import sys
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, quote
from queue import Queue
import time
import streamlit as st  # Streamlit'i import et
import logging

# Logging ayarları
logging.basicConfig(
    filename='webscraping.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Modül yolunu ekle
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from google import genai
from google.genai import types
from database import init_db, save_message, get_user_history

# Veritabanını başlat
init_db()

# Global değişkenler
client = genai.Client(
    api_key="AIzaSyDHVdeeOK0KnJMVoxpvmnXumetpOSRBST4",
)
model = "gemini-2.0-flash"
contents = [
    types.Content(
        role="user",
        parts=[
            types.Part.from_text(text="""hello, who are you?"""),
        ],
    ),
]
generate_content_config = types.GenerateContentConfig(
    temperature=1,
    top_p=0.95,
    top_k=40,
    max_output_tokens=8192,
    response_mime_type="text/plain",
)

# Global değişkenler
chat_histories = {}  # Her chat ID için ayrı geçmiş tutacak sözlük

# Global değişkenlere website içeriğini ekle
WEBSITE_CONTENT = ""

def check_robots_txt(base_url):
    """robots.txt kontrolü yapar"""
    try:
        robots_url = urljoin(base_url, '/robots.txt')
        response = requests.get(robots_url)
        return 'Disallow: /' not in response.text
    except:
        return False

def get_all_links(soup, base_url, base_domain):
    """Sayfadaki tüm geçerli linkleri bulur"""
    links = set()
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        full_url = urljoin(base_url, href)
        if is_valid_url(full_url, base_domain):
            links.add(full_url)
    return links

def fetch_website_content(url):
    """Tek bir sayfadan içerik çeker"""
    try:
        # robots.txt kontrolü
        if not check_robots_txt(url):
            print(f"Bu site ({url}) web scraping'e izin vermiyor.")
            return None, ""

        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; MyBot/1.0; +http://example.com/bot)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Gereksiz HTML elementlerini temizle
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        
        # Ana içeriği al
        main_content = soup.find('main') or soup.find('article') or soup.find('body')
        return soup, main_content.get_text(separator='\n', strip=True)
    except Exception as e:
        print(f"Error fetching content from {url}: {e}")
        return None, ""

def crawl_website(base_url, max_pages=50):
    """Websitesini crawl eder ve tüm içeriği toplar"""
    try:
        # Base domain'i al
        base_domain = urlparse(base_url).netloc
        
        # Ziyaret edilecek ve edilmiş URL'leri takip et
        visited_urls = set()
        url_queue = Queue()
        url_queue.put(base_url)
        
        all_content = []
        page_count = 0
        
        print('Website içeriği toplanıyor...')  # st.spinner yerine print kullan
        
        while not url_queue.empty() and page_count < max_pages:
            current_url = url_queue.get()
            
            if current_url in visited_urls:
                continue
                
            # İçeriği çek
            soup, content = fetch_website_content(current_url)
            if soup and content:
                all_content.append(f"Page URL: {current_url}\n{content}\n{'='*50}\n")
                visited_urls.add(current_url)
                page_count += 1
                
                # Yeni linkleri bul ve kuyruğa ekle
                new_links = get_all_links(soup, current_url, base_domain)
                for link in new_links:
                    if link not in visited_urls:
                        url_queue.put(link)
            
            # İlerleme göster
            print(f"İşlenen sayfa: {page_count}/{max_pages}")
            
            # Rate limiting
            time.sleep(2)  # Her istek arasında 2 saniye bekle
        
        return "\n".join(all_content)
    
    except Exception as e:
        print(f"Hata oluştu: {str(e)}")
        return ""

def is_valid_url(url, base_domain):
    """URL'nin geçerli ve aynı domain'de olup olmadığını kontrol eder"""
    try:
        parsed = urlparse(url)
        return parsed.netloc == base_domain
    except:
        return False

def update_website_content(url, max_pages=50):
    """Website içeriğini günceller"""
    global WEBSITE_CONTENT
    logging.info(f"Website içeriği güncelleniyor: {url}")
    WEBSITE_CONTENT = crawl_website(url, max_pages)
    logging.info("Website içeriği güncellendi")

def generate_response(prompt, chat_id="default_user"):
    global chat_histories
    
    # Chat geçmişini al veya yeni oluştur
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []
        # Veritabanından geçmişi yükle
        db_history = get_user_history(chat_id)
        chat_histories[chat_id].extend(db_history)
    
    try:
        # System prompt
        system_prompt = "You are a chatbot for World of Warcraft game. Answer questions in a friendly and informative way."

        # Konuşma geçmişini oluştur
        full_prompt = system_prompt + "\n\n"

        # Geçmiş konuşmaları ekle
        for role, text in chat_histories[chat_id]:
            full_prompt += f"{role}: {text}\n"

        # Yeni soruyu ekle
        full_prompt += f"user: {prompt}\n"

        # İçeriği oluştur
        contents[0].parts[0].text = full_prompt

        # Yanıtı al
        response_text = ""
        response = client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=generate_content_config,
        )
        for chunk in response:
            if hasattr(chunk, 'text'):
                response_text += chunk.text

        # Geçmişe ekle ve veritabanına kaydet
        chat_histories[chat_id].append(("user", prompt))
        chat_histories[chat_id].append(("assistant", response_text))
        
        # Veritabanına kaydet
        save_message(chat_id, "user", prompt)
        save_message(chat_id, "assistant", response_text)

        return response_text
    except Exception as e:
        return f"Bir hata oluştu: {str(e)}"

def clear_chat_history(chat_id):
    """Belirli bir chat'in geçmişini temizler"""
    global chat_histories
    if chat_id in chat_histories:
        chat_histories[chat_id] = []

def load_chat_history(chat_id):
    """Veritabanından chat geçmişini yükler"""
    global chat_histories
    chat_histories[chat_id] = list(get_user_history(chat_id))
    return chat_histories[chat_id]

def search_fandom(fandom_url, search_term):
    """Fandom sitesinde arama yapar ve sonuçları getirir"""
    try:
        # Fandom URL'sini düzenle
        if not fandom_url.endswith('/'):
            fandom_url += '/'
        
        # Arama URL'sini oluştur
        search_url = f"{fandom_url}Special:Search?query={quote(search_term)}"
        
        # Arama sayfasını getir
        response = requests.get(search_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Arama sonuçlarını bul
        search_results = soup.find_all('a', class_='unified-search__result__title')
        
        all_content = []
        
        # İlk 3 sonucu işle
        for result in search_results[:3]:
            article_url = result['href']
            
            # Makale içeriğini getir
            article_response = requests.get(article_url)
            article_soup = BeautifulSoup(article_response.text, 'html.parser')
            
            # Ana içerik bölümünü bul
            content_div = article_soup.find('div', class_='mw-parser-output')
            
            if content_div:
                # Gereksiz elementleri temizle
                for unwanted in content_div.find_all(['script', 'style', 'div', 'table']):
                    unwanted.decompose()
                
                # Başlık ve içeriği al
                title = article_soup.find('h1', id='firstHeading')
                title_text = title.text if title else "Başlık bulunamadı"
                
                # İçeriği temizle ve ekle
                content_text = content_div.get_text(separator='\n', strip=True)
                all_content.append(f"=== {title_text} ===\n{content_text}\n")
        
        return "\n\n".join(all_content)
    
    except Exception as e:
        print(f"Hata oluştu: {str(e)}")
        return ""

def update_fandom_content(fandom_url, search_term):
    """Fandom içeriğini günceller"""
    global WEBSITE_CONTENT
    WEBSITE_CONTENT = search_fandom(fandom_url, search_term)

# Test için
print("Database functions imported successfully")
