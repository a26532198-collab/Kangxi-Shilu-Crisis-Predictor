#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
강희제실록 (聖祖仁皇帝實錄) 전체 한자 단어 빈도 추출기
출처: https://sillok.history.go.kr/mc/
총 760개월 (1661년~1722년)

사용 방법:
  1. 필요 패키지 설치: pip install jieba beautifulsoup4
  2. 같은 폴더에 kangxi_months.json 파일 필요
  3. python kangxi_full_scraper.py 실행
  4. output_csv/ 폴더에 월별 CSV 파일 생성됨
  5. 중단 후 재실행 시 자동으로 이어서 진행 (checkpoint.json)
"""

import ssl, socket, time, re, json, csv, os
from collections import Counter
from bs4 import BeautifulSoup
import jieba
import logging
import urllib.parse
from datetime import datetime

# ─── 로깅 ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[
        logging.FileHandler('kangxi_scraper.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logging.getLogger('jieba').setLevel(logging.WARNING)
log = logging.getLogger(__name__)

# ─── 설정 ──────────────────────────────────────────────────────────────────
OUTPUT_DIR      = "output_csv"
CHECKPOINT_FILE = "checkpoint.json"
DELAY           = 1.2   # 요청 간격(초) - 서버 부하 방지
MAX_RETRY       = 6
RETRY_WAIT      = 4

# ─── SSL 연결 ───────────────────────────────────────────────────────────────
def make_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE
    ctx.set_ciphers('ALL:@SECLEVEL=0')
    return ctx

def _raw_request(method, path, body=None, retries=MAX_RETRY):
    """저수준 HTTP/TLS 요청 (SSL 버전 문제 우회)"""
    headers = (
        f"{method} {path} HTTP/1.1\r\n"
        "Host: sillok.history.go.kr\r\n"
        "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\r\n"
        "Accept: text/html,application/xhtml+xml,application/xml\r\n"
        "Accept-Language: ko-KR,ko;q=0.9,zh-CN;q=0.8\r\n"
    )
    if body:
        headers += (
            "Content-Type: application/x-www-form-urlencoded\r\n"
            f"Content-Length: {len(body)}\r\n"
        )
    headers += "Connection: close\r\n\r\n"

    for attempt in range(retries):
        try:
            ctx = make_ctx()
            raw = socket.create_connection(('sillok.history.go.kr', 443), timeout=30)
            ssl_s = ctx.wrap_socket(raw, server_hostname='sillok.history.go.kr')
            payload = headers.encode()
            if body:
                payload += body
            ssl_s.sendall(payload)
            chunks = []
            while True:
                c = ssl_s.recv(8192)
                if not c:
                    break
                chunks.append(c)
            ssl_s.close()
            data = b''.join(chunks)
            sep = data.find(b'\r\n\r\n')
            resp_body = data[sep+4:] if sep >= 0 else data
            return resp_body.decode('utf-8', errors='replace')
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(RETRY_WAIT)
            else:
                log.warning(f"      ⚠ {method} {path} 실패: {e}")
    return None

def fetch_get(path):
    return _raw_request('GET', path)

def fetch_post(path, params):
    body = urllib.parse.urlencode(params, encoding='utf-8').encode('utf-8')
    return _raw_request('POST', path, body)

# ─── 텍스트 추출 ────────────────────────────────────────────────────────────
def extract_text(html):
    """기사 페이지 HTML에서 한자 본문 추출"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # 1순위: div.view-text
    vt = soup.find('div', class_='view-text')
    if vt:
        return vt.get_text(' ', strip=True)
    
    # 2순위: div.view-area 내 p 태그
    va = soup.find('div', class_='view-area')
    if va:
        parts = [p.get_text(' ', strip=True) for p in va.find_all('p')]
        text = ' '.join(p for p in parts if p)
        if text:
            return text
    
    # 3순위: 한자 포함 p 태그 전체
    parts = []
    for p in soup.find_all('p'):
        t = p.get_text(' ', strip=True)
        if sum(1 for c in t if '\u4e00' <= c <= '\u9fff') > 5:
            parts.append(t)
    return ' '.join(parts)

def get_record_ids(daylist_html):
    """월별 기사목록 HTML에서 강희제 기사 ID 추출"""
    pattern = r"searchView\s*\(\s*'(qsilok_005_[^']+)'\s*\)"
    ids = re.findall(pattern, daylist_html)
    return list(dict.fromkeys(ids))  # 순서 유지 중복 제거

# ─── 중국어 분절 ────────────────────────────────────────────────────────────
def tokenize(text):
    """
    한자 텍스트 → 단어 리스트
    jieba 형태소 분석 사용 (단일 한자 포함)
    """
    cn = ''.join(c for c in text if '\u4e00' <= c <= '\u9fff')
    if not cn:
        return []
    return [
        w for w in jieba.cut(cn, cut_all=False)
        if len(w) >= 1 and all('\u4e00' <= c <= '\u9fff' for c in w)
    ]

# ─── 체크포인트 ─────────────────────────────────────────────────────────────
def load_cp():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"completed": []}

def save_cp(cp):
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(cp, f, ensure_ascii=False, indent=2)

# ─── CSV 저장 ───────────────────────────────────────────────────────────────
def save_csv(month_label, counts):
    """월별 CSV 저장 (파일명 예: 1661년_01월.csv, 1661년_윤07월.csv)"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    safe = month_label.replace(' ', '_')
    m = re.search(r'(\d+)월', safe)
    if m and '윤' not in safe:
        safe = safe.replace(f"{m.group(1)}월", f"{int(m.group(1)):02d}월")
    
    path = os.path.join(OUTPUT_DIR, f"{safe}.csv")
    rows = sorted(counts.items(), key=lambda x: -x[1])
    
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['한자단어', '빈도'])
        w.writerows(rows)
    return path

# ─── 월 처리 ────────────────────────────────────────────────────────────────
def process_month(month_id, month_label):
    """한 달의 전체 기사를 처리하여 단어 빈도 반환"""
    
    # 1. 일별 기사 목록 요청
    params = {
        'id':        month_id,
        'level':     '5',
        'treeType':  'C',
        'kingName':  '聖祖仁皇帝',
        'silokName': '聖祖仁皇帝實錄',
        'dateInfo':  month_label
    }
    daylist = fetch_post('/mc/inspectionDayList.do', params)
    time.sleep(DELAY)
    
    if not daylist:
        log.error(f"    ❌ daylist 실패: {month_label}")
        return Counter(), 0
    
    # 2. 기사 ID 추출
    rec_ids = get_record_ids(daylist)
    
    if not rec_ids:
        return Counter(), 0
    
    # 3. 각 기사 텍스트 수집
    all_parts = []
    for rid in rec_ids:
        html = fetch_get(f'/mc/id/{rid}')
        time.sleep(DELAY)
        if html:
            t = extract_text(html)
            if t:
                all_parts.append(t)
    
    # 4. 단어 빈도 계산
    full = ' '.join(all_parts)
    words = tokenize(full)
    return Counter(words), len(rec_ids)

# ─── 메인 ──────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("  강희제실록 한자 단어 빈도 추출기")
    log.info(f"  시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)
    
    # 월 목록 로드
    months_file = "kangxi_months.json"
    if not os.path.exists(months_file):
        log.error(f"파일 없음: {months_file}")
        return
    
    with open(months_file, 'r', encoding='utf-8') as f:
        months = json.load(f)
    
    log.info(f"총 {len(months)}개월 (1661~1722년)")
    
    # 체크포인트
    cp = load_cp()
    done = set(cp.get("completed", []))
    remaining = [(mid, mlab) for mid, mlab in months if mid not in done]
    log.info(f"완료: {len(done)}개월 | 남은: {len(remaining)}개월")
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    t0 = time.time()
    new_done = 0
    
    for i, (month_id, month_label) in enumerate(remaining):
        global_i = months.index((month_id, month_label)) if (month_id, month_label) in months else i
        
        log.info(f"\n[{len(done)+new_done+1}/{len(months)}] {month_label}")
        
        try:
            counts, num_records = process_month(month_id, month_label)
            
            csv_path = save_csv(month_label, counts)
            total_w = sum(counts.values())
            log.info(f"    기사 {num_records}건 | 단어 {total_w}개 ({len(counts)}종) → {os.path.basename(csv_path)}")
            
            # 상위 5개 단어 미리보기
            top5 = sorted(counts.items(), key=lambda x: -x[1])[:5]
            if top5:
                log.info(f"    Top5: {top5}")
            
            # 체크포인트 저장
            cp["completed"].append(month_id)
            save_cp(cp)
            new_done += 1
            
            # ETA
            elapsed = time.time() - t0
            avg = elapsed / new_done
            eta_m = (len(remaining) - i - 1) * avg / 60
            log.info(f"    ETA: {eta_m:.0f}분 후 완료")
            
        except KeyboardInterrupt:
            log.info("\n사용자 중단. 체크포인트 저장됨.")
            save_cp(cp)
            break
        except Exception as e:
            log.error(f"    ❌ 오류: {e}")
            continue
    
    log.info(f"\n{'='*60}")
    csvs = os.listdir(OUTPUT_DIR) if os.path.exists(OUTPUT_DIR) else []
    log.info(f"완료! CSV {len(csvs)}개 파일 → {os.path.abspath(OUTPUT_DIR)}/")
    log.info(f"소요: {(time.time()-t0)/60:.1f}분")
    log.info(f"종료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == '__main__':
    main()
