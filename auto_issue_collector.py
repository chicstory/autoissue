# -*- coding: utf-8 -*-
"""
ThePathLab Auto Issue Collector & Pipeline Engine
Fetches domestic (Korea MOLIT / RSS) and global (NHTSA / US RSS) automotive issues,
deduplicates and merges them into data/issues.json, and produces KPI summary stats.
"""

import os
import json
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ISSUES_FILE = os.path.join(DATA_DIR, "issues.json")
STATS_FILE = os.path.join(DATA_DIR, "latest_stats.json")

# 10 Major Manufacturer Groups
BRAND_CONFIG = {
    "hyundai_kia": {
        "name": "현대·기아 (제네시스)",
        "keywords": ["현대차", "기아", "제네시스", "현대자동차", "Hyundai", "Kia", "Genesis"],
        "engine_table": "https://chicstory.github.io/engines/hyundai_kia_engine_table.html"
    },
    "bmw_mini": {
        "name": "BMW · MINI",
        "keywords": ["BMW", "MINI", "미니", "비엠더블유"],
        "engine_table": "https://chicstory.github.io/engines/bmw_engine_table.html"
    },
    "mercedes": {
        "name": "메르세데스-벤츠",
        "keywords": ["벤츠", "메르세데스", "Mercedes", "Benz"],
        "engine_table": "https://chicstory.github.io/engines/mercedes_benz_engine_table.html"
    },
    "vw_audi": {
        "name": "폭스바겐 · 아우디",
        "keywords": ["폭스바겐", "아우디", "Volkswagen", "Audi", "VW"],
        "engine_table": "https://chicstory.github.io/engines/volkswagen_engine_table.html"
    },
    "kgm": {
        "name": "KGM (쌍용)",
        "keywords": ["KGM", "쌍용", "KG모빌리티", "액티언", "토레스", "Ssangyong"],
        "engine_table": "https://chicstory.github.io/engines/kgm_ssangyong_engine_table.html"
    },
    "gm_chevy": {
        "name": "GM · 쉐보레",
        "keywords": ["쉐보레", "GM", "한국GM", "캐딜락", "Chevrolet", "Cadillac", "트랙스"],
        "engine_table": "https://chicstory.github.io/engines/"
    },
    "renault": {
        "name": "르노코리아",
        "keywords": ["르노", "르노코리아", "Renault", "콜레오스", "아르카나"],
        "engine_table": "https://chicstory.github.io/engines/"
    },
    "toyota_lexus": {
        "name": "토요타 · 렉서스",
        "keywords": ["토요타", "도요타", "렉서스", "Toyota", "Lexus", "캠리", "프리우스"],
        "engine_table": "https://chicstory.github.io/engines/"
    },
    "ford_lincoln": {
        "name": "포드 · 링컨",
        "keywords": ["포드", "링컨", "Ford", "Lincoln", "익스플로러"],
        "engine_table": "https://chicstory.github.io/engines/"
    },
    "tesla_others": {
        "name": "테슬라 · 기타 수입차",
        "keywords": ["테슬라", "Tesla", "볼보", "Volvo", "포르쉐", "Porsche", "폴스타"],
        "engine_table": "https://chicstory.github.io/engines/"
    },
    "byd": {
        "name": "BYD (비야디)",
        "keywords": ["BYD", "비야디", "씰", "아토3", "Atto", "돌핀", "Dolphin", "한EV", "탕EV", "비야디코리아"],
        "engine_table": "https://chicstory.github.io/engines/"
    },
    "rivian": {
        "name": "Rivian",
        "keywords": ["Rivian", "리비안", "R1T", "R1S", "R2", "R3"],
        "engine_table": "https://chicstory.github.io/engines/"
    },
    "lucid": {
        "name": "Lucid Motors",
        "keywords": ["Lucid", "루시드", "Lucid Air", "Lucid Gravity", "루시드 에어"],
        "engine_table": "https://chicstory.github.io/engines/"
    }
}

def load_existing_issues():
    if os.path.exists(ISSUES_FILE):
        try:
            with open(ISSUES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load existing issues: {e}")
    return []

def clean_html_tags(text):
    if not text:
        return ""
    clean = re.sub(r'<.*?>', '', text)
    clean = clean.replace('&quot;', '"').replace('&apos;', "'").replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return clean.strip()

def detect_brand(text):
    for b_id, b_info in BRAND_CONFIG.items():
        for kw in b_info["keywords"]:
            if kw.lower() in text.lower():
                return b_id, b_info["name"]
    return "hyundai_kia", "현대·기아 (제네시스)"

def detect_category(title, snippet=""):
    combined = (title + " " + snippet).lower()
    if any(k in combined for k in ["리콜", "recall", "결함", "화재 위험", "제동 불량", "에어백", "소손"]):
        return "recall", "🚨 리콜 공고"
    if any(k in combined for k in ["무상수리", "service campaign", "캠페인", "소프트웨어 업데이트", "ota", "개선"]):
        return "service", "🔧 무상수리·OTA"
    if any(k in combined for k in ["전기차", "ev", "배터리", "충전", "fsd", "자율주행"]):
        return "tech_ev", "⚡ 전기차·배터리"
    if any(k in combined for k in ["신차", "출시", "공개", "페이스리프트", "풀체인지", "하이브리드", "launch", "debut"]):
        return "newcar", "🚗 신차·출시"
    return "industry", "📰 업계·테크 이슈"

def fetch_rss(url, timeout=7):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read()
    except Exception as e:
        print(f"RSS fetch skipped for {url[:50]}...: {e}")
        return None

def collect_korean_news():
    queries = [
        "자동차 리콜 when:7d",
        "국토부 리콜 when:7d",
        "자동차 무상수리 when:7d",
        "현대차 기아 신차 when:7d",
        "수입차 결함 리콜 when:7d",
        "BYD 비야디 리콜 결함 when:7d",
        "BYD 비야디 신차 출시 when:7d"
    ]
    items = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    for q in queries:
        encoded = urllib.parse.quote(q)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
        xml_data = fetch_rss(url)
        if not xml_data:
            continue
        try:
            root = ET.fromstring(xml_data)
            for item in root.findall(".//item")[:5]:
                title = clean_html_tags(item.findtext("title", ""))
                link = item.findtext("link", "")
                pub_date = item.findtext("pubDate", "")
                
                # Simple date formatting
                date_str = today_str
                if pub_date:
                    try:
                        # e.g. Mon, 08 Sep 2026 05:12:00 GMT
                        dt = datetime.strptime(pub_date[:16], "%a, %d %b %Y")
                        date_str = dt.strftime("%Y-%m-%d")
                    except:
                        date_str = today_str
                
                brand_id, brand_name = detect_brand(title)
                cat_id, cat_label = detect_category(title)
                
                # Skip trivial non-auto matches
                if not any(k in title for k in ["차", "차량", "모빌리티", "엔진", "모터", "기아", "현대", "BMW", "벤츠", "리콜", "아우디", "폭스바겐", "KGM", "쉐보레", "토요타", "포드", "테슬라", "BYD", "비야디"]):
                    continue

                items.append({
                    "id": f"kr-{abs(hash(title)) % 1000000}",
                    "date": date_str,
                    "brand_id": brand_id,
                    "brand_name": brand_name,
                    "category": cat_id,
                    "category_label": cat_label,
                    "origin": "domestic",
                    "origin_label": "국내 공식 공고",
                    "title": title,
                    "vehicles": [brand_name.split()[0]],
                    "powertrain_tags": ["주요 파워트레인"],
                    "engine_link": BRAND_CONFIG[brand_id]["engine_table"],
                    "summary": f"{title} 관련 최신 국내 공식 보도 및 공고 사항입니다. 상세 세부 내역은 원문 링크에서 확인하실 수 있습니다.",
                    "details": {
                        "units_affected": "공고문 참조",
                        "production_period": "세부 차종별 상이",
                        "defect_cause": "공식 공고 사유 참조",
                        "action_plan": "지정 공식 서비스센터 방문 또는 무상 조치"
                    },
                    "source_name": "국내 주요 언론 & 국토교통부 보도",
                    "source_url": link
                })
        except Exception as e:
            print(f"Error parsing KR RSS for query {q}: {e}")
    return items

def collect_global_nhtsa_news():
    queries = [
        "NHTSA recall Hyundai Kia when:7d",
        "NHTSA recall BMW when:7d",
        "NHTSA recall Mercedes when:7d",
        "NHTSA recall Toyota Ford when:7d",
        "NHTSA safety recall defect when:7d",
        "NHTSA recall BYD when:7d",
        "NHTSA recall Rivian when:7d",
        "Rivian recall defect investigation when:7d",
        "NHTSA recall Lucid when:7d",
        "Lucid Motors recall defect when:7d"
    ]
    items = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    for q in queries:
        encoded = urllib.parse.quote(q)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
        xml_data = fetch_rss(url)
        if not xml_data:
            continue
        try:
            root = ET.fromstring(xml_data)
            for item in root.findall(".//item")[:4]:
                title = clean_html_tags(item.findtext("title", ""))
                link = item.findtext("link", "")
                pub_date = item.findtext("pubDate", "")
                
                date_str = today_str
                if pub_date:
                    try:
                        dt = datetime.strptime(pub_date[:16], "%a, %d %b %Y")
                        date_str = dt.strftime("%Y-%m-%d")
                    except:
                        date_str = today_str

                brand_id, brand_name = detect_brand(title)
                cat_id, cat_label = detect_category(title)
                
                # Check for recall keywords
                if "recall" not in title.lower() and "defect" not in title.lower() and "investigation" not in title.lower():
                    continue

                items.append({
                    "id": f"nhtsa-{abs(hash(title)) % 1000000}",
                    "date": date_str,
                    "brand_id": brand_id,
                    "brand_name": brand_name,
                    "category": cat_id,
                    "category_label": cat_label,
                    "origin": "global_nhtsa",
                    "origin_label": "해외 선제 공고 (NHTSA 🌐)",
                    "title": f"[해외 선제공고] {title}",
                    "vehicles": [brand_name.split()[0]],
                    "powertrain_tags": ["북미/글로벌 탑재 파워트레인"],
                    "engine_link": BRAND_CONFIG[brand_id]["engine_table"],
                    "summary": f"미국 NHTSA 및 북미 안전 감독 당국에서 발표된 선제적 결함 조사 및 리콜 공고입니다. 국내 도입 여부는 순차 확인 중입니다.",
                    "details": {
                        "units_affected": "북미 대상 대수 확인 중",
                        "production_period": "글로벌 생산분 대상",
                        "defect_cause": "NHTSA 캠페인 조사 보고서 참조",
                        "action_plan": "북미 공식 딜러망 선제 점검 개시 (국내 미반영분 선제 대비 권장)"
                    },
                    "source_name": "미국 NHTSA / Global Safety Agency",
                    "source_url": link
                })
        except Exception as e:
            print(f"Error parsing NHTSA RSS for query {q}: {e}")
    return items

def update_pipeline():
    os.makedirs(DATA_DIR, exist_ok=True)
    existing = load_existing_issues()
    existing_titles = {item.get("title", "").strip().lower() for item in existing}
    
    print(f"Existing curated issues: {len(existing)}")
    
    # Collect fresh news
    kr_items = collect_korean_news()
    print(f"Collected domestic items: {len(kr_items)}")
    
    global_items = collect_global_nhtsa_news()
    print(f"Collected global NHTSA items: {len(global_items)}")
    
    new_added = 0
    for it in (kr_items + global_items):
        t_clean = it["title"].strip().lower()
        if t_clean not in existing_titles:
            existing.append(it)
            existing_titles.add(t_clean)
            new_added += 1

    # Sort descending by date
    existing.sort(key=lambda x: x.get("date", "2000-01-01"), reverse=True)
    
    # Keep top 500 issues for long-term weekly accumulation
    final_issues = existing[:500]
    
    with open(ISSUES_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_issues, f, ensure_ascii=False, indent=2)
        
    print(f"Saved {len(final_issues)} issues to {ISSUES_FILE} (+{new_added} new added)")

    # Build KPI Statistics
    stats = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_count": len(final_issues),
        "recall_count": sum(1 for i in final_issues if i.get("category") == "recall"),
        "newcar_count": sum(1 for i in final_issues if i.get("category") == "newcar"),
        "service_count": sum(1 for i in final_issues if i.get("category") == "service"),
        "global_count": sum(1 for i in final_issues if i.get("origin") == "global_nhtsa"),
        "brands_count": len(BRAND_CONFIG),
        "ev_new_brands": ["byd", "rivian", "lucid"]
    }
    
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"Stats summary: {stats}")
    return stats

if __name__ == "__main__":
    print("=== ThePathLab Auto Issue Collector Engine ===")
    update_pipeline()
