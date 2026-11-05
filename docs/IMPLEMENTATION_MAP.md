# FORINA: Zielarchitektur, Implementierungsstand und Arbeitspakete

Grundlage ist das vom Nutzer bereitgestellte [Concept Paper v1.0 vom 5. November 2026](FORINA_CONCEPT_V1.md). Diese Zuordnung trennt vorhandene Funktionen von offenen Zielkomponenten. Sie ist eine gemeinsame Entwicklungsgrundlage und keine bestätigte Aufgabenübernahme durch Devin. Es wurden keine Unterlagen an einen externen Dienst oder Entwicklungsagenten versandt.

## Architekturabgleich

| Zielkomponente | Vorhandene Basis im Repository | Wesentliche Lücke zur Zielarchitektur |
|---|---|---|
| Domain Enrollment Engine | Domainnormalisierung über die unveränderten Guardrails; `Workbench.challenge()` erzeugt einen proprietären DNS-TXT-Entwurf; `forina/enrollment.py` ergänzt persistente lokale Test-Challenges mit Ablauf-/Replay-Schutz | Keine externe DNS-/DNSSEC-, TLS-, RDAP- oder Well-Known-Verifikation; keine DNS-Provider-Anbindung. Ein lokaler Simulationsablauf erfüllt diese Prüfungen nicht. |
| Organization Identity Engine | Lokales Organisationsregister in `forina/core.py`; optionale LEI mit reiner Formatprüfung; alle Identitäten bleiben ungeprüft | Keine unabhängige Register-, LEI/vLEI-, eIDAS-/Siegel- oder VC-Prüfung. Aussteller, Geltung, Prüfzeit und Widerruf benötigen ein belastbares Evidenzmodell und Adapter. |
| International Compliance Engine | `forina/intake.py`, `forina/compliance.py`, portabler Quellenbestand; versionierte Anforderungen, Fundstellen, Architekturmodule, ausdrücklicher Geltungsbereich, lokale Planungsfreigabe und Wiedervorlage | Fachliche Normprüfung, gesetzliche Geltungsdaten, Organisationskategorien und zuständige Aufsicht als eigenständige strukturierte Felder sind noch zu vervollständigen. Planungsfreigabe und offene Nachweisarten sind keine nachgewiesene Compliance. |
| Federated Trust Registry | SQLite-Organisationen und reproduzierbare Nachweispakete nach Schema 2; Komponenten-/Bundle-Hashes und Compliance-Snapshots | Vorhandene ZIP-Nachweispakete sind unsignierte Prüfentwürfe. Eine produktive Trust Registry benötigt extern verankerte Signaturen, Ausstellervertrauen, Gültigkeits- und Widerrufsprüfung sowie getrennte Identitäts-, Domain-, Compliance- und Autorisierungszustände. |
| Federation Access Gateway | Lokale HTTP-API mit Loopback-Bindung, Host-/Origin-Prüfung und begrenzten JSON-Anfragen | Keine authentifizierte Mehrbenutzerfähigkeit, keine föderierten Teilnehmer oder OIDC-/OAuth-/SAML-/mTLS-/VC-Verbindungen. Host-/Origin-Prüfungen ersetzen keine Identitäts- oder Berechtigungsprüfung. |
| Library of State | Quellenkatalog, Originaldateihashes, versionierte Quellenpakete und Anforderungen, lokale Änderungsereignisse und Export-Snapshots | Keine technisch getrennten öffentlichen und geschützten Bereiche; keine externe Beglaubigung oder manipulationssichere Audit-Speicherung. Aktuelle lokale Datenbank und Protokolle bleiben veränderbar. |
| Automated Renewal & Monitoring | Regeln überschreiten bei abgelaufener Wiedervorlage ihren Planungsfreigabestatus; Quellenänderungen eröffnen neue Entwurfsrevisionen | Kein laufender externer Prüfdienst, keine automatische Erneuerung realer Domain-/Identitäts-/Zertifikatsnachweise, keine unabhängigen Widerrufsquellen. |
| Security & Sovereignty Layer | Keine automatischen externen Abrufe oder Fremddomainänderungen; Quellen werden als Daten verarbeitet; keine Zugangsfreigabe aus Compliance-Planung; Originalarchive bleiben erhalten | Produktive Authentifizierung, Zugriffstrennung, Schlüsselverwaltung, datensparsame Aufbewahrungsregeln und unabhängig geprüfte Sicherheitskontrollen fehlen. Lokale Testschlüssel sind keine produktiven Vertrauensanker. |

## Implementierter lokaler Baustein: Phase II

Das abgegrenzte **FTEP-Testprofil** ist implementiert: zeitlich begrenzte Challenges, ausdrücklich simulierte DNS-Antworten, Ed25519-signierte Testnachweise, lokaler Widerruf, API/Oberfläche und ein Offline-CLI-Client. Der genaue Vertrag und seine Grenzen stehen in [FTEP_LOCAL_PROTOCOL.md](FTEP_LOCAL_PROTOCOL.md). Die ursprünglichen Schema-2-Prüfpakete bleiben von den signierten Testnachweisen getrennt.

Die Bedeutung der Testzustände ist fest begrenzt:

- Ein lokaler Autorisierungsvermerk dokumentiert eine Testeingabe, keine unabhängig geprüfte Befugnis eines fremden Domainadministrators.
- Eine passende synthetische DNS-Antwort bestätigt die Simulationsfixture, keine Kontrolle über eine reale Domain.
- Der Testnachweis muss als `TEST ONLY` erkennbar und von den bisherigen unsignierten Nachweispaketen unterscheidbar sein.
- Eine gültige Testsignatur bestätigt die Integrität gegenüber dem gewählten lokalen Testschlüssel, keine Organisationsidentität oder externe Ausstellerlegitimation.
- Identitäts- und Compliance-Verifikation bleiben unabhängig ungeprüft; Föderationsmitgliedschaft und Zugangsrechte bleiben verweigert.
- Ablauf, Wiederverwendung einer verbrauchten Challenge, unbekannte Schlüssel, manipulierte Inhalte und lokale Widerrufe gehören zu den Negativtests.
- Live-DNS, DNS-Provider-Änderungen und die Veröffentlichung einer Well-Known-Datei gehören nicht zu diesem lokalen Schritt.

## Phasen und überprüfbare Liefergegenstände

| Phase | Stand / nächster Liefergegenstand | Abnahmegrenze |
|---|---|---|
| I – Foundation | Quellenkatalog, Organisationsmodell und Compliance-Einpflege vorhanden; Concept Paper und Architekturabgleich dokumentiert | Geprüfte Schemas, Quellenprovenienz und klar getrennte Statusaussagen; noch keine produktive Vertrauensinfrastruktur |
| II – Enrollment Prototype | Lokales FTEP-Testprofil implementiert: Challenge-Lebenszyklus, Ed25519-Testnachweise, lokaler Widerruf, Offline-Client, UI und API-Vertrag | Synthetische Erfolgs- und Fehlerfälle, Ablauf-/Replay-/Manipulations-/Widerrufstests; keine Behauptung realer Domainkontrolle |
| III – Identity & Compliance | Versionierte Compliance-Planung vorhanden; institutionelle Evidenzmodelle und Registeradapter offen | Autorisierte Testadapter, Nachweise mit Aussteller, Geltungsbereich, Prüfzeit, Gültigkeit und Widerruf; fachlich geprüfte Regeln |
| IV – Federation | Offen | Nachweislich autorisierte Teilnehmer, authentifizierte Rollen-/Rechteprüfung, unabhängig widerrufbare Zugangsrechte |
| V – Website Integration | Offen | Explizit autorisierte DNS-/Well-Known-/API-Integration mit engem Änderungsumfang und Rollback |
| VI – Governance & Production Readiness | Offen | Unabhängige Sicherheits-/Integrationstests, Datenschutzprüfung einschließlich erforderlicher Folgenabschätzung und kontrollierte Pilotierung |

Ein Test nach Phase II ist kein Ersatz für die späteren Abnahmen. Insbesondere sind `APPROVED_FOR_PLANNING`, erfolgreiche Hash-Konsistenz, eine synthetische DNS-Fixture und eine gültige lokale Testsignatur unterschiedliche Nachweise mit unterschiedlicher Reichweite.

## Vorschlag gemeinsamer Arbeitspakete für Codex und Devin

Diese Pakete sind **vorgeschlagen und nicht extern zugewiesen**. Übergaben sollen öffentliche Konzept-/Schnittstellenunterlagen, synthetische Fixtures und Ergebnisse enthalten. Produktive private Schlüssel, vertrauliche Nachweise, geschützte Zugänge oder personenbezogene Produktionsdaten gehören nicht in diese Übergaben.

| Kennung | Vorgeschlagener Schwerpunkt | Liefergegenstand | Abhängigkeit / Abnahmekriterium |
|---|---|---|---|
| C-01 | Codex: FTEP-Protokollentwurf | Versionsfähiger lokaler Vertrag, Zustandsmodell und Fehlersemantik | Domain-, Identitäts-, Compliance- und Zugangsstatus sind unabhängig; Testprofil ist ausdrücklich kein ACME-Standard |
| C-02 | Codex: Challenge-Modul | Zeitlich begrenzte Challenge, Bindung an Organisation/Domain und Verbrauchsstatus | Falscher Token, falsche Domain, Ablauf und Replay liefern keine positive Entscheidung |
| C-03 | Codex: Testnachweis und Validierung | Kanonisches signiertes Testobjekt, Testschlüsselauswahl, Verifikation und Widerruf | Manipulation und unbekannter Schlüssel werden erkannt; Signatur begründet keine Mitgliedschaft |
| C-04 | Codex: Lokaler Enrollment-Client | CLI/API-Beispiel und synthetischer Ende-zu-Ende-Test | Kein Netzabruf und keine automatische DNS- oder Websiteänderung |
| D-01 | Devin: Compliance-Regelmodell | Rechtsgrundlage, Normfassung, Geltungsdatum, Organisationskategorie, zuständige Aufsicht und Provenienz | Fachliche Prüfung bleibt dokumentiert; keine Anwendbarkeit allein aus einem Ländernamen oder Domain-Suffix |
| D-02 | Devin: Institutionelle Evidenzadapter | Schnittstellen und synthetische Register-/LEI-/vLEI-/Trust-List-Fixtures | Verifikation, Gültigkeit und Widerruf werden unabhängig von Domainkontrolle behandelt |
| D-03 | Devin: Sicherheits-/Architekturprüfung | Bedrohungsmodell und Review der Autorisierungs-, Datenschutz- und Schlüsselgrenzen | Öffentliche Katalogisierung kann keine aktive Mitgliedschaft oder Zugangsberechtigung auslösen |
| D-04 | Devin: Synthetische Integration und Zuständigkeiten | Testmatrix, API-Abgleich und fachlich zu prüfende Zuständigkeitsmatrix | Ergebnisse unterscheiden bestandene, fehlgeschlagene, simulierte und noch nicht ausgeführte Prüfungen |
| G-01 | Gemeinsam: Library of State | Klassifikation und technische Trennung öffentlicher Dokumentation und geschützter Evidenz | Keine automatische Offenlegung vertraulicher Daten durch FOIA-/Sunshine-Schlagworte |
| G-02 | Gemeinsam: Erneuerung und Widerruf | Zeit-/Änderungsmodell, unabhängige Revocation-Quellen und Statusübergänge | Alte Nachweise und widerrufene Zugangsrechte werden nicht durch unveränderte Signaturgültigkeit wieder aktiviert |

## Zuordnung der sieben im Kontext genannten Lovable-Anwendungen

Die erneut bereitgestellte [frühere Analyse](LOVABLE_ANALYSIS_USER_PROVIDED.md) ist als Nutzer-Kontext unverändert abgelegt. Sie unterscheidet sich von der zuvor hochgeladenen Fassung nur durch die Darstellung eines HTML-Leerzeichens. Ihre Aussagen über eingesehene Quellcodes oder Deployment-Zuordnungen wurden in dieser Cloud-Aufgabe nicht eigenständig bestätigt; die entsprechenden Checkouts fehlen weiterhin. Die folgende Zuordnung ist deshalb eine Integrationsplanung, keine aktive Verbindung.

| Genannte Anwendung / Domain | Forina-Zielkomponente | Vorgesehener, noch zu implementierender Übergabevertrag |
|---|---|---|
| Global Finance Scout / `globe-finance-finder.lovable.app` | Organization Identity Engine | Registerfund mit Quellen-URL, Abrufzeit, Organisationskennung, Aufsicht/Tätigkeit und unverifiziertem/validiertem Evidenzstatus getrennt |
| Compliance Connectors / `trustbridge-connector-lab.lovable.app` | Federation Access Gateway / Registry-Adapter | Autorisierte Connector-Identität, erlaubte Ziele und Tätigkeiten, normalisierte Evidenzantwort; kein Zugriff aus bloßem Registerfund |
| Script Weaver / `script-weaver-crossroads.lovable.app` | Domain Enrollment Engine / Infrastructure | Explizit freigegebene Challenge-Aktion mit Domainbindung, Ablauf und begrenztem Änderungsumfang |
| Compliance Blueprint / `build-my-compliance.lovable.app` | International Compliance Engine | Versionierter Regelentwurf mit Rechtsgrundlage, Fundstelle, Geltungsbereich, Kontrollen und Nachweisarten |
| Compliance Compass / `regula-quest.lovable.app` | International Compliance Engine | Quellen-/Evidenzprüfung mit Prüferentscheidung, Gültigkeit und Wiedervorlage |
| Geometric Weaver / `geo-weave-connect.lovable.app` | Federated Trust Registry | Vertrauenskante mit überprüfbaren Nachweisen und getrenntem Autorisierungs-/Widerrufsstatus |
| Package Inspector / `package-proof-kit.lovable.app` | Library of State / Nachweisexport | Manifest, Inhalts-/Quellhashes und ggf. extern verankerte Signatur; Integrität ist kein Berechtigungsnachweis |

Für lokale Einpflege der beiden Projektgrundlagen in das vorhandene Quellenregister: `python3 tools/import_project_context.py`. Der Mechanismus verwendet dieselbe Vorschau-/Digest-/Revisionslogik wie die Oberfläche. Unveränderte Wiederholungen bleiben ohne neue Quellenrevisionen. Die Konzept- und Analyseunterlagen werden als ungeprüfte Dokumentquellen behandelt, nicht als Gesetze oder institutionelle Bestätigungen.

## CSV-Master-Registry und Auth-Gateway-Planung

Der neue [CSV-/Pocket-ID-Architekturstand](CSV_AUTH_ARCHITECTURE.md) ergänzt den Offline-Import bis 72.000 Datenzeilen, normalisierte URL-/Domainbestände, Quellenberichte und CSV-Export. Domain-/Institutionstypen sind ausschließlich unverifizierte Hinweise; echte Rechtsräume und Prüfstatus werden nicht aus einer TLD abgeleitet. DNS/TLS/RDAP, Auth-Discovery, Signatur und aktive Föderation werden durch den Import nicht ausgeführt.

Ein Offline-Rechtsraumresolver stellt Regelkandidaten zu ausdrücklich benannten Rechtsräumen zusammen, bestätigt aber keine rechtliche Kompatibilität. Der [Pocket-ID-/Forward-Auth-Vertrag](POCKET_ID_GATEWAY.md) und ein reiner Planungsevaluator sind vorbereitet. Die echte Forward-Auth-Schnittstelle verweigert mit HTTP 503, bis OIDC-Sitzungsverifikation und Zugriffsdurchsetzung implementiert sind. Das ursprüngliche Ziel eines authentifizierten Federation Access Gateway bleibt damit offen.

## Voraussetzungen für externe Integrationen

Vor einem externen Adapter oder einer Änderung an einer teilnehmenden Domain sind Zielorganisation, autorisierte Tätigkeit, Datenumfang, notwendige Freigabe, technische Berechtigungen und Rücknahmeverfahren zu bestimmen. Die aktuelle lokale Implementierung stellt diese Voraussetzungen nicht durch eine Formulareingabe oder einen Testtoken her.

Eine Veröffentlichung oder Weitergabe dieser Dokumente an Devin wurde durch das Anlegen im gemeinsamen Workspace nicht ausgeführt. Die Dateien sind für eine spätere, ausdrücklich veranlasste Übergabe vorbereitet.
