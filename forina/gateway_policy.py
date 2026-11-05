"""Offline connector-plan evaluation, deliberately not an authentication/ForwardAuth service.

Dictionary assertions here are not credentials. A future trusted OIDC verifier and
independent evidence/authorization services must supply this context internally.
The evaluator never authenticates input provenance and never grants access.
"""
import re
import time
from urllib.parse import urlsplit

PROFILE = 'FORINA_GATEWAY_PLAN_V1'
TOP_FIELDS = {'profile', 'policy', 'session', 'target', 'authorization', 'evidence'}
SESSION_FIELDS = {'verification_profile', 'verified', 'issuer', 'audience', 'subject',
                  'issued_at', 'expires_at', 'revoked', 'authentication_method'}
AUTHORIZATION_FIELDS = {'verification_profile', 'verified', 'subject', 'resource', 'scopes',
                        'approval_reference', 'expires_at', 'revoked'}
EVIDENCE_FIELDS = {'verification_profile', 'verified', 'reference', 'expires_at', 'revoked'}
EXTERNAL_EVIDENCE = {'domain_control', 'organization_identity', 'regulatory_evidence',
                     'federation_consent', 'jurisdiction_compatibility'}


def _shape(value, keys):
    return isinstance(value, dict) and set(value) == keys


def _text(value, limit=300):
    return isinstance(value, str) and 0 < len(value.strip()) <= limit and not any(ord(c) < 32 for c in value)


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}', value) is not None


def _identifiers(value):
    return isinstance(value, list) and 0 < len(value) <= 50 and all(_identifier(v) for v in value) and len(set(value)) == len(value)


def _issuer(value):
    if not _text(value):
        return False
    try:
        parsed = urlsplit(value)
        parsed.port
        return parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
    except ValueError:
        return False


def _current(expiry, now):
    return type(expiry) is int and expiry > now


def _decision(reasons):
    eligible = not reasons
    return {
        'profile': PROFILE,
        'decision': 'ELIGIBLE_FOR_AUTHORIZED_CONNECTOR_PLAN' if eligible else 'DENY',
        'reasons': reasons or ['ALL_DECLARED_PLANNING_PRECONDITIONS_PRESENT'],
        'eligible_for_plan': eligible,
        'access_granted': False,
        'enforcement_implemented': False,
        'input_authenticity_verified': False,
        'scope': 'OFFLINE_PLANNING_ONLY',
    }


def evaluate_gateway(context, *, now=None):
    """Evaluate an internally assembled planning context, with no network or access action.

    ``now`` is an internal test-clock injection; it must never be supplied through
    an untrusted client request. Exact schemas keep client headers, discovery
    metadata and unrecognized assertions from becoming implicit authorizations.
    """
    instant = int(time.time()) if now is None else now
    if type(instant) is not int:
        return _decision(['INVALID_EVALUATION_TIME'])
    if not _shape(context, TOP_FIELDS):
        return _decision(['INVALID_CONTEXT_SHAPE'])
    if context['profile'] != PROFILE:
        return _decision(['UNSUPPORTED_CONTEXT_PROFILE'])
    policy, session, target = context['policy'], context['session'], context['target']
    authorization, evidence = context['authorization'], context['evidence']
    if not _shape(policy, {'issuer', 'audience', 'allowed_resources'}):
        return _decision(['INVALID_POLICY_SHAPE'])
    if not _shape(session, SESSION_FIELDS):
        return _decision(['INVALID_SESSION_SHAPE'])
    if not _shape(target, {'kind', 'resource', 'required_scopes'}):
        return _decision(['INVALID_TARGET_SHAPE'])
    if not _shape(authorization, AUTHORIZATION_FIELDS):
        return _decision(['INVALID_AUTHORIZATION_SHAPE'])
    if not isinstance(evidence, dict):
        return _decision(['INVALID_EVIDENCE_SHAPE'])
    reasons = []
    if not _issuer(policy['issuer']) or not _text(policy['audience']) or not _identifiers(policy['allowed_resources']):
        reasons.append('INVALID_CONFIGURED_POLICY')
    if session['verification_profile'] != 'OIDC_VERIFIER_OUTPUT' or session['verified'] is not True:
        reasons.append('VERIFIED_OIDC_SESSION_REQUIRED')
    if not _issuer(session['issuer']) or session['issuer'] != policy['issuer']:
        reasons.append('SESSION_ISSUER_MISMATCH')
    if not _text(session['audience']) or session['audience'] != policy['audience']:
        reasons.append('SESSION_AUDIENCE_MISMATCH')
    if not _text(session['subject']):
        reasons.append('SESSION_SUBJECT_REQUIRED')
    if type(session['issued_at']) is not int or session['issued_at'] > instant or not _current(session['expires_at'], instant) or (type(session['issued_at']) is int and type(session['expires_at']) is int and session['expires_at'] <= session['issued_at']):
        reasons.append('SESSION_OUTSIDE_VALIDITY')
    if session['revoked'] is not False:
        reasons.append('SESSION_REVOKED_OR_UNKNOWN')
    if session['authentication_method'] != 'PASSKEY':
        reasons.append('VERIFIED_PASSKEY_METHOD_REQUIRED')
    if target['kind'] not in ('OWN_SERVICE', 'EXTERNAL_PORTAL'):
        reasons.append('UNSUPPORTED_TARGET_KIND')
    if not _identifier(target['resource']) or not _identifiers(target['required_scopes']):
        reasons.append('INVALID_TARGET_SCOPE')
    if not isinstance(policy['allowed_resources'], list) or target['resource'] not in policy['allowed_resources']:
        reasons.append('RESOURCE_NOT_CONFIGURED')
    if authorization['verification_profile'] != 'INDEPENDENT_AUTHORIZATION' or authorization['verified'] is not True:
        reasons.append('INDEPENDENT_AUTHORIZATION_REQUIRED')
    if not _text(authorization['subject']) or authorization['subject'] != session['subject']:
        reasons.append('AUTHORIZATION_SUBJECT_MISMATCH')
    if not _identifier(authorization['resource']) or authorization['resource'] != target['resource']:
        reasons.append('AUTHORIZATION_RESOURCE_MISMATCH')
    if not _identifiers(authorization['scopes']):
        reasons.append('INVALID_AUTHORIZATION_SCOPE')
    elif _identifiers(target['required_scopes']) and not set(target['required_scopes']).issubset(authorization['scopes']):
        reasons.append('AUTHORIZATION_SCOPE_INSUFFICIENT')
    if not _text(authorization['approval_reference']):
        reasons.append('DOCUMENTED_AUTHORIZATION_REQUIRED')
    if not _current(authorization['expires_at'], instant):
        reasons.append('AUTHORIZATION_EXPIRED_OR_UNKNOWN')
    if authorization['revoked'] is not False:
        reasons.append('AUTHORIZATION_REVOKED_OR_UNKNOWN')
    if target['kind'] == 'EXTERNAL_PORTAL':
        if set(evidence) != EXTERNAL_EVIDENCE:
            reasons.append('EXTERNAL_EVIDENCE_INCOMPLETE')
        else:
            for name in sorted(EXTERNAL_EVIDENCE):
                item = evidence[name]
                if not _shape(item, EVIDENCE_FIELDS):
                    reasons.append(name.upper() + '_INVALID_SHAPE')
                    continue
                if item['verification_profile'] != 'INDEPENDENT_EVIDENCE' or item['verified'] is not True or not _text(item['reference']):
                    reasons.append(name.upper() + '_INDEPENDENT_VERIFICATION_REQUIRED')
                if not _current(item['expires_at'], instant):
                    reasons.append(name.upper() + '_EXPIRED_OR_UNKNOWN')
                if item['revoked'] is not False:
                    reasons.append(name.upper() + '_REVOKED_OR_UNKNOWN')
    elif target['kind'] == 'OWN_SERVICE' and evidence:
        reasons.append('UNEXPECTED_OWN_SERVICE_EVIDENCE_FIELDS')
    return _decision(reasons)
