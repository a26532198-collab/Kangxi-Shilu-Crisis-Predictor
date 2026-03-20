#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
강희제실록 - 기사 0건 월 재수집 스크립트
55개 빈 월을 재시도하여 CSV 채우기
"""

import ssl, socket, time, re, json, csv, os
from collections import Counter
from bs4 import BeautifulSoup
import jieba
import logging
import urllib.parse
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[
        logging.FileHandler('/home/user/retry_scraper.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logging.getLogger('jieba').setLevel(logging.WARNING)
log = logging.getLogger(__name__)

OUTPUT_DIR = '/home/user/output_csv'
DELAY      = 2.0    # 재시도는 좀 더 여유있게
MAX_RETRY  = 8
RETRY_WAIT = 6

def make_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE
    ctx.set_ciphers('ALL:@SECLEVEL=0')
    return ctx

def raw_request(path, method='GET', body=None):
    host = 'sillok.history.go.kr'
    ctx  = make_ctx()
    hdrs = {
        'Host': host,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ko-KR,ko;q=0.9',
        'Connection': 'close',
    }
    if body:
        hdrs['Content-Type']   = 'application/x-www-form-urlencoded'
        hdrs['Content-Length'] = str(len(body.encode('utf-8')))

    req = f"{method} {path} HTTP/1.1\r\n"
    for k, v in hdrs.items():
        req += f"{k}: {v}\r\n"
    req += "\r\n"
    if body:
        req += body

    with socket.create_connection((host, 443), timeout=20) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as s:
            s.sendall(req.encode('utf-8'))
            data = b""
            while True:
                chunk = s.recv(8192)
                if not chunk:
                    break
                data += chunk

    idx = data.find(b'\r\n\r\n')
    if idx < 0:
        return None
    body_bytes = data[idx+4:]
    # chunked transfer-encoding 처리
    header_part = data[:idx].decode('utf-8', errors='ignore')
    if 'Transfer-Encoding: chunked' in header_part or 'transfer-encoding: chunked' in header_part:
        decoded = b""
        pos = 0
        while pos < len(body_bytes):
            end = body_bytes.find(b'\r\n', pos)
            if end < 0:
                break
            size = int(body_bytes[pos:end], 16)
            if size == 0:
                break
            decoded += body_bytes[end+2:end+2+size]
            pos = end+2+size+2
        return decoded.decode('utf-8', errors='ignore')
    return body_bytes.decode('utf-8', errors='ignore')

def fetch_post(path, params):
    body = urllib.parse.urlencode(params)
    for attempt in range(1, MAX_RETRY+1):
        try:
            result = raw_request(path, 'POST', body)
            if result and len(result) > 500:
                return result
            log.warning(f"      ⚠ POST {path} 응답 짧음 ({len(result) if result else 0}bytes), 재시도 {attempt}/{MAX_RETRY}")
        except Exception as e:
            log.warning(f"      ⚠ POST {path} 실패: {e}, 재시도 {attempt}/{MAX_RETRY}")
        time.sleep(RETRY_WAIT * attempt)
    return None

def fetch_get(path):
    for attempt in range(1, MAX_RETRY+1):
        try:
            result = raw_request(path, 'GET')
            if result and len(result) > 200:
                return result
            log.warning(f"      ⚠ GET {path} 응답 짧음, 재시도 {attempt}/{MAX_RETRY}")
        except Exception as e:
            log.warning(f"      ⚠ GET {path} 실패: {e}, 재시도 {attempt}/{MAX_RETRY}")
        time.sleep(RETRY_WAIT * attempt)
    return None

def extract_text(html):
    soup = BeautifulSoup(html, 'html.parser')
    vt = soup.find('div', class_='view-text')
    if vt:
        return vt.get_text(' ', strip=True)
    va = soup.find('div', class_='view-area')
    if va:
        parts = [p.get_text(' ', strip=True) for p in va.find_all('p')]
        text = ' '.join(p for p in parts if p)
        if text:
            return text
    parts = []
    for p in soup.find_all('p'):
        t = p.get_text(' ', strip=True)
        if sum(1 for c in t if '\u4e00' <= c <= '\u9fff') > 5:
            parts.append(t)
    return ' '.join(parts)

def get_record_ids(html):
    pattern = r"searchView\s*\(\s*'(qsilok_005_[^']+)'\s*\)"
    ids = re.findall(pattern, html)
    return list(dict.fromkeys(ids))

def tokenize(text):
    cn = ''.join(c for c in text if '\u4e00' <= c <= '\u9fff')
    if not cn:
        return []
    return [w for w in jieba.cut(cn, cut_all=False)
            if len(w) >= 1 and all('\u4e00' <= c <= '\u9fff' for c in w)]

def save_csv(csv_path, counts):
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['한자단어', '빈도'])
        for word, cnt in counts.most_common():
            writer.writerow([word, cnt])

def process_month(month_id, month_label):
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
        return None, 0

    rec_ids = get_record_ids(daylist)
    if not rec_ids:
        log.warning(f"    ⚠ 기사 ID 없음: {month_label}")
        return None, 0

    all_parts = []
    for rid in rec_ids:
        html = fetch_get(f'/mc/id/{rid}')
        time.sleep(DELAY)
        if html:
            t = extract_text(html)
            if t:
                all_parts.append(t)

    full  = ' '.join(all_parts)
    words = tokenize(full)
    return Counter(words), len(rec_ids)

def main():
    log.info("=" * 60)
    log.info("  강희제실록 빈 월 재수집 시작")
    log.info(f"  시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

    with open('/tmp/retry_months.json', 'r', encoding='utf-8') as f:
        retry_list = json.load(f)

    total   = len(retry_list)
    success = 0
    failed  = []

    for i, item in enumerate(retry_list, 1):
        csv_file  = item['csv']
        month_id  = item['id']
        month_label = item['label']
        csv_path  = os.path.join(OUTPUT_DIR, csv_file)

        log.info(f"[{i}/{total}] {month_label}  ({month_id})")

        counts, n_articles = process_month(month_id, month_label)

        if counts is None or n_articles == 0:
            log.error(f"    ❌ 재수집 실패: {month_label}")
            failed.append(item)
            # 빈 CSV는 그대로 유지
            continue

        save_csv(csv_path, counts)
        top5 = counts.most_common(5)
        log.info(f"    ✅ 기사 {n_articles}건 | 단어 {sum(counts.values())}개 ({len(counts)}종) → {csv_file}")
        log.info(f"    Top5: {top5}")
        success += 1
        time.sleep(DELAY)

    log.info("=" * 60)
    log.info(f"재수집 완료: 성공 {success}/{total}개")
    if failed:
        log.warning(f"여전히 실패: {len(failed)}개")
        for f in failed:
            log.warning(f"  - {f['label']}")
    log.info(f"종료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

if __name__ == '__main__':
    main()
