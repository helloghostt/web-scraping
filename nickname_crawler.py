
import time
import openpyxl
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from datetime import datetime
import re

# ---------------- 설정 ----------------
CAFE_ID = "23788550"
MENU_ID = "429"
START_DATE = datetime.strptime("2025-11-17", "%Y-%m-%d")
END_DATE = datetime.today()
EXCEL_HEADER = ["닉네임", "작성일 목록"]  # ✅ 구조 변경

# ---------------- 날짜 파싱 ----------------
def parse_date(date_text):
    """게시글 날짜 문자열을 datetime으로 변환"""
    date_text = re.sub(r"[^\d.:]", "", date_text).strip()
    today = datetime.today()

    if re.match(r"^\d{1,2}:\d{2}$", date_text):  # 오늘 글의 'HH:MM'
        hour, minute = map(int, date_text.split(":"))
        return today.replace(hour=hour, minute=minute, second=0, microsecond=0)

    for fmt in ["%Y.%m.%d.", "%Y.%m.%d", "%m.%d."]:
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
    print("✅ 로그인 완료\n")

# ---------------- 닉네임 수집 ----------------
def collect_nicknames():
    print("🚀 네이버 카페 닉네임/작성일 수집 시작")

    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    login_naver(driver)
    time.sleep(2)

    page = 1
    nickname_dict = {}  # {닉네임: set(작성일)}

    while page <= 100:
        print(f"📄 {page}페이지 처리 중...")
        url = f"https://cafe.naver.com/f-e/cafes/{CAFE_ID}/menus/{MENU_ID}?viewType=L&page={page}"
        driver.get(url)
        time.sleep(2.5)

        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        if not rows:
            print("⚠️ 게시글 없음 - 종료")
            break

        stop_flag = False

        for row in rows:
            try:
                text = row.text.strip()
                # 공지글 제외
                if any(k in text for k in ["공지", "[공지]", "[필독]", "Notice", "[Notice]"]):
                    continue

                # 날짜
                date_elem = row.find_elements(By.CSS_SELECTOR, ".td_date, td.td_date, [class*='date']")
                if not date_elem:
                    continue
                date_text = date_elem[0].text.strip()
                post_date = parse_date(date_text)
                if not post_date:
                    continue

                # 날짜 필터
                if post_date.date() < START_DATE.date():
                    stop_flag = True
                    break
                if post_date.date() > END_DATE.date():
                    continue

                # 닉네임
                nick_elem = row.find_elements(By.CSS_SELECTOR, ".p-nick, .m-tcol-c, .inner_name, .nickname, .writer")
                if not nick_elem:
                    continue
                nickname = nick_elem[0].text.strip()
                if not nickname:
                    continue

                # 닉네임별로 날짜 저장
                if nickname not in nickname_dict:
                    nickname_dict[nickname] = set()
                nickname_dict[nickname].add(post_date.strftime("%Y-%m-%d"))

            except Exception as e:
                print(f"  ⚠️ 행 처리 오류: {e}")
                continue

        if stop_flag:
            print("📅 시작일 이전 글 도달, 종료합니다.")
            break

        page += 1
        time.sleep(1.5)

    driver.quit()

    # 엑셀 저장
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(EXCEL_HEADER)

    for nick, dates in sorted(nickname_dict.items()):
        date_list = ", ".join(sorted(dates))
        ws.append([nick, date_list])

    filename = f"닉네임_({START_DATE:%Y%m%d}~{END_DATE:%Y%m%d}).xlsx"
    wb.save(filename)

    print(f"\n✅ 완료! 총 {len(nickname_dict)}명 수집됨")
    print(f"💾 엑셀 저장: {filename}")

# ---------------- 실행 ----------------
if __name__ == "__main__":
    collect_nicknames()
