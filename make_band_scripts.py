# -*- coding: utf-8 -*-
# Генератор neiry_band_1/2/3.py из _template_neiry_band.py.
# ПРАВИТЬ ЛОГИКУ ТОЛЬКО В ШАБЛОНЕ, потом: python make_band_scripts.py
# Раскладка бендов/портов/стен — таблица BANDS ниже.
import ast
import os

HERE = os.path.dirname(os.path.abspath(__file__))

BANDS = [
    dict(N='1', LABEL='R', ADDR='F7:14:0E:FE:9D:20', PORT='9003', EVT='9013', LOCKPORT='47654', DELAY='0'),
    dict(N='2', LABEL='C', ADDR='C6:0D:7C:18:44:AA', PORT='9002', EVT='9012', LOCKPORT='47655', DELAY='10'),
    dict(N='3', LABEL='L', ADDR='EF:21:DE:1C:A3:67', PORT='9001', EVT='9011', LOCKPORT='47656', DELAY='20'),
]

tpl = open(os.path.join(HERE, '_template_neiry_band.py'), encoding='utf-8').read()
for b in BANDS:
    out = tpl
    for k, v in b.items():
        out = out.replace('@@%s@@' % k, v)
    assert '@@' not in out, 'незамещённый плейсхолдер (бенд %s)' % b['N']
    ast.parse(out)  # проверка синтаксиса до записи
    path = os.path.join(HERE, 'neiry_band_%s.py' % b['N'])
    open(path, 'w', encoding='utf-8').write(out)
    print('OK', path)
