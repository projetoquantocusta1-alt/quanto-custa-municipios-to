# Quanto Custa — Prefeituras e câmaras do Tocantins

Quanto custam as câmaras municipais e as prefeituras dos municípios do Tocantins, desde 2017, corrigido pela
inflação. Aparece na página única dos municípios: https://quantocustaum.com/quanto-custa-municipios/?uf=to

Mesmo código do repositório da Bahia (quanto-custa-municipios-ba). Só muda o bloco "ESTADO" em `config.py` e o
bloco CFG no começo de `docs/uf.js`.

## Fontes
- **SICONFI (Tesouro Nacional)**: RREO, Anexo 2 (despesa por função). A câmara é a função "Legislativa".
- **TSE**: eleitos de 2016, 2020 e 2024. **IBGE**: população. **Banco Central**: IPCA.

## Limitações (explicadas no site)
- Sem nota a nota, fornecedores e gabinetes: só o TCE-TO tem, e o robô ainda não foi testado no site dele.
- O RREO traz o empenhado e o liquidado por função, não o pago.
- Prefeituras que não entregam o relatório ao Tesouro ficam fora do ano e são listadas no site.

## Robô
`python atualizar.py` (todo dia, GitHub Actions). `--semanal` também baixa TSE, IBGE e IPCA.
