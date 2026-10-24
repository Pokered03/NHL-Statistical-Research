from research.market_validation import metrics,evaluate

def test_missing_lines_do_not_fabricate_validation():
    cal=[{'actual_margin':1,'margin':0,'actual_total':10,'total':10}]*10
    result=evaluate(cal,[{'actual_margin':1,'margin':0,'actual_total':10,'total':10}])
    assert result['spread']['n']==0 and not result['spread']['gate']
    assert result['total']['n']==0 and not result['total']['gate']

def test_pushes_excluded_and_spread_sign():
    cal=[{'actual_margin':0,'margin':0,'actual_total':10,'total':10}]*10
    rows=[{'actual_margin':7,'margin':5,'actual_total':11,'total':10,'home_spread':-3,'market_total':10},
          {'actual_margin':3,'margin':5,'actual_total':10,'total':10,'home_spread':-3,'market_total':10}]
    result=evaluate(cal,rows)
    assert result['spread']['n']==1 and result['spread']['pushes_excluded']==1
    assert result['spread']['brier']==0
    assert result['total']['pushes_excluded']==1
    assert not result['spread']['gate']

def test_confidence_category_requires_heldout_evidence():
    r=metrics([{'p':.7,'y':1}]*200)
    assert r['categories']['strong']['supported']
    # Constant 70% predictions that win 100% are poorly calibrated; cannot pass the probability gate.
    assert not r['gate']
