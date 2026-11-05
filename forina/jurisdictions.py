"""Explicit-jurisdiction review planner, not an automated conflict-of-laws opinion."""
import json
from pathlib import Path

from .core import guardrails

VENDOR = Path(__file__).resolve().parent / 'vendor/guardrails'
SECTORS = {'general','finance','critical','crypto','platform','ai','government'}

def resolve_plan(body):
    countries = json.loads((VENDOR / 'jurisdictions.json').read_text())
    codes = body.get('jurisdictions')
    contexts = body.get('institutional_contexts', [])
    sector = body.get('sector', 'general')
    if not isinstance(codes, list) or not 1 <= len(codes) <= 20:
        raise ValueError('Ein bis zwanzig ausdrücklich gewählte Rechtsräume erforderlich')
    if any(not isinstance(c, str) or c.upper() not in countries or c.upper() == 'NATO' for c in codes):
        raise ValueError('Unbekannter Rechtsraum; NATO ist ein institutioneller Kontext, kein nationaler Rechtsraum')
    if not isinstance(contexts, list) or any(c != 'NATO' for c in contexts):
        raise ValueError('Unterstützter institutioneller Kontext: NATO')
    if sector not in SECTORS:
        raise ValueError('Unbekannter Sektor')
    codes = sorted(set(c.upper() for c in codes))
    assessments = []
    for code in codes:
        plan = guardrails('plan','--jurisdiction',code,'--domain','example.org','--sector',sector)
        assessments.append({'jurisdiction':code,'name':countries[code]['name'],
            'authority_references':countries[code].get('competent_authorities', {}),
            'regulatory_candidates':plan['possible_regulations'], 'applicability':'REQUIRES_REVIEW'})
    common = set(assessments[0]['regulatory_candidates'])
    for assessment in assessments[1:]:
        common.intersection_update(assessment['regulatory_candidates'])
    return {'mode':'OFFLINE_JURISDICTION_PLAN','jurisdictions':codes,'sector':sector,
        'institutional_contexts':sorted(set(contexts)), 'compatibility':'REQUIRES_REVIEW',
        'shared_candidate_codes':sorted(common),'assessments':assessments,
        'open_checks':['Niederlassung, Rolle, Tätigkeit und Datenflüsse belegen',
            'Anwendbarkeit und aktuelle nationale Normfassungen fachlich prüfen',
            'Übermittlungen, Lokalisierung und widersprechende Anforderungen prüfen',
            'Zuständige Aufsicht und institutionelle Teilnahmefreigaben bestätigen'],
        'legal_compatibility_verified':False,'access_granted':False,'network_access':'NONE',
        'explanation':'Gemeinsame Regelkandidaten sind kein Kompatibilitätsnachweis. Domainendungen bestimmen diesen Plan nicht.'}
