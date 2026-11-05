# FORINA – Federated Organizational Registry, Identity, Network & Assurance

**Concept Paper – Version 1.0**  
**Datum:** 5. November 2026  
**Projektstatus:** Konzept und technische Entwicklung  
**Entwicklungsumgebung:** Codex und Devin  
**Ausrichtung:** Internationale Finanzinfrastruktur, Government, Compliance, digitale Identitäten und vertrauenswürdige Netzwerkföderation

Dieses Dokument übernimmt das vom Nutzer bereitgestellte Concept Paper als gemeinsame Entwicklungsgrundlage. Es beschreibt die Zielarchitektur; daraus folgt keine Behauptung, dass die beschriebenen Komponenten bereits vollständig implementiert, institutionell anerkannt oder produktionsreif sind. Der aktuelle Implementierungsstand und die vorgeschlagenen Arbeitspakete stehen in [IMPLEMENTATION_MAP.md](IMPLEMENTATION_MAP.md).

## 1. Executive Summary

FORINA ist als international einsetzbare, föderierte Infrastruktur zur Vernetzung bestehender Domains, Organisationen, Finanzsysteme, staatlicher Einrichtungen und digitaler Identitäten vorgesehen.

Das System soll bestehende Webseiten und institutionelle Plattformen nicht ersetzen, sondern über standardisierte technische Nachweise, Organisationsidentitäten und regulatorische Prüfverfahren miteinander verbinden.

Die zentrale Idee besteht darin, ein Let’s-Encrypt-ähnliches Verfahren für Domainkontrolle, institutionelle Identitäten und Compliance-Nachweise zu entwickeln. Während Let’s Encrypt die automatisierte Ausstellung und Erneuerung von TLS-Zertifikaten ermöglicht, soll FORINA die automatisierte Überprüfung und Aktualisierung verschiedener Vertrauensnachweise ermöglichen.

FORINA soll jedoch keine staatlichen Zulassungen, Banklizenzen oder amtlichen Zertifizierungen selbst ausstellen. Das langfristige Ziel ist eine interoperable, international anschlussfähige Vertrauensinfrastruktur.

## 2. Ausgangssituation

Internationale Organisationen betreiben ihre digitalen Infrastrukturen über unterschiedliche Domains, Registrierungsstellen, Aufsichtsbehörden, Identitätsdienste und technische Standards. Daraus entstehen Herausforderungen:

- Fehlende einheitliche Verknüpfung von Domainkontrolle und juristischer Organisationsidentität.
- Unterschiedliche nationale und internationale Compliance-Verfahren.
- Manuelle Prüfung von Zertifikaten, Zulassungen und institutionellen Berechtigungen.
- Fehlende standardisierte Vertrauensnachweise zwischen unabhängigen Plattformen.
- Hoher Verwaltungsaufwand bei grenzüberschreitender Integration.
- Schwierige Nachvollziehbarkeit von Berechtigungen und deren Gültigkeit.

FORINA soll diese Probleme durch eine gemeinsame, modular aufgebaute Vertrauens- und Integrationsschicht adressieren.

## 3. Projektziele

FORINA verfolgt sieben Hauptziele:

1. Automatisierte Registrierung und technische Verifizierung autorisierter Domains.
2. Verknüpfung von Domains mit überprüfbaren Organisationsidentitäten.
3. Integration nationaler und internationaler Compliance-Nachweise.
4. Automatisierte Erstellung signierter Trust Records.
5. Aufbau föderierter Vertrauensbeziehungen zwischen teilnehmenden Organisationen.
6. Transparente, revisionsfähige Dokumentation in einer Library of State.
7. Datenschutzkonforme, sichere und international interoperable Infrastruktur.

## 4. Technische Gesamtarchitektur

FORINA wird in acht voneinander getrennte Komponenten gegliedert.

### 4.1 Domain Enrollment Engine

Die Domain Enrollment Engine ermöglicht die Registrierung bestehender Domains innerhalb der FORINA-Föderation.

Unterstützte Verfahren der Zielarchitektur:

- DNS-TXT-Challenge
- DNSSEC-Prüfung
- TLS-Zertifikatsprüfung
- RDAP-Abfragen
- Autorisierte DNS-Provider-APIs
- Optionaler HTTP-Well-Known-Nachweis

Die technische Verifizierung bestätigt die Kontrolle über eine Domain, nicht automatisch die Identität ihres rechtmäßigen Eigentümers.

### 4.2 Organization Identity Engine

Diese Komponente verbindet Domains mit juristischen Organisationen. Vorgesehene Nachweise:

- Nationale Handels- und Unternehmensregister
- Legal Entity Identifier (LEI)
- Verifiable LEI (vLEI)
- eIDAS-Vertrauensdienste
- Qualifizierte elektronische Organisationssiegel
- Verifiable Credentials
- Institutionelle Organisationsregister

Jeder Nachweis erhält Angaben über Aussteller, Geltungsbereich, Prüfzeitpunkt und Gültigkeitsstatus.

### 4.3 International Compliance Engine

Die Compliance Engine verwaltet maschinenlesbare Prüfregeln für unterschiedliche Rechtsräume.

**Europäische Union:** DSGVO, AI Act, eIDAS, NIS2, DORA, MiCA, Digital Services Act und Digital Markets Act, jeweils soweit anwendbar.

**Nationale Rechtsräume:** Deutschland, Irland, Spanien, Italien, Frankreich, Belgien, Luxemburg, Portugal, Schweden, Finnland, Dänemark und Schweiz.

**Internationale Erweiterung:** USA, Brasilien und ausgewählte asiatische Rechtsräume.

Die Regeln werden nach Version, Rechtsgrundlage, Geltungsdatum, betroffener Organisationskategorie und zuständiger Aufsicht strukturiert. Eine automatisierte Prüfung darf nur Aussagen treffen, die durch verfügbare Nachweise tatsächlich gedeckt sind.

### 4.4 Federated Trust Registry

Die Trust Registry verwaltet überprüfbare Vertrauensbeziehungen. Jeder Trust Record kann enthalten:

- Domain
- Organisationskennung
- Identitätsnachweise
- Technischen Verifizierungsstatus
- Regulatorische Nachweise
- Zertifikatsreferenzen
- Berechtigungsumfang
- Gültigkeitszeitraum
- Widerrufsstatus
- Kryptografische Signatur

FORINA muss zwischen technischen Nachweisen, regulatorischen Genehmigungen und tatsächlichen Zugriffsberechtigungen unterscheiden.

### 4.5 Federation Access Gateway

Das Gateway verbindet ausdrücklich autorisierte Teilnehmer. Vorgesehene Standards:

- OpenID Connect
- OpenID Federation
- OAuth 2.0
- SAML 2.0
- Mutual TLS
- Verifiable Credentials
- Signierte API-Anfragen

Der Zugriff wird durch Richtlinien, Rollen und explizite Autorisierung begrenzt.

### 4.6 Library of State

Die Library of State dient als strukturierte Dokumentations-, Transparenz- und Governance-Ebene. Mögliche Inhalte:

- Öffentliche Rechtsgrundlagen
- Compliance-Richtlinien
- Organisationsnachweise
- Freigegebene institutionelle Dokumente
- Zertifikatsreferenzen
- Governance-Entscheidungen
- Audit-Nachweise
- Dokumentierte Vertrauensbeziehungen

Vertrauliche Daten bleiben in geschützten Bereichen. Öffentliche Dokumentation und geschützte Nachweise müssen technisch getrennt werden.

### 4.7 Automated Renewal & Monitoring

Die Erneuerungs-Engine prüft regelmäßig:

- Domainkontrolle
- Zertifikatsgültigkeit
- Signaturstatus
- Widerruf
- Organisationsstatus
- Ablauf von Nachweisen
- Änderungen regulatorischer Anforderungen

Bei wesentlichen Änderungen wird der betreffende Trust Record aktualisiert, eingeschränkt oder widerrufen.

### 4.8 Security & Sovereignty Layer

Diese Schicht erzwingt technische Sicherheitsgrenzen. Verbindliche Vorgaben:

- Keine unautorisierten Änderungen an fremden Domains.
- Keine automatische Erteilung staatlicher oder regulatorischer Berechtigungen.
- Keine Weitergabe privater Schlüssel oder vertraulicher Zertifikatsdaten.
- Keine Speicherung von Geheimnissen in Logs oder Telemetrie.
- Keine Übertragung produktiver vertraulicher Daten an externe Entwicklungsagenten.
- Strikte Trennung zwischen öffentlicher Verifikation und geschützten Zugängen.
- Nachweisbare Freigaben für Änderungen und Integrationen.
- Revisionsfähige, datensparsame Audit-Protokolle.
- Widerruf und Sperrung von Föderationsberechtigungen.

## 5. Das FORINA Trust Enrollment Protocol

Als eigenes Protokoll wird das **FORINA Trust Enrollment Protocol (FTEP)** vorgeschlagen. Es orientiert sich konzeptionell an ACME, ist jedoch zunächst kein standardisiertes oder ACME-kompatibles Protokoll.

### Enrollment-Ablauf

1. **Domain Discovery:** Eine Domain wird in FORINA erfasst. Öffentliche DNS-, TLS- und Registrierungsinformationen werden geprüft.
2. **Authorization:** Ein berechtigter Organisationsadministrator bestätigt die Teilnahme und die Befugnis zur Domainverifizierung.
3. **DNS Challenge:** FORINA erstellt einen zeitlich begrenzten Challenge-Token. Die Organisation veröffentlicht einen entsprechenden DNS-TXT-Eintrag.
4. **Domain Verification:** FORINA überprüft den Eintrag und bestätigt die technische Domainkontrolle.
5. **Identity Verification:** Die juristische Organisationsidentität wird anhand geeigneter Register und Nachweise geprüft.
6. **Compliance Evidence:** Relevante regulatorische Nachweise werden nach Zuständigkeit und Geltungsbereich validiert.
7. **Federation Authorization:** Die Organisation erhält nach ausdrücklicher Autorisierung einen definierten Föderationsstatus.
8. **Trust Record Issuance:** Ein zeitlich begrenzter, kryptografisch signierter Trust Record wird erstellt.
9. **Continuous Renewal:** Die Nachweise werden innerhalb ihres zulässigen Geltungsbereichs automatisch erneut überprüft.

## 6. Integration in bestehende Webseiten

FORINA soll möglichst ohne Änderungen an der bestehenden Webseitenarchitektur integrierbar sein. Dafür sind drei Integrationswege vorgesehen.

### DNS-Integration

Ein autorisierter DNS-TXT-Eintrag bestätigt die Kontrolle über die Domain.

### Well-Known-Integration

Eine optionale Datei unter `https://example.org/.well-known/forina-trust.json` stellt einen überprüfbaren Verweis auf den signierten Vertrauensnachweis bereit. Dieser Pfad ist zunächst FORINA-spezifisch und kein offiziell registrierter Internetstandard.

### API-Integration

Institutionelle Plattformen können signierte Trust Records über autorisierte Schnittstellen austauschen. Die technische Integration soll mit vorhandenen Webseiten, Portalen und API-Gateways kompatibel sein.

## 7. Government-, NATO- und Finanzinfrastruktur

FORINA kann öffentlich zugängliche Nachweise institutioneller Domains auswerten. Dazu gehören beispielsweise:

- Nationale Regierungsdomains
- EU-Institutionen
- NATO-Domains
- Internationale Organisationen
- Banken und Finanzdienstleister
- Kritische Infrastrukturanbieter
- Forschungs- und Technologieinstitutionen

Die Aufnahme in ein öffentliches Verzeichnis bedeutet keine Partnerschaft oder offizielle Anerkennung. Eine aktive Föderationsmitgliedschaft und der Zugang zu geschützten Diensten setzen eine ausdrückliche Autorisierung der jeweiligen Organisation voraus.

## 8. Transparenz und Freedom-of-Information-Prinzipien

FORINA soll Transparenz und institutionelle Nachvollziehbarkeit fördern. Dafür werden Prinzipien aus unterschiedlichen Rechtsrahmen berücksichtigt:

- Freedom of Information
- Government in the Sunshine Act
- Datenschutz und Informationsfreiheit
- Transparenz öffentlicher Mittelverwendung
- Revisionsfähigkeit institutioneller Entscheidungen
- Digitale Kommunikationsfreiheit

Diese Prinzipien werden in ein eigenständiges Governance-Modell übertragen, ohne zu behaupten, dass die genannten Gesetze unmittelbar auf jede teilnehmende Organisation anwendbar sind.

## 9. Zusammenarbeit zwischen Codex und Devin

Die Entwicklung wird in klar getrennte Aufgabenbereiche gegliedert. Die folgende Aufgabenteilung ist ein Vorschlag, keine bereits bestätigte Zuweisung.

### Codex – Protokoll und lokale Implementierung

Vorgeschlagene Aufgaben:

- FTEP-Protokollentwurf
- DNS-Challenge-Modul
- Trust-Record-Datenmodell
- Kryptografische Validierung
- Offline-Tests
- Schnittstellenspezifikationen
- Lokaler Enrollment-Client

### Devin – Architektur und Compliance-Integration

Vorgeschlagene Aufgaben:

- Internationale Compliance-Regelmodelle
- Institutionelle Registry-Adapter
- API-Schnittstellendokumentation
- Sicherheits- und Architekturprüfungen
- Synthetische Integrationstests
- Dokumentation regulatorischer Zuständigkeiten

Produktive Schlüssel, vertrauliche Daten und geschützte Zugänge dürfen nicht in die Entwicklungsumgebungen übertragen werden.

## 10. Entwicklungsphasen

| Phase | Bezeichnung | Ziel |
|---|---|---|
| I | Foundation | Datenmodelle, Regelkatalog, Protokollentwurf und Sicherheitsarchitektur |
| II | Enrollment Prototype | Lokaler Enrollment-Client, simulierte DNS-Challenges und signierte Testnachweise |
| III | Identity & Compliance | Registeradapter, Organisationsidentitäten, regulatorische Evidenz und versionierte Richtlinien |
| IV | Federation | Autorisierte Organisationsföderation, Rollenverwaltung, Zugriffskontrolle und Widerruf |
| V | Website Integration | DNS-Provider-Anbindungen, Well-Known-Dateien und API-Integration für teilnehmende Webseiten |
| VI | Governance & Production Readiness | Sicherheitsprüfung, Datenschutzfolgenabschätzung soweit erforderlich, unabhängige Tests, Dokumentation und kontrollierte Pilotierung |

## 11. Erfolgskriterien

FORINA gilt erst dann als produktionsreif, wenn mindestens folgende Bedingungen nachweislich erfüllt sind:

- Domainkontrolle ist kryptografisch beziehungsweise durch geeignete Challenge-Verfahren überprüfbar.
- Juristische Identitäten werden unabhängig von Domainkontrolle validiert.
- Compliance-Aussagen sind auf konkrete Quellen und Geltungsbereiche zurückführbar.
- Zugriffsrechte können unabhängig von Trust Records widerrufen werden.
- Unautorisierte Domains können nicht in eine aktive Föderation aufgenommen werden.
- Private Schlüssel und vertrauliche Daten bleiben geschützt.
- Jede institutionelle Vertrauensbeziehung besitzt einen dokumentierten Autorisierungsnachweis.
- Die Implementierung besteht unabhängige Sicherheits- und Integrationstests.

## 12. Schlussfolgerung

FORINA soll eine international interoperable Vertrauens- und Compliance-Infrastruktur schaffen, welche bestehende Domains, juristische Organisationsidentitäten, regulatorische Nachweise und technische Zugriffsberechtigungen miteinander verbindet.

Die Innovation liegt nicht darin, bestehende staatliche Zertifizierungsstellen zu ersetzen. Sie liegt darin, unterschiedliche bereits vorhandene Vertrauenssysteme über eine einheitliche, überprüfbare und automatisierbare Protokollschicht interoperabel zu machen.

Damit entsteht eine Grundlage für grenzüberschreitende Finanzinfrastrukturen, institutionelle Zusammenarbeit, digitale Souveränität und kontrollierte Netzwerkföderation.

**FORINA – Connecting Domains. Verifying Organizations. Federating Trust.**

Das Concept Paper ist bewusst so formuliert, dass Codex und Devin daraus technische Arbeitspakete ableiten können, ohne unautorisierte Integrationen oder Änderungen an bestehenden Systemen vorzunehmen. Der entscheidende Architekturgedanke ist: FORINA verbindet bestehende institutionelle Vertrauensnachweise, statt selbst eine neue staatliche Autorität zu behaupten.
