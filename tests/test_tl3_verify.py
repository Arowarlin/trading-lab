"""E2 · Verificación: lo habría cazado y registro."""

from __future__ import annotations

import pytest

from tradinglab.tl3 import registry, verify


def test_magnitude_caza_swap_100x():
    check = verify.magnitude("SWAP_BPS", 200.8, 0.5, 5.0)
    assert check["ok"] is False
    assert check["defect"] is True
    assert check["factor"] > 3


def test_magnitude_aviso_sin_llegar_a_factor_3():
    check = verify.magnitude("coste", 6.0, 0.5, 5.0)
    assert check["ok"] is False
    assert check["defect"] is False
    assert check["status"] == "aviso"


def test_tolerancia_de_puntos_usada_como_precio():
    check = verify.magnitude("tolerancia 2x90 puntos como precio", 2 * 90, 0, 100, factor=1.0)
    assert check["ok"] is False
    assert check["defect"] is True


def test_constants_match_caza_371_frente_a_357():
    rows = verify.constants_match({"session_min": 357}, {"session_min": 371})
    assert len(rows) == 1
    assert rows[0]["ok"] is False
    assert rows[0]["defect"] is True


def test_huella_48_primeras_distinta_de_t5():
    t5 = [
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 17, 18, 19, 20,
        21, 22, 23, 24, 25, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38,
        39, 40, 41, 43, 44, 45, 47, 48, 49, 50, 51, 53,
    ]
    primeras = [52 if value == 53 else value for value in t5]
    assert len(t5) == 48 and len(primeras) == 48
    assert verify.sample_fingerprint(t5) != verify.sample_fingerprint(primeras)
    assert verify.sample_fingerprint(t5) == verify.sample_fingerprint(reversed(t5))


def test_trigger_rate_fuera_de_mitad_o_doble():
    assert verify.trigger_rate(0.6, 1.0)["ok"] is True
    assert verify.trigger_rate(2.5, 1.0)["defect"] is True


def test_reporte_conforma_y_defectos():
    ok = verify.magnitude("tick", 0.5, 0.5, 0.5)
    assert "Veredicto: Conforma" in verify.report([ok])
    bad = verify.magnitude("swap", 200.8, 0.5, 5.0)
    assert "Veredicto: Defectos" in verify.report([ok, bad])


def test_verifications_solo_anaden_y_requieren_conforma(tmp_path):
    db = tmp_path / "tl3.db"
    registry.init_db(db)
    registry.add_verification("NQF-A", "hash-ok", "sesion-b", "Conforma", "informe", db_path=db)
    registry.require_verified("NQF-A", "hash-ok", db_path=db)
    with pytest.raises(registry.VerificationRequired):
        registry.require_verified("NQF-A", "hash-otro", db_path=db)
    registry.add_verification("NQF-A", "hash-malo", "sesion-b", "Defectos", "informe", db_path=db)
    with pytest.raises(registry.VerificationRequired):
        registry.require_verified("NQF-A", "hash-malo", db_path=db)
    with registry.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM verifications").fetchone()[0] == 2
