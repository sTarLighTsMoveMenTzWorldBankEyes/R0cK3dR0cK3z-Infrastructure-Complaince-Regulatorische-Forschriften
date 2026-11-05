#!/usr/bin/env python3
"""FORINA Offline Trust-Policy Starter (no network, no DNS writes, no certification)."""
import argparse
import datetime as dt
import json
import pathlib
import secrets
import sys
from urllib.parse import urlsplit
HERE = pathlib.Path(__file__).resolve().parent
EU_BASE = ['GDPR','EU_AI_ACT','NIS2','DORA','EIDAS','MICA','PSD2','DSA','DMA','EU_FOI']

def load(name):
    return json.loads((HERE/name).read_text(encoding='utf-8'))

def hostname(raw):
    if not raw or any(c in raw for c in '\r\n\t '):
        raise ValueError('Leere oder ungültige Domain')
    u=urlsplit(raw if '://' in raw else 'https://'+raw)
    if u.scheme not in ('https','http') or u.username or u.password:
        raise ValueError('Nur http/https URLs ohne Zugangsdaten')
    if u.port is not None:
        raise ValueError('URLs mit Ports sind für die Domainkontrolle nicht unterstützt')
    host = u.hostname
    if not host:
        raise ValueError('Domain fehlt')
    try:
        host=host.rstrip('.').encode('idna').decode('ascii').lower()
    except UnicodeError:
        raise ValueError('Domain-IDN ungültig')
    labels=host.split('.')
    if len(host)>253 or len(labels)<2 or any(not (1<=len(x)<=63 and x[0].isalnum() and x[-1].isalnum() and all(y.isalnum() or y=='-' for y in x)) for x in labels):
        raise ValueError('Ungültiger DNS-Hostname')
    if all(x.isdigit() for x in labels) or host in ('localhost.localdomain','local.internal'):
        raise ValueError('IP und lokale Namen sind ausgeschlossen')
    return host

def run_catalog(args):
    countries,laws=load('jurisdictions.json'),load('laws.json')
    codes=[v.upper() for v in args.jurisdiction] if args.jurisdiction else sorted(countries)
    for code in codes:
        if code not in countries:
            raise ValueError('Unbekannter Rechtsraum '+code)
    result={'mode':'OFFLINE_CATALOG','jurisdictions':{c:countries[c] for c in codes},'regulations':laws if args.all_laws else None,
            'legal_effect':'NONE','message':'Informationskatalog: keine Rechtsberatung oder Zulassungsprüfung.'}
    if args.us_states:
        result['us_states']=load('us_states.json')
    print(json.dumps(result,ensure_ascii=False,indent=2))

def run_plan(args):
    countries,laws=load('jurisdictions.json'),load('laws.json')
    codes=[c.upper() for c in args.jurisdiction]
    for c in codes:
        if c not in countries: raise ValueError('Unbekannter Rechtsraum: '+c)
    hosts=[hostname(x) for x in args.domain]
    # Never infer geography or organizational identity from a TLD or hostname alone.
    possible=set()
    for c in codes:
        for key in countries[c]['national_compliance_topics']:
            if key=='EU_BASE': possible.update(EU_BASE)
            else: possible.add(key)
    sector_extra={'finance':['DORA','PSD2','US_GLBA','CH_FINMA','SG_MAS'],
                  'critical':['NIS2'], 'crypto':['MICA'], 'platform':['DSA','DMA'],
                  'ai':['EU_AI_ACT'],'government':['EU_FOI','US_FOIA','US_SUNSHINE'], 'general':[]}
    for k in sector_extra[args.sector]:
        if k in laws and any(x in codes for x in ['EU','DE','IE','ES','IT','FR','BE','LU','PT','SE','FI','DK']) and k in ('DORA','PSD2','MICA','NIS2','DSA','DMA','EU_AI_ACT','EU_FOI'):
            possible.add(k)
        if 'US' in codes and k.startswith('US_'): possible.add(k)
        if 'CH' in codes and k.startswith('CH_'): possible.add(k)
        if 'SG' in codes and k.startswith('SG_'): possible.add(k)
    selected={k:laws[k] for k in sorted(possible) if k in laws}
    controls=['AUTHORIZATION_REQUIRED','DOMAIN_CONTROL_UNVERIFIED','ORG_IDENTITY_UNVERIFIED',
              'REGULATORY_SCOPE_NOT_ASSESSED','NO_CERTIFICATION','NO_NETWORK','NO_DNS_WRITE','NO_API_ACCESS']
    out={'mode':'LOCAL_DRY_RUN','created_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
         'hosts':[{'hostname':h,'status':'UNVERIFIED','federation_status':'NOT_ENROLLED'} for h in hosts],
         'jurisdictions':codes,'sector':args.sector,'possible_regulations':selected,
         'guardrails':controls,'decision':'REVIEW_REQUIRED','access_granted':False,
         'explanation':'Gesetze sind Prüfkandidaten und KEINE festgestellte Rechtsanwendbarkeit.'}
    if 'US' in codes and args.us_state:
        states=load('us_states.json')
        for st in args.us_state:
            if st not in states: raise ValueError('US-Bundesstaat unbekannt: '+st)
        out['us_states']={st:states[st] for st in args.us_state}
    print(json.dumps(out,ensure_ascii=False,indent=2))

def run_challenge(args):
    host=hostname(args.domain)
    if not args.authorization_reference or len(args.authorization_reference.strip())<8:
        raise ValueError('Dokumentierte Freigabereferenz erforderlich (mindestens 8 Zeichen)')
    token=secrets.token_urlsafe(32)
    # Custom, non-ACME TXT proof; NEVER use _acme-challenge to avoid affecting real CAs.
    print(json.dumps({'protocol':'FORINA-DEMO-DNS-TXT-v0.1','domain':host,
       'txt_name':'_forina-challenge.'+host,
       'txt_value':'forina-v1='+token,'ttl_suggested_seconds':300,
       'authorization_reference':args.authorization_reference,
       'challenge_created_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
       'max_age_seconds':900,
       'status':'PENDING_EXTERNAL_DNS_VERIFICATION','domain_control_verified':False,
       'organizational_identity_verified':False,'federation_access_granted':False,
       'warning':'Keine DNS-Abfrage, kein DNS-Write, kein Zertifikat, keine Rechtszertifizierung. '
                 'Freigabereferenz ist selbst kein überprüfter Zustimmungsnachweis.'},ensure_ascii=False,indent=2))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('catalog',help='Rechtsräume und offizielle Portale lokal anzeigen')
    a.add_argument('-j','--jurisdiction',nargs='*',default=[])
    a.add_argument('--all-laws',action='store_true')
    a.add_argument('--us-states',action='store_true')
    a.set_defaults(fn=run_catalog)
    a=sub.add_parser('plan',help='Offline-Compliance-Prüfplan für URLs erzeugen')
    a.add_argument('-j','--jurisdiction',required=True,nargs='+')
    a.add_argument('--domain',required=True,nargs='+')
    a.add_argument('--sector',choices=['general','finance','critical','crypto','platform','ai','government'],default='general')
    a.add_argument('--us-state',action='append',default=[])
    a.set_defaults(fn=run_plan)
    a=sub.add_parser('challenge',help='Nur TXT-Nachtragsvorschlag für bereits autorisierte Domain erzeugen')
    a.add_argument('--domain',required=True)
    a.add_argument('--authorization-reference',required=True)
    a.set_defaults(fn=run_challenge)
    args=p.parse_args()
    try: args.fn(args)
    except (ValueError,OSError,json.JSONDecodeError) as ex:
        print('FORINA SAFETY STOP: '+str(ex),file=sys.stderr)
        return 2
    return 0
if __name__=='__main__':
    sys.exit(main())
