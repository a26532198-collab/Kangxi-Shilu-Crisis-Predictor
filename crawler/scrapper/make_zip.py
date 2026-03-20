#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
한글 파일명 → 영문 파일명으로 변환 후 ZIP 생성
예) 1661년_01월.csv → 1661_01.csv
"""
import zipfile, os, re

src_dir = '/home/user/output_csv'
out_zip = '/home/user/kangxi_windows.zip'

# 파일명 변환 함수: "1661년_01월.csv" → "1661_01.csv", "1661년_윤7월.csv" → "1661_yun07.csv"
def convert_name(fname):
    # 윤달 처리
    m = re.match(r'(\d{4})년_윤(\d+)월\.csv', fname)
    if m:
        return f"{m.group(1)}_yun{int(m.group(2)):02d}.csv"
    # 일반 월 처리
    m = re.match(r'(\d{4})년_(\d+)월\.csv', fname)
    if m:
        return f"{m.group(1)}_{int(m.group(2)):02d}.csv"
    return None

files = sorted(os.listdir(src_dir))
csv_files = [(f, convert_name(f)) for f in files if convert_name(f)]

print(f"변환할 CSV 파일 수: {len(csv_files)}개")
print("첫 5개:", [new for _, new in csv_files[:5]])
print("마지막 5개:", [new for _, new in csv_files[-5:]])

with zipfile.ZipFile(out_zip, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
    for orig, new_name in csv_files:
        fpath = os.path.join(src_dir, orig)
        zf.write(fpath, new_name)

size_kb = os.path.getsize(out_zip) / 1024
print(f"\nZIP 생성 완료: {out_zip}")
print(f"크기: {size_kb:.1f} KB")
print(f"포함 파일 수: {len(csv_files)}개")
