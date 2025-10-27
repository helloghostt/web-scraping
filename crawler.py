import os
import time
import urllib.request
import openpyxl
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from datetime import datetime
import re
from config import CAFE_ID, MENU_ID, START_DATE, END_DATE, DOWNLOAD_FOLDER, SUBJECT, EXCEL_HEADER

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
    date_text = re.sub(r"[^\d.:]", "", date_text).strip()
    today = datetime.today()

    if re.match(r"^\d{1,2}:\d{2}$", date_text):
        try:
            hour, minute = map(int, date_text.split(":"))
            return today.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except:
            return None

    date_formats = ["%Y.%m.%d.", "%Y.%m.%d", "%m.%d."]
    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_text, fmt)
            if fmt == "%m.%d.":
                dt = dt.replace(year=today.year)
            return dt
        except:
            continue
    
    return None

# ---------------- 로그인 ----------------
def login_naver(driver):
    print("\n🔑 네이버 로그인 창을 엽니다. 직접 로그인 해주세요.")
    driver.get("https://nid.naver.com/nidlogin.login")
    driver.maximize_window()
    input("✋ 로그인이 완료되면 Enter 키를 누르세요... ")
    print("✅ 로그인 완료")

# ---------------- 게시글 리스트 ----------------
def get_articles_from_page(driver, page_num):
    url = f"https://cafe.naver.com/f-e/cafes/{CAFE_ID}/menus/{MENU_ID}?viewType=L&page={page_num}"
    driver.get(url)
    time.sleep(3)
    articles = []

    if page_num == 1:
        with open('debug_page.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print("  🐛 debug_page.html 생성됨")

    try:
        posts = driver.find_elements(By.CSS_SELECTOR, '.article-board.m-tcol-c:not(#upperArticleList) .article')
        if not posts:
            posts = driver.find_elements(By.CSS_SELECTOR, '.article')
            print(f"  🔍 방법2: {len(posts)}개 발견")
        if not posts:
            posts = driver.find_elements(By.CSS_SELECTOR, "a[href*='/articles/']")
            print(f"  🔍 방법3: {len(posts)}개 발견")
        if not posts:
            print(f"  ⚠️ {page_num}페이지: 게시글 없음")
            return []

        print(f"  📄 {page_num}페이지: {len(posts)}개 게시글 발견")

        for idx, post in enumerate(posts):
            try:
                href = ""
                if post.tag_name == 'a':
                    href = post.get_attribute("href")
                else:
                    link = post.find_element(By.CSS_SELECTOR, "a[href*='/articles/']")
                    href = link.get_attribute("href")
                if not href or "/articles/" not in href:
                    continue

                date_text = ""
                parent = post
                for _ in range(5):
                    parent = parent.find_element(By.XPATH, "..")
                    date_elements = parent.find_elements(By.CSS_SELECTOR, ".td_date, [class*='date'], [class*='Date']")
                    if date_elements:
                        date_text = date_elements[0].text.strip()
                        break

                if not date_text:
                    print(f"    ⚠️ {idx+1}번째 게시글: 날짜 없음")
                    continue

                post_date = parse_date(date_text)
                if not post_date:
                    print(f"    ⚠️ 날짜 파싱 실패: {date_text}")
                    continue

                if START_DATE.date() <= post_date.date() <= END_DATE.date():
                    articles.append({"url": href, "date": post_date})
                    print(f"    ✅ 수집 대상: {post_date}")
                else:
                    print(f"    ⏭️ 기간 외: {post_date}")
            except Exception as e:
                print(f"    ❌ {idx+1}번째 게시글 처리 오류: {e}")
                continue
    except Exception as e:
        print(f"  ❌ 페이지 파싱 오류: {e}")

    return articles

# ---------------- 상세페이지 정보 추출 ----------------
def extract_article_info(driver, url):
    driver.get(url)
    time.sleep(1.5)

    info = {
        "post_number": "",
        "title": "",
        "nickname": "",
        "img_urls": [],
        "url": url,
        "is_notice": False
    }

    match = re.search(r'/articles/(\d+)', url)
    if match:
        info["post_number"] = match.group(1)

    try:
        driver.switch_to.frame("cafe_main")
        time.sleep(0.5)

        # 공지 체크
        notice_selectors = [".notice-article", ".board-notice", "[class*='notice']", "[class*='Notice']", "span.icon-badge.notice", ".article-board__notice"]
        for sel in notice_selectors:
            if driver.find_elements(By.CSS_SELECTOR, sel):
                info["is_notice"] = True
                break

        # 제목
        try:
            title_elem = driver.find_element(By.CSS_SELECTOR, "h3.title_text, .tit_txt, .article_title, .title")
            title_text = title_elem.text.strip()
            if any(k in title_text for k in ["[공지]", "[필독]", "[안내]", "[NOTICE]"]):
                info["is_notice"] = True
            info["title"] = title_text
        except:
            pass

        # 닉네임
        try:
            nickname_elem = driver.find_element(By.CSS_SELECTOR, ".nickname, .nick_name")
            info["nickname"] = nickname_elem.text.strip()
        except:
            pass

        # 이미지 URL
        try:
            article_viewer = driver.find_element(By.CSS_SELECTOR, "#article_viewer, .article_viewer")
            imgs = article_viewer.find_elements(By.TAG_NAME, "img")
            for img in imgs:
                src = img.get_attribute("src") or img.get_attribute("data-src")
                if src and any(d in src for d in ["phinf.pstatic.net", "blogfiles.naver.net", "postfiles.pstatic.net", "cafeskthumb"]):
                    src = src.replace("type=w800", "type=w2000")
                    if src not in info["img_urls"]:
                        info["img_urls"].append(src)
        except:
            pass

        driver.switch_to.default_content()
    except:
        driver.switch_to.default_content()
    
    return info

# ---------------- 크롤러 ----------------
def crawl_naver_cafe():
    print("🚀 네이버 카페 크롤러 시작")
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(EXCEL_HEADER)

    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    login_naver(driver)
    time.sleep(2)

    page = 1
    total_collected = 0
    passed_end_date = False

    while page <= 100:
        print(f"🔍 {page}페이지 수집 중...")
        articles = get_articles_from_page(driver, page)
        if not articles:
            break

        for art in articles:
            if art["date"].date() < START_DATE.date():
                passed_end_date = True
                break
            if not (START_DATE.date() <= art["date"].date() <= END_DATE.date()):
                continue

            article_info = extract_article_info(driver, art["url"])
            if article_info.get("is_notice"):
                print(f"  ⏭️ 공지글 제외: {article_info['title'][:30]}")
                continue

            # 이미지 다운로드
            downloaded_images = []
            if article_info['img_urls']:
                safe_title = safe_filename(article_info['title'])
                post_num = article_info['post_number']
                total_images = len(article_info['img_urls'])

                for idx, img_url in enumerate(article_info['img_urls'], 1):
                    if total_images == 1:
                        filename = f"{post_num} {safe_title}.jpg"
                    else:
                        filename = f"{post_num} {safe_title}_{idx}.jpg"
                    filepath = os.path.join(DOWNLOAD_FOLDER, filename)
                    if download_image(img_url, filepath):
                        downloaded_images.append(img_url)

            # 이미지 저장 후 아이디 가져오기
            user_id = ""
            try:
                driver.get(article_info['url'])
                driver.switch_to.frame("cafe_main")
                time.sleep(0.5)
                profile_img = driver.find_element(By.CSS_SELECTOR, "img[alt='프로필 사진']")
                driver.execute_script("arguments[0].click();", profile_img)
                time.sleep(0.5)
                # 팝업 내 user_id 요소 대기
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC

                try:
                    user_id_elem = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".user_id"))
                    )
                    user_id = user_id_elem.text.strip()
                except:
                    user_id = ""
                try:
                    close_btn = driver.find_element(By.CSS_SELECTOR, ".layer_close, .close_btn")
                    driver.execute_script("arguments[0].click();", close_btn)
                    time.sleep(0.2)
                except:
                    pass
            except Exception as e:
                print(f"    ⚠️ 아이디 가져오기 실패: {e}")

            # 엑셀 기록
            ws.append([
                article_info['post_number'],
                article_info['title'],
                article_info['nickname'],
                user_id,
                '',
                '',
                art["date"].strftime("%Y-%m-%d"),
                article_info['url'],
                ';'.join(downloaded_images),
                len(downloaded_images)
            ])
            total_collected += 1
            time.sleep(0.8)

        if passed_end_date:
            break
        page += 1
        time.sleep(1.5)

    driver.quit()
    excel_filename = f"{START_DATE:%m}월{SUBJECT}({START_DATE:%Y%m%d}~{END_DATE:%Y%m%d}).xlsx"
    wb.save(excel_filename)
    print(f"✅ 크롤링 완료! 총 {total_collected}개 게시글 수집")
    print(f"💾 엑셀: {excel_filename}")
    print(f"📁 이미지 폴더: {DOWNLOAD_FOLDER}/")

if __name__ == "__main__":
    crawl_naver_cafe()
