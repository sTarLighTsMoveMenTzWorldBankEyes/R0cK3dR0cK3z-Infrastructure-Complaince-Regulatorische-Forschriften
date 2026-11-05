# Forina – Global Compliance & DNS Trust Guardrails (v0.1)

**Reiner, lokal ausführbarer Offline-Prototyp** (Python 3, Standardbibliothek). Keine Installation, keine Container, keine Systemkonfiguration, keine Internetzugriffe, keine Änderung fremder Domains und keine Zertifikats-/Trust-Mark-Ausstellung.

## Start

```bash
cd forina_compliance_guardrails_v01
python3 forina.py catalog --jurisdiction EU IE ES IT FR BE LU CH PT SE FI DK US BR SG JP IN KR HK NATO
python3 forina.py catalog --jurisdiction US --us-states
python3 forina.py plan --jurisdiction EU DE CH US --domain example.org --sector finance --us-state California
python3 forina.py challenge --domain example.org --authorization-reference ORG-APPROVAL-2026-001
python3 -m unittest discover -s tests -v
```

Alle Befehle schreiben **nur nach stdout**; Ausgabe kann bewusst in einer Datei im Projektordner umgeleitet werden. Keine sensiblen Produktionsdomains, persönlichen Daten, Zugangsdaten oder Schlüssel als Argumente verwenden, wenn Shell-History gespeichert wird.

## Design / Trust States

- `UNVERIFIED`: nur Domainname geparst.
- `PENDING_EXTERNAL_DNS_VERIFICATION`: einmaliges TXT-Challenge vorgeschlagen, nicht geprüft.
- `APPLICABILITY_REQUIRES_REVIEW`: Vorschrift ist Prüfkandidat, nicht rechtsverbindlich zugeordnet.
- `NOT_ENROLLED`: keine Mitgliedschaft und keine Autorisierung.

**Wichtig:** `challenge` ist ein **proprietärer Demonstrations-TXT-Nachweis**, nicht RFC-8555-ACME. Er stellt **kein TLS-Zertifikat** aus. Der Vergleich mit Let's Encrypt betrifft ausschließlich die zukünftige Automationsarchitektur (Challenge → externe Validierung → institutionelle Freigabe). Die Referenznummer ist kein validierter Zustimmungsnachweis. Die produktive Validierungsstufe muss unabhängig und DNSSEC-/Trust-Anchor-bewusst implementiert werden.

## Produktions-Backlog (nicht implementiert)

1. Authentifizierte Domain-Verwalter mit elektronischer Autorisierung, Allowlists und feinsten Berechtigungen.
2. Unabhängiger Online-DNS-Challenge-Prüfer auf autorisierten Hosts; Schutz vor Replay, DNS-Caching, Rebinding und Transferrisiken.
3. Registerdaten- und LEI/vLEI-Abgleich mit nachvollziehbarem Datenprovenienz-Modell.
4. Vertrauensprüfung über EU Trusted Lists, OpenID Federation 1.0, Widerruf und kryptografische Signaturen.
5. Regulatorische Zuständigkeit pro Tätigkeit, Land, Zeitpunkt und Aufsichtsstatus.
6. Einwilligungs- und Zugangsverwaltung für die Federation; kein Automatismus aus DNS-Beweis.
7. DNS-Provider-Adapter **nur** nach explizitem separatem Auftrag, eng begrenzte TXT-Änderungen und Rollback.
8. Reproduzierbare Policy-Pakete mit Versionssignatur, Quellenprüfung, unabhängiger Rechtsfreigabe.
9. Isolierte lokale Ausführung mit externem Startmechanismus, der Netzfreiheit und Programmintegrität nachweist.

## Haftungs- und Statushinweis

Nur ein Entwurfs-/Erfassungswerkzeug. Keine juristische Beratung, keine Vollständigkeitsgarantie, keine Konformitätsbescheinigung. Gesetzeslage ändert sich; alle Regeln vor produktiver Verwendung prüfen. US FOIA und Government in the Sunshine Act treffen grundsätzlich entsprechende Bundesbehörden, nicht automatisch Forina selbst. Der US FREEDOM Act ist ein anderes Gesetz; ohne genaues Thema ist 'Freedom Act' mehrdeutig. 'Ethics Act' ist kein eindeutiger EU-weit einheitlicher Gesetzestitel.

## Technische Primärquellen

- ACME: https://datatracker.ietf.org/doc/html/rfc8555
- OpenID Federation 1.0: https://openid.net/specs/openid-federation-1_0-final.html
- EU Trusted Lists: https://digital-strategy.ec.europa.eu/en/policies/eu-trusted-lists
- EU AI Act: https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai
- EU Finanzrecht: https://finance.ec.europa.eu/regulation-and-supervision/financial-services-legislation/overview-financial-services-legislation_en
- US Sunshine: https://uscode.house.gov/us/usc/119-134/t5/s552b/
- US FOIA: https://uscode.house.gov/us/usc/119-118/t5/s552/
- Brasilien LGPD: https://www.gov.br/anpd/pt-br
- Singapur MAS: https://www.mas.gov.sg/regulation/operational-resilience
