#!/usr/bin/env python3
# coding: utf-8
"""Katalog modeli WIC -> raport porownawczy z EZ-Reset (bez wysylania komend do drukarki)."""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

DEFAULT_URL = 'https://wic-reset.com/supported-printers'
SOURCES = {
    'reset_wic': 'WIC: reset i odczyt (deklarowane przez źródło)',
    'bez_odczytu_reset': 'WIC: wyłącznie regulacje, bez resetu i odczytu',
    'tylko_odczyt': 'WIC: odczyt tak, reset nie',
}

# Wyciąg z opublikowanej listy WIC; dane ET/L nie mają kluczy serwisowych.
# Ten zestaw służy do lokalnego uruchomienia raportu bez internetu.
SEED_RESET_ET = '''ET-M1100 ET-M1108 ET-M1109 ET-1110 ET-1111 ET-1112 ET-1113 ET-1114 ET-1115 ET-1116 ET-1118
ET-M1120 ET-M1128 ET-M1129 ET-1810 ET-1811 ET-1812 ET-1813 ET-1814 ET-1815 ET-1816 ET-1818
ET-M2120 ET-M2128 ET-M2129 ET-2400 ET-2401 ET-2402 ET-2403 ET-2404 ET-2405 ET-2406 ET-2408
ET-2500 ET-2550 ET-2600 ET-2610 ET-2650 ET-2700 ET-2701 ET-2702 ET-2703 ET-2704 ET-2705 ET-2706 ET-2708
ET-2710 ET-2711 ET-2712 ET-2713 ET-2714 ET-2715 ET-2716 ET-2718 ET-2720 ET-2721 ET-2722 ET-2723 ET-2724 ET-2725 ET-2726 ET-2728 ET-2750 ET-2751 ET-2756 ET-2760
ET-2800 ET-2801 ET-2802 ET-2803 ET-2804 ET-2805 ET-2806 ET-2808 ET-2810 ET-2811 ET-2812 ET-2813 ET-2814 ET-2815 ET-2816 ET-2818
ET-2820 ET-2821 ET-2822 ET-2823 ET-2824 ET-2825 ET-2826 ET-2828 ET-2850 ET-2851 ET-2853 ET-2855 ET-2860 ET-2861 ET-2863 ET-2865 ET-2870 ET-2871 ET-2873 ET-2875 ET-3600 ET-4500 ET-4550 ET-4700 ET-4800 ET-14000'''
SEED_RESET_L = '''L100 L110 L111 L120 L130 L132 L200 L210 L211 L220 L222 L300 L301 L303 L308 L310 L312 L350 L351 L353 L355 L358 L360 L362 L364 L365 L366 L375 L380 L382 L385 L386 L395 L396 L405 L455 L456 L475 L485 L486 L495 L550 L551 L552 L553 L554 L555 L556 L557 L558 L559 L565 L566 L575 L605 L606 L655 L656 L800 L805 L810 L850 L1110 L1118 L1119 L1210 L1216 L1218 L1219 L1230 L1236 L1238 L1239 L1250 L1256 L1258 L1259 L1270 L1276 L1278 L1279 L1300 L1800
L3050 L3060 L3070 L3100 L3101 L3104 L3105 L3106 L3107 L3108 L3109 L3110 L3111 L3114 L3115 L3116 L3117 L3118 L3119 L3150 L3151 L3152 L3153 L3156 L3158 L3160 L3161 L3163 L3165 L3166 L3168
L3200 L3201 L3203 L3205 L3206 L3207 L3208 L3209 L3210 L3211 L3213 L3215 L3216 L3217 L3218 L3219 L3230 L3231 L3233 L3235 L3236 L3237 L3238 L3239
L3250 L3251 L3253 L3255 L3256 L3257 L3258 L3259 L3260 L3261 L3263 L3265 L3266 L3267 L3268 L3269 L3270 L3271 L3273 L3275 L3276 L3277 L3278 L3279 L3280 L3281 L3283 L3285 L3286 L3287 L3288 L3289
L4150 L4151 L4152 L4153 L4154 L4155 L4156 L4157 L4158 L4159 L4160 L4161 L4162 L4163 L4164 L4165 L4166 L4167 L4168 L4169 L4260 L4261 L4263 L4265 L4266 L4267 L4268 L4269 L5190 L5196 L5198 L5290 L5296 L5298 L5310 L5316 L5318'''
SEED_NORESET_ET = '''ET-2830 ET-2831 ET-2832 ET-2833 ET-2834 ET-2835 ET-2836 ET-2838 ET-3700 ET-3710 ET-3750 ET-3760 ET-3800 ET-3830 ET-3850 ET-4750 ET-4760 ET-4810 ET-4850 ET-5170 ET-5800 ET-5850 ET-5880 ET-7700 ET-7750 ET-8500 ET-8550 ET-8700 ET-15000 ET-16150 ET-16500 ET-16600 ET-M16600 ET-16650 ET-16680 ET-M16680 ET-18100'''
SEED_NORESET_L = '''L1455 L3550 L3556 L3558 L5590 L5596 L5598 L6160 L6161 L6168 L6170 L6171 L6178 L6190 L6191 L6198 L6260 L6266 L6268 L6269 L6270 L6276 L6278 L6279 L6290 L6296 L6298 L6299 L6490 L6496 L6498 L6499 L6550 L6551 L6558 L6570 L6571 L6578 L6580 L6581 L6588 L7160 L7168 L7180 L7188 L8050 L8058 L8160 L8168 L8180 L8188 L11050 L11058 L11160 L11168 L14150 L14158 L15150 L15158 L15160 L15168 L15180 L15188 L18050 L18058'''
SEED_READONLY = '''WP-4010 WP-4011 WP-M4011 WP-4015 WP-M4015 WP-4020 WP-4022 WP-4023 WP-4025 WP-4090 WP-4091 WP-4092 WP-4095 WP-M4095 WP-4511 WP-4515 WP-4520 WP-4521 WP-M4521 WP-4525 WP-M4525 WP-4530 WP-4531 WP-4532 WP-4533 WP-4535 WP-4540 WP-4545 WP-4590 WP-4592 WP-4595 WP-M4595'''

class SupportedWicHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_epson = False
        self.mode = 'reset_wic'
        self.heading = None
        self.heading_parts = []
        self.in_anchor = False
        self.anchor_parts = []
        self.entries = []

    def handle_starttag(self, tag, attrs):
        if tag in ('h2','h3','h4'):
            self.heading = tag
            self.heading_parts = []
        elif tag == 'a' and self.in_epson:
            self.in_anchor = True
            self.anchor_parts = []

    def handle_data(self, data):
        if self.heading is not None:
            self.heading_parts.append(data)
        if self.in_anchor:
            self.anchor_parts.append(data)

    def handle_endtag(self, tag):
        if tag == self.heading:
            name = ' '.join(' '.join(self.heading_parts).split()).lower()
            if tag == 'h2':
                if 'epson printers' in name:
                    self.in_epson = True
                    self.mode = 'reset_wic'
                elif self.in_epson:
                    self.in_epson = False
            if self.in_epson and tag == 'h3':
                if 'reset and read counters' in name and 'not' in name:
                    self.mode = 'bez_odczytu_reset'
                elif 'reset function' in name and 'not' in name:
                    self.mode = 'tylko_odczyt'
            if self.in_epson and tag == 'h4' and name in ('company','support','contact'):
                self.in_epson = False
            self.heading = None
            self.heading_parts=[]
        if tag == 'a' and self.in_anchor:
            label = ' '.join(' '.join(self.anchor_parts).split())
            if self.in_epson and valid_model(label):
                self.entries.append((label, self.mode))
            self.in_anchor = False
            self.anchor_parts=[]

MODEL_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9+._-]*(?:\s+[A-Za-z0-9][A-Za-z0-9+._-]*){0,2}$')
def valid_model(name):
    return len(name) <= 45 and bool(MODEL_RE.fullmatch(name)) and any(c.isdigit() for c in name)

def canonical(s):
    return re.sub(r'[^A-Z0-9]', '', s.upper().removeprefix('EPSON '))

# Tytuły w EZ mają np. 'Epson L3250/L3251/L3253/L3255',
# a pole 'model' jest identyfikatorem USB (często 'L3250 Series').
# Tworzymy bezpieczne aliasy tylko z nazw, nigdy z domniemanych parametrów EEPROM.
TOKEN_RE = re.compile(r'(?<![A-Z0-9])(?:ET-M|WF-[CMR]|SC-|XP-|PX-|EP-|ET-|EW-|WF-|WP-|PM-|ME-|[A-Z]{1,3}-?|[A-Z]{1,3}\s+)?\d+[A-Z0-9+]*(?![A-Z0-9])', re.I)
SUFFIX_RE = re.compile(r'^\d+[A-Z0-9+]*$', re.I)
def title_aliases(title):
    upper=title.upper().removeprefix('EPSON ').strip()
    out=set()
    for chunk in upper.split(','):
        fragments=[x.strip() for x in chunk.split('/')]
        last=None
        for frag in fragments:
            matches=list(TOKEN_RE.finditer(frag))
            token=(matches[-1].group().strip() if matches else None)
            if token is None:
                continue
            if last and SUFFIX_RE.fullmatch(token):
                prefix=re.match(r'^(.*?)(?=\d)',last)
                token=(prefix.group(1) if prefix else '')+token
            out.add(canonical(token))
            last=token
        if len(fragments)==1 and fragments[0]:
            out.add(canonical(fragments[0]))
    return out

def get_ez_rows(root):
    devices = root.find('devices')
    specs_by_name={e.tag:e for e in devices}
    results=[]
    for record in root.find('records'):
        name=record.get('title','')
        aliases=title_aliases(name)
        # Pole short może być istotne przy nazwach Photo, WorkForce, itd.
        if record.get('short') and '/' not in record.get('short',''):
            aliases.add(canonical(record.get('short','')))
        specs=record.get('specs','').split(',')
        has_reset=has_read=False
        for spec in specs:
            s=specs_by_name.get(spec)
            if s is None: continue
            for node in s.findall('.//waste/reset'):
                has_reset|=bool((node.text or '').strip())
            for node in s.findall('.//waste/query'):
                has_read|=bool((node.text or '').strip() or len(node))
        results.append({'title':name, 'model_usb':record.get('model',''), 'specs':','.join(specs),
                        'read':has_read,'reset':has_reset,'aliases':aliases})
    return results

def parse_html(s):
    p=SupportedWicHTMLParser();p.feed(s)
    return list(dict.fromkeys(p.entries))

def fetch_models(url):
    req=Request(url, headers={'User-Agent':'Mozilla/5.0 (compatible; WIC-model-catalog-audit/1.0)', 'Accept':'text/html'})
    with urlopen(req, timeout=20) as response:
        html=response.read().decode('utf-8','replace')
    entries=parse_html(html)
    if len(entries)<800 or not any(x[0]=='ET-2850' for x in entries):
        raise RuntimeError('Strona się zmieniła lub dostarczyła niepełną listę modeli. '
                           f'Uzyskano tylko {len(entries)} pozycji. Przerwano import.')
    return entries

def seed_models():
    categories=[(SEED_RESET_ET,'reset_wic'),(SEED_RESET_L,'reset_wic'),
        (SEED_NORESET_ET,'bez_odczytu_reset'),(SEED_NORESET_L,'bez_odczytu_reset'),
        (SEED_READONLY,'tylko_odczyt')]
    return list(dict.fromkeys((n,cat) for raw,cat in categories for n in raw.split()))

def rows_compare(root, entries, source):
    ez=get_ez_rows(root)
    by_alias={}
    for item in ez:
        for alias in item['aliases']:
            by_alias.setdefault(alias,[]).append(item)
    rows=[]
    for model,wic_status in sorted(entries, key=lambda x:(x[0].upper(),x[1])):
        candidates=by_alias.get(canonical(model),[])
        if not candidates:
            assessment='BRAK_W_EZ'
            selected=None
        else:
            selected=max(candidates,key=lambda x:(x['reset'],x['read']))
            if selected['reset'] and selected['read']:
                assessment='EZ_MA_RESET_I_ODCZYT'
            elif selected['reset']:
                assessment='EZ_MA_RESET'
            elif selected['read']:
                assessment='EZ_MA_TYLKO_ODCZYT'
            else:
                assessment='EZ_BRAK_KOMEND'
        rows.append({
            'wic_model':model,'wic_status':wic_status,'ez_wynik':assessment,
            'ez_tytul':selected['title'] if selected else '',
            'ez_usb_mdl':selected['model_usb'] if selected else '',
            'ez_specs':selected['specs'] if selected else '',
            'do_weryfikacji': 'TAK' if (selected is None or
                (wic_status=='reset_wic' and not selected['reset']) or
                (wic_status!='reset_wic' and selected['reset'])) else 'NIE',
            'zrodlo':source,
        })
    return rows

def write_csv(filename, rows):
    fields=['wic_model','wic_status','ez_wynik','ez_tytul','ez_usb_mdl','ez_specs','do_weryfikacji','zrodlo']
    with open(filename,'w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter=';')
        w.writeheader();w.writerows(rows)

def write_candidates(filename, rows):
    root=ET.Element('wic_catalog',{'description':'Tylko katalog nazw. Brak potwierdzonych komend resetowania.',
         'generated_utc':datetime.now(timezone.utc).isoformat()})
    for row in rows:
        if row['ez_wynik']=='BRAK_W_EZ':
            ET.SubElement(root,'candidate',{'name':row['wic_model'], 'wic_status':row['wic_status'],
                 'validated_usb_mdl':'false', 'validated_eeprom':'false','reset_enabled':'false'})
    ET.indent(root,space='  ')
    ET.ElementTree(root).write(filename,encoding='utf-8',xml_declaration=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--xml',default='devices.xml',help='Oryginalny plik EZ-Reset devices.xml')
    ap.add_argument('--out',default='.',help='Folder wynikowy')
    ap.add_argument('--seed-only',action='store_true', help='Porównaj tylko wbudowany fragment ET/L/WP (offline)')
    ap.add_argument('--html',help='HTML zapisany lokalnie ze strony WIC (zamiast pobierania)')
    args=ap.parse_args()
    root=ET.parse(args.xml).getroot()
    if root.find('records') is None or root.find('devices') is None:
        ap.error('Niepoprawny devices.xml EZ-Reset')
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    if args.seed_only:
        entries=seed_models(); source='seed WIC ET/L/WP; fragment katalogu'
    elif args.html:
        entries=parse_html(Path(args.html).read_text(encoding='utf-8'))
        if len(entries)<800: ap.error(f'Niepełny HTML, znaleziono {len(entries)} modeli (minimum 800)')
        source=f'lokalny HTML: {Path(args.html).name}'
    else:
        entries=fetch_models(DEFAULT_URL);source=DEFAULT_URL
    rows=rows_compare(root, entries,source)
    write_csv(out/'wic_vs_ez.csv',rows)
    write_csv(out/'wic_do_weryfikacji.csv',[r for r in rows if r['do_weryfikacji']=='TAK'])
    write_candidates(out/'wic_nowe_modele_katalog.xml', rows)
    print('Źródło:',source)
    print('Pozycje WIC:',len(rows))
    print('Brak w EZ:',sum(x['ez_wynik']=='BRAK_W_EZ' for x in rows))
    print('Wymagają weryfikacji:',sum(x['do_weryfikacji']=='TAK' for x in rows))
    print('Wyniki:',out.resolve())
    print('UWAGA: Nie zmieniono urządzeń ani parametrów resetowania w devices.xml.')

if __name__=='__main__':
    main()
