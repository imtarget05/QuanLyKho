"""Heuristic AI risk assessment — pure function, no DB or external API required.

Covers assess_request_heuristic: cash/quỹ, adjustment/stocktake, receipt,
and default (issue/transfer) kinds across all value thresholds, plus
short-reason penalty and audit stamp generation.
"""
from app.services.ai import assess_request_heuristic


def _base_data(**overrides):
    data = {
        'request_id': 'req-001',
        'kind': 'cash',
        'amount_or_qty': '100',
        'maker': 'Trưởng ca',
        'reason': 'Lý do đầy đủ và rõ ràng cho phiếu này.',
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Cash / quỹ kind — ngưỡng kiểm soát kép 500 triệu VND
# ---------------------------------------------------------------------------
def test_cash_low_value():
    data = _base_data(kind='cash', amount_or_qty='50.000.000')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'low'
    assert result['risk_score'] == 20
    assert 'định mức' in result['recommendations'][0]


def test_cash_medium_value():
    data = _base_data(kind='cash', amount_or_qty='300.000.000')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'medium'
    assert result['risk_score'] == 58


def test_cash_high_value():
    data = _base_data(kind='cash', amount_or_qty='600.000.000')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'high'
    assert result['risk_score'] == 88
    assert 'kiểm soát kép' in result['flagged_rules'][0]
    assert 'PIN Kiểm soát viên' in result['recommendations'][0]


def test_cash_boundary_200m():
    data = _base_data(kind='cash', amount_or_qty='200.000.000')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'medium'


def test_cash_boundary_500m():
    data = _base_data(kind='cash', amount_or_qty='500.000.000')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'high'


def test_cash_quỹ_alias():
    data = _base_data(kind='quỹ', amount_or_qty='100.000.000')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'low'


# ---------------------------------------------------------------------------
# Adjustment / stocktake kind
# ---------------------------------------------------------------------------
def test_adjustment_low_value():
    data = _base_data(kind='adjustment', amount_or_qty='2')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'low'
    assert result['risk_score'] == 18


def test_adjustment_medium_value():
    data = _base_data(kind='adjustment', amount_or_qty='5')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'medium'
    assert result['risk_score'] == 55


def test_adjustment_high_value():
    data = _base_data(kind='adjustment', amount_or_qty='15')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'high'
    assert result['risk_score'] == 82
    assert 'đối chiếu' in result['flagged_rules'][0]


def test_stocktake_alias():
    data = _base_data(kind='stocktake', amount_or_qty='5')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'medium'


# ---------------------------------------------------------------------------
# Receipt kind
# ---------------------------------------------------------------------------
def test_receipt_low_value():
    data = _base_data(kind='receipt', amount_or_qty='10')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'low'
    assert result['risk_score'] == 20


def test_receipt_medium_value():
    data = _base_data(kind='receipt', amount_or_qty='50')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'medium'
    assert result['risk_score'] == 52
    assert 'Max kho' in result['flagged_rules'][0]


# ---------------------------------------------------------------------------
# Default kind (issue / transfer / unknown)
# ---------------------------------------------------------------------------
def test_issue_low_value():
    data = _base_data(kind='issue', amount_or_qty='10')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'low'
    assert result['risk_score'] == 18


def test_issue_high_value():
    data = _base_data(kind='issue', amount_or_qty='100')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'medium'
    assert result['risk_score'] == 50


def test_transfer_kind():
    data = _base_data(kind='transfer', amount_or_qty='5')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'low'


def test_unknown_kind_defaults_to_low():
    data = _base_data(kind='unknown_type', amount_or_qty='1')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'low'


# ---------------------------------------------------------------------------
# Short reason penalty (< 5 ký tự)
# ---------------------------------------------------------------------------
def test_short_reason_penalty_upgrades_low_to_medium():
    data = _base_data(kind='cash', amount_or_qty='50.000.000', reason='ok')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'medium'
    assert result['risk_score'] == 35  # 20 + 15
    assert 'quá ngắn' in result['flagged_rules'][0]


def test_short_reason_penalty_high_stays_high():
    data = _base_data(kind='cash', amount_or_qty='600.000.000', reason='no')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'high'
    assert result['risk_score'] == min(98, 88 + 15)


def test_empty_reason_penalty():
    data = _base_data(kind='cash', amount_or_qty='50.000.000', reason='')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'medium'
    assert any('quá ngắn' in rule for rule in result['flagged_rules'])


def test_reason_exactly_4_chars_is_short():
    data = _base_data(kind='cash', amount_or_qty='50.000.000', reason='abcd')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'medium'


def test_reason_exactly_5_chars_is_ok():
    data = _base_data(kind='cash', amount_or_qty='50.000.000', reason='abcde')
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'low'


# ---------------------------------------------------------------------------
# Amount string parsing
# ---------------------------------------------------------------------------
def test_amount_with_dots_and_commas():
    data = _base_data(kind='cash', amount_or_qty='1.234.567,89')
    result = assess_request_heuristic(data)
    assert result['risk_score'] == 20  # low (< 200M)


def test_amount_with_no_digits():
    data = _base_data(kind='cash', amount_or_qty='abc')
    result = assess_request_heuristic(data)
    assert result['risk_score'] == 20  # value = 0


def test_amount_zero():
    data = _base_data(kind='cash', amount_or_qty='0')
    result = assess_request_heuristic(data)
    assert result['risk_score'] == 20


# ---------------------------------------------------------------------------
# Audit stamp (SHA-256, 64 hex chars)
# ---------------------------------------------------------------------------
def test_audit_stamp_is_sha256():
    data = _base_data(kind='cash', amount_or_qty='100')
    result = assess_request_heuristic(data)
    stamp = result['audit_stamp']
    assert len(stamp) == 64
    assert all(c in '0123456789abcdef' for c in stamp)


def test_audit_stamp_deterministic():
    data = _base_data(kind='cash', amount_or_qty='100')
    r1 = assess_request_heuristic(data)
    r2 = assess_request_heuristic(data)
    assert r1['audit_stamp'] == r2['audit_stamp']


def test_audit_stamp_changes_with_input():
    data1 = _base_data(kind='cash', amount_or_qty='100')
    data2 = _base_data(kind='cash', amount_or_qty='200')
    r1 = assess_request_heuristic(data1)
    r2 = assess_request_heuristic(data2)
    assert r1['audit_stamp'] != r2['audit_stamp']


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
def test_default_request_id():
    data = {'kind': 'cash', 'amount_or_qty': '100', 'maker': 'X', 'reason': 'Lý do đầy đủ.'}
    result = assess_request_heuristic(data)
    assert result['request_id'] == 'REQ-000'


def test_default_kind_is_cash():
    data = {'request_id': 'r1', 'amount_or_qty': '100', 'maker': 'X', 'reason': 'Lý do đầy đủ.'}
    result = assess_request_heuristic(data)
    assert result['risk_level'] == 'low'


def test_returned_keys():
    result = assess_request_heuristic(_base_data())
    expected_keys = {
        'request_id', 'risk_level', 'risk_score', 'summary',
        'flagged_rules', 'recommendations', 'audit_stamp',
    }
    assert set(result.keys()) == expected_keys


def test_summary_contains_risk_info():
    result = assess_request_heuristic(_base_data(kind='cash', amount_or_qty='600.000.000'))
    assert 'HIGH' in result['summary']
    assert '88' in result['summary']
    assert 'req-001' in result['summary']