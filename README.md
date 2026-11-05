# Forina · Federation Workbench

Lokaler Integrationsprototyp aus den zwölf bereitgestellten Archiven: Quellenkatalog → Organisationsregister → Compliance-Prüfplan → exportierbares Nachweispaket.

Die **Compliance-Einpflege** verbindet nun vollständige Archivtexte und Hyperlinks mit versionierten Anforderungen, Architekturmodulen, Kontrollen und Nachweisarten. Die Oberfläche „Vorschriften einpflegen“ bietet Dokumentimport mit Vorschau, eigene Anforderungen aus Fundstellen, fachliche Bearbeitung, Planungsfreigabe und Wiedervorlage. Details, Architekturzuordnung und API: [Compliance-Einpflege](docs/COMPLIANCE_INTAKE.md).

Das [Concept Paper v1.0](docs/FORINA_CONCEPT_V1.md) ist als Architekturgrundlage aufgenommen. [Implementierungsstand und Arbeitspakete](docs/IMPLEMENTATION_MAP.md) trennen die acht Zielkomponenten von den vorhandenen Funktionen. Phase II ist als [lokales FTEP-Testprofil](docs/FTEP_LOCAL_PROTOCOL.md) mit DNS-Fixture, Ed25519-signiertem Testnachweis und lokalem Widerruf ergänzt.

Die [CSV-Master-Registry](docs/CSV_AUTH_ARCHITECTURE.md) ergänzt den Offline-Import bis 72.000 Zeilen mit URL-/Domain-Deduplizierung und unverifizierten Länder-/Institutionstyp-Hinweisen. Eine CLI ist über `python3 -m forina.registry_client` verfügbar. [Pocket ID und Forward Auth](docs/POCKET_ID_GATEWAY.md) sind als getrennte Integrationsschicht beschrieben; die aktuelle Forward-Auth-Schnittstelle verweigert Zugriffe, bis ein echter OIDC-Verifier eingerichtet ist.

## Start

Python 3.11 oder neuer, ausschließlich Standardbibliothek. Keine Paketinstallation erforderlich.

Die optionale FTEP-Testsignatur benötigt zusätzlich OpenSSL 3 mit Ed25519-Unterstützung (hier mit OpenSSL 3.5.7 geprüft). Sie erzeugt nur lokale Testschlüssel; der öffentliche Schlüssel wird getrennt vom privaten Schlüssel ausgegeben. Für eine reine Offline-Demonstration mit temporären synthetischen Daten: `python3 -m forina.ftep_client`.

```sh
python3 -m forina.server
```

Der Dienst bindet ausschließlich an Loopback, Port 8787. Für eine andere lokale Portnummer: `python3 -m forina.server --port 8788`. Die Cloud-Onboarding-Oberfläche bietet keine Webvorschau für Loopback-Adressen. Die HTTP-API kann lokal geprüft werden; keine öffentliche Bereitstellung ist enthalten. Lokale Daten werden in `.runtime/forina.sqlite3` gespeichert. Der Server benötigt nach einem Neustart der Umgebung einen erneuten Start.

## Was verbunden ist

- **Alle zwölf Archive:** 503 Dateinachweise mit SHA-256 und 360 begrenzte, durchsuchbare Textauszüge. Archivname, Rolle und Herkunft bleiben erhalten. Es werden keine Aussagen allein durch ihren Import bestätigt.
- **Forina Guardrails:** unverändert übernommener Offline-Adapter für Rechtsraum-/Sektor-Prüfkandidaten und DNS-TXT-Entwürfe.
- **Compliance-Register:** 411 vollständig erfasste Text-/Konfigurationsdateien, 3.673 normalisierte Hyperlinks und 90 initiale Anforderungskandidaten. Die 24 internen Guardrails und drei OPA-Policies bleiben von Rechts-/Standardverweisen unterscheidbar. Alles beginnt als Prüfentwurf.
- **Organisationsregister:** lokale Erfassung von Name, Domain, Rechtsräumen, Sektor und optionalem LEI. LEI-Eingaben erhalten nur eine Formatprüfung, keine Prüfziffer- oder Registerverifikation.
- **Nachweispaket:** JSON/ZIP mit Organisations-Snapshot, Prüfplan, versioniertem Compliance-Register, Herkunft aller Archive und Komponenten-/Bundle-Hashes; unabhängige Konsistenzprüfung über Upload von `record.json`. Alte Pakete nach Schema 1 bleiben prüfbar.

Die weiteren Projekte sind als Quellen erschlossen, ihre Dienste wurden nicht zu einer funktionierenden Gesamtföderation verschaltet. Konzepttexte sind keine ausführbaren Dienste. Die früher beschriebenen sieben Lovable-Anwendungen liegen hier nicht als bestätigte Checkouts vor.

## Herkunft und Aktualisierung

`forina/data/catalog.json` enthält die portable Quellenerschließung. Originalarchive und vollständige entpackte Inhalte verbleiben unter `/workspace/attachments` bzw. `/workspace/forina-onboarding/sources`; sie wurden nicht verändert. Einige Texte sind auf 24.000 Zeichen begrenzt und entsprechend gekennzeichnet. Die Suche deckt diese Auszüge und ihre Dateipfade ab, keine vollständige inhaltliche Prüfung aller Dateien. Bibliotheksdateien/Quelltexte werden als Daten behandelt und nicht durch den Import ausgeführt.

Katalog aus der bestehenden Inventardatei neu erstellen:

```sh
python3 tools/import_sources.py /workspace/forina-onboarding/inventory.json
```

`forina/vendor/guardrails/` enthält die ursprünglichen Guardrails-Dateien inklusive README. Rechtsquellen und Anwendbarkeit sind importierte Prüfkandidaten und müssen fachlich geprüft werden; die App bestätigt keine aktuelle Rechtslage. Beispielsweise sind die deutschen BAFIN-/BSI-Quellen im Ausgangskatalog pauschal auf die BfDI-Website verwiesen. Diese Angaben wurden nicht als rechtlich validierte Regeln übernommen.

## Validierung

```sh
python3 -m unittest discover -s tests -v
```

Die Tests prüfen alle Archivzählungen, Suchprovenienz, Eingabevalidierung, persistente Erfassung, Policy-Planung, Challenge-Status, ZIP-Export, Manipulationserkennung und den kompletten HTTP-Arbeitsablauf. Sie verwenden temporäre Datenbanken und synthetische Organisationen.

Die erweiterte Suite prüft außerdem Quellenimport, Fundstellen hinter der bisherigen Textbegrenzung, Revisionskonflikte, fachliche Freigabe, Geltungsbereich, Wiedervorlage und Rücksetzung bei Quellenänderungen. Ein optionaler Browsercheck ist in `tools/browser_smoke.py` enthalten.

## API

| Methode | Route | Zweck |
|---|---|---|
| GET | `/api/health` | Lokale Betriebsbereitschaft |
| GET | `/api/catalog` | Quellen und Rechtsräume |
| GET | `/api/search?q=OPA` | Suche in Textauszügen |
| GET / POST | `/api/organizations` | Organisationen anzeigen / erfassen |
| GET | `/api/organizations/{id}/plan` | Offline-Prüfplan |
| POST | `/api/organizations/{id}/challenge` | TXT-Entwurf mit `authorization_reference` |
| GET / POST | `/api/records` | Nachweise anzeigen / mit `organization_id` erzeugen |
| GET | `/api/records/{id}/export` | JSON-/ZIP-Paket |
| POST | `/api/verify` | Komponenten-/Bundle-Hash eines Records prüfen |

## Grenzen und nächste Integrationsstufen

Keine Live-DNS-Abfragen oder DNS-Änderungen, keine LEI/vLEI-/eIDAS-/Registerprüfung, keine OpenID-Federation-Trust-Chain, keine Zertifikate und keine Zugangsfreigabe. Die Oberfläche weist alle Organisationen als ungeprüft aus. Bestehende Schema-2-Prüfpakete bleiben unsignierte Entwürfe. Nur das getrennte FTEP-Testprofil erzeugt signierte Testnachweise; deren DNS-Fixture und lokale Testfreigabe sind keine echte Domainkontrolle oder Organisationsautorisierung. Die älteren TXT-Entwürfe der Guardrails bleiben ein separates, nicht persistiertes Demonstrationsverfahren.

Hashes erkennen Inkonsistenzen innerhalb eines Pakets. Wer alle Inhalte und Hashes neu berechnet, kann damit nicht erkannt werden. Metadaten wie `signed` sind keine kryptografischen Beweise. Die SQLite-Datenbank ist lokal veränderbar und kein unveränderliches Audit-Ledger.

Ein produktiver Mehrbenutzerbetrieb benötigt zuerst Authentifizierung, Berechtigungen, geregelte Datenspeicherung, geprüfte Registeradapter, unabhängige Verifikation und ein Schlüssel-/Signaturkonzept. Der enthaltene Standardbibliothek-HTTP-Server ist für lokale Entwicklung gedacht.
