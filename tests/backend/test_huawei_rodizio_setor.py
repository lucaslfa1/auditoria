import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from core.huawei_sync import _selecionar_rodizio_por_setor


def _c(setor, ident):
    return {"_setor_rodizio": setor, "id": ident}


class TestRodizioPorSetor(unittest.TestCase):
    def test_balanceia_em_vez_de_um_setor_dominar(self):
        # 10 cadastro + 3 uti + 2 fenix, 6 vagas -> nao pode vir 6 cadastro.
        cands = (
            [_c("cadastro", i) for i in range(10)]
            + [_c("uti", 100 + i) for i in range(3)]
            + [_c("fenix", 200 + i) for i in range(2)]
        )
        sel = _selecionar_rodizio_por_setor(cands, 6)
        self.assertEqual(len(sel), 6)
        setores = [c["_setor_rodizio"] for c in sel]
        self.assertLessEqual(setores.count("cadastro"), 2)
        self.assertIn("uti", setores)
        self.assertIn("fenix", setores)

    def test_rodizio_pega_primeiro_de_cada_setor_na_ordem(self):
        cands = [_c("cadastro", 1), _c("cadastro", 2), _c("uti", 3)]
        sel = _selecionar_rodizio_por_setor(cands, 2)
        self.assertEqual([c["id"] for c in sel], [1, 3])

    def test_poucos_candidatos_devolve_intacto(self):
        cands = [_c("cadastro", 1), _c("uti", 2)]
        self.assertEqual(_selecionar_rodizio_por_setor(cands, 5), cands)
        self.assertEqual(_selecionar_rodizio_por_setor(cands, 0), cands)

    def test_preserva_ordem_dentro_do_setor(self):
        # cadastro tem volume; ao esgotar uti, completa com cadastro na ordem.
        cands = [_c("cadastro", 1), _c("cadastro", 2), _c("uti", 3), _c("cadastro", 4)]
        sel = _selecionar_rodizio_por_setor(cands, 3)
        # rodizio: cadastro(1), uti(3), volta cadastro(2)
        self.assertEqual([c["id"] for c in sel], [1, 3, 2])

    def test_sem_setor_nao_quebra(self):
        cands = [{"id": 1}, {"id": 2}, {"id": 3}]
        sel = _selecionar_rodizio_por_setor(cands, 2)
        self.assertEqual(len(sel), 2)


if __name__ == "__main__":
    unittest.main()
