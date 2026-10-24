from pathlib import Path
from streamlit.testing.v1 import AppTest

def test_render_empty(tmp_path,monkeypatch):
    from research import store
    monkeypatch.setattr(store,'DB_PATH',tmp_path/'absent.sqlite')
    at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=15).run()
    assert not at.exception
    assert any('has not published' in x.value for x in at.info)

def test_render_manual_and_switch(fixture_db,monkeypatch):
    from research import store
    import urllib.request
    monkeypatch.setattr(store,'DB_PATH',fixture_db)
    original_connect=store.connect
    def fixture_connect(path=None,readonly=True):return original_connect(fixture_db,readonly)
    monkeypatch.setattr(store,'connect',fixture_connect)
    def deny(*a,**kw):raise AssertionError('Interactive rendering attempted network request')
    monkeypatch.setattr(urllib.request,'urlopen',deny)
    at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=20).run()
    assert not at.exception
    at.radio[0].set_value('Manual teams').run()
    assert not at.exception
    assert any('STATISTICAL CONFIDENCE LEVELS' in x.value for x in at.markdown)
    at.selectbox[1].set_value('2').run()
    assert not at.exception
    at.checkbox[1].check().run()
    assert not at.exception
    assert all('TEST FIXTURE' in x.value or 'old' in x.value for x in at.warning)
