import os
import time
import urllib.request
import openpyxl
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timedelta
import re

# ---------------- 사용자 설정값 ----------------
CAFE_ID = ""   # 카페 ID 입력 (예: 12345)
MENU_ID = ""   # 메뉴 ID 입력 (예: 67890)
START_DATE = datetime.strptime("2025-10-01", "%Y-%m-%d")
END_DATE = datetime.strptime("2025-10-06", "%Y-%m-%d")
DOWNLOAD_FOLDER = "./downloads_cafe"

# ---------------- 유틸 함수 ----------------
def safe_filename(name):
    return "".join(c for c in name if c.isalnum() or c in " _-").strip()[:30]

def download_image(url, path):
    try:
        urllib.request.urlretrieve(url, path)
        return True
    except Exception as e:
        print(f"❌ 이미지 다운로드 실패: {url} - {e}")
        return False

def parse_date(date_text):
    date_text = re.sub(r"[^\d가-힣:.\s]", "", date_text).strip()
    today = datetime.today()

    # "HH:MM" 형식
    if re.match(r"^\d{1,2}:\d{2}$", date_text):
        hour, minute = map(int, date_text.split(":"))
        return today.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # "어제 HH:MM"
    if "어제" in date_text:
        try:
            times = re.findall(r"\d{1,2}", date_text)
            if len(times) >= 2:
                hour, minute = int(times[0]), int(times[1])
                yesterday = today - timedelta(days=1)
                return yesterday.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except:
            pass

    # 일반 날짜 형식
    date_formats = [
        "%Y.%m.%d.",
        "%Y.%m.%d",
        "%Y-%m-%d",
        "%m.%d."
    ]
    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_text, fmt)
            if fmt == "%m.%d.":
                dt = dt.replace(year=today.year)
            return dt
        except:
            continue
    return None

# ---------------- 로그인 함수 ----------------
def login_naver(driver):
    """
    네이버 로그인 - 사용자 직접 로그인 방식
    (브라우저 창을 띄우고 수동 로그인 후 Enter 입력시 진행)
    """
    print("\n🔑 네이버 로그인 창을 엽니다. 직접 로그인 해주세요.")
    driver.get("https://nid.naver.com/nidlogin.login")
    driver.maximize_window()

    # 로그인 완료 대기
    while True:
        current_url = driver.current_url
        if "nid.naver.com" not in current_url:
            print("✅ 로그인 완료 감지됨.")
            break
        user_input = input("로그인이 완료되면 Enter 키를 누르세요... ")
        if "nid.naver.com" not in driver.current_url:
            break


# ---------------- 게시글 리스트 가져오기 ----------------
def get_articles_from_page(driver, page_num):
    url = f"https://cafe.naver.com/f-e/cafes/{CAFE_ID}/menus/{MENU_ID}?viewType=L&page={page_num}"
    driver.get(url)
    time.sleep(2)

    # 공지글 제외한 일반 게시글만 선택
    posts = []
    try:
        # 방법 1: upperArticleList 제외
        posts = driver.find_elements(By.CSS_SELECTOR, '.article-board.m-tcol-c:not(#upperArticleList) .article')
    except:
        pass
    
    # 방법 1이 실패하면 기존 방식 사용
    if not posts:
        selectors_to_try = [
            "a.article-link",
            "a[href*='/articles/']",
            ".ArticleItem a",
            "div[class*='ArticleItem']",
            "article a"
        ]
        
        found_selector = None
        for selector in selectors_to_try:
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    found_selector = selector
                    break
            except:
                continue
        
        if not found_selector:
            print("  ✗ 게시글 없음")
            return [], True

    time.sleep(1)

    articles = []
    stop_page = False

    # posts가 있으면 그것을 사용, 없으면 링크로 검색
    if posts:
        links = []
        for post in posts:
            try:
                link = post.find_element(By.CSS_SELECTOR, "a[href*='/articles/']")
                links.append(link)
            except:
                continue
    else:
        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/articles/']")

    for link in links:
        try:
            href = link.get_attribute("href")
            if not href or "/articles/" not in href:
                continue

            date_text = ""
            parent = link
            
            for _ in range(5):
                try:
                    parent = parent.find_element(By.XPATH, "..")
                    date_candidates = parent.find_elements(By.CSS_SELECTOR, 
                        "span, div, time, [class*='date'], [class*='Date'], [class*='time']")
                    
                    for candidate in date_candidates:
                        text = candidate.text.strip()
                        if text and (
                            re.search(r'\d{1,2}:\d{2}', text) or 
                            re.search(r'\d{4}\.\d{1,2}\.\d{1,2}', text) or
                            re.search(r'\d{1,2}\.\d{1,2}\.', text) or
                            '시간 전' in text or '분 전' in text or '어제' in text
                        ):
                            date_text = text
                            break
                    
                    if date_text:
                        break
                except:
                    break

            if not date_text:
                continue

            post_date = parse_date(date_text)
            
            if not post_date:
                continue

            try:
                title = link.text.strip()[:40] or "제목없음"
            except:
                title = "제목없음"

            if START_DATE <= post_date <= END_DATE:
                articles.append({"url": href, "date": post_date})

        except Exception as e:
            continue

    return articles, stop_page

# ---------------- 상세페이지 정보 추출 ----------------
def extract_article_info(driver, url):
    driver.get(url)
    time.sleep(1.5)

    # ------------------ [1] iframe 진입 ------------------
    try:
        driver.switch_to.frame("cafe_main")
        time.sleep(0.5)
    except:
        print("  ✗ iframe 접근 실패 (cafe_main 없음)")
        pass

    info = {
        "post_number": "",
        "title": "",
        "nickname": "",
        "img_urls": set(),
        "url": url,
        "is_notice": False
    }

    match = re.search(r'/articles/(\d+)', url)
    if match:
        info["post_number"] = match.group(1)

    # ------------------ [2] 공지글 체크 ------------------
    notice_indicators = [
        ".notice-article",
        ".board-notice",
        "[class*='notice']",
        "[class*='Notice']"
    ]
    for selector in notice_indicators:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                info["is_notice"] = True
                break
        except:
            continue

    # ------------------ [3] 제목 ------------------
    title_selectors = [
        "h3.title_text",
        "span.tit_txt",
        "#postTitleText",
        ".article_title",
        "h1.tit",
        "h2.tit",
        "h3.tit"
    ]
    for selector in title_selectors:
        try:
            elem = driver.find_element(By.CSS_SELECTOR, selector)
            text = elem.text.strip()
            if text and 1 < len(text) < 200:
                info["title"] = text
                break
        except:
            continue

    # ------------------ [4] 닉네임 ------------------
    nickname_selectors = [
        ".nickname",
        ".user",
        ".member_nick",
        "span.user",
        ".nick_area"
    ]
    for selector in nickname_selectors:
        try:
            elem = driver.find_element(By.CSS_SELECTOR, selector)
            text = elem.text.strip()
            if text:
                info["nickname"] = text
                break
        except:
            continue

    # ------------------ [5] 이미지 (article_viewer 내부만) ------------------
    article_viewer_selectors = [
        "#article_viewer",
        ".article_viewer",
        "#postContent",
        ".post_content",
        ".article-body"
    ]
    
    article_viewer = None
    for selector in article_viewer_selectors:
        try:
            article_viewer = driver.find_element(By.CSS_SELECTOR, selector)
            break
        except:
            continue
    
    if article_viewer:
        imgs = article_viewer.find_elements(By.TAG_NAME, "img")
    else:
        imgs = driver.find_elements(By.TAG_NAME, "img")
    
    for img in imgs:
        src = (
            img.get_attribute("src") or
            img.get_attribute("data-src") or
            img.get_attribute("data-lazy-src")
        )
        if src and any(domain in src for domain in [
            "phinf.pstatic.net",
            "blogfiles.naver.net",
            "postfiles.pstatic.net",
            "cafeskthumb"
        ]):
            src = src.replace("type=w800", "type=w2000")
            info["img_urls"].add(src)

    # iframe 빠져나오기
    try:
        driver.switch_to.default_content()
    except:
        pass

    return info

# ---------------- 크롤링 메인 ----------------
def crawl_naver_cafe():
    print("🚀 네이버 카페 크롤러 시작")
    print(f"카페 ID: {CAFE_ID}")
    print(f"메뉴 ID: {MENU_ID}")
    print(f"수집 기간: {START_DATE.strftime('%Y-%m-%d')} ~ {END_DATE.strftime('%Y-%m-%d')}")
    
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["게시물번호", "제목", "닉네임", "아이디", "지사", "교사", "작성일", "링크", "이미지링크", "이미지수"])

    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    # 로그인 시도
    login_naver(driver)
    time.sleep(2)

    page = 1
    post_index = 1
    total_collected = 0
    consecutive_empty_pages = 0

    while page <= 100:
        articles, stop_page = get_articles_from_page(driver, page)
        
        if not articles:
            consecutive_empty_pages += 1
            if page == 1:
                print("\n❌ 게시글을 찾을 수 없습니다")
                break
            elif consecutive_empty_pages >= 3:
                break
            else:
                page += 1
                time.sleep(2)
                continue
        
        consecutive_empty_pages = 0

        for art in articles:
            article_info = extract_article_info(driver, art["url"])
            
            if not article_info:
                continue
            
            # 3️⃣ 공지글이면 건너뛰기
            if article_info.get("is_notice", False):
                continue
            
            title = article_info.get("title", "")

            # 이미지 다운로드
            downloaded_images = []
            if article_info['img_urls']:
                for idx, img_url in enumerate(article_info['img_urls'], 1):
                    safe_title = safe_filename(title) if title else f"post_{post_index}"
                    post_num = article_info.get('post_number', f"{post_index:04d}")
                    filename = f"{post_num}_{safe_title}_{idx}.jpg"
                    filepath = os.path.join(DOWNLOAD_FOLDER, filename)
                    if download_image(img_url, filepath):
                        downloaded_images.append(img_url)

            ws.append([
                article_info.get('post_number', ''),
                article_info.get('title', ''),
                article_info.get('nickname', ''),
                '', '', '',
                art["date"].strftime("%Y%m%d"),
                article_info.get('url', ''),
                ';'.join(downloaded_images),
                len(downloaded_images)
            ])

            post_index += 1
            total_collected += 1
            time.sleep(0.5)

        if stop_page:
            break

        page += 1
        time.sleep(1)

    driver.quit()
    
    excel_filename = f"naver_cafe_crawl_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    wb.save(excel_filename)
    
    print("\n✅ 크롤링 완료!")
    print(f"📊 총 {total_collected}개 게시글 수집")
    print(f"💾 엑셀: {excel_filename}")
    print(f"📁 이미지: {DOWNLOAD_FOLDER}/")

if __name__ == "__main__":
    crawl_naver_cafe()