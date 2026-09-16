# Tradutor Inteligente de Livros e Documentos (EN → PT-BR)

Sistema editorial de tradução automática assistida e orientada a contexto para livros e documentos em inglês para Português Brasileiro (PT-BR).

## Filosofia do Projeto

> **"Modelo competente + Contexto correto + Memória persistente + Regras + Validação + Auditoria."**

O projeto não trata a tradução como envio isolado de parágrafos para uma API ou chat generativo. Ele funciona como uma **pipeline editorial completa**, com memórias de personagens e termos, análise global prévia da obra, controle semântico e determinístico de qualidade (QA) e revisão de consistência intercapítulos.

O motor inicial de tradução é o **MADLAD-400-10B-MT**, executado localmente e desacoplado do núcleo da aplicação.

## Estrutura do Projeto

Consulte [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) para a arquitetura técnica detalhada e [`docs/PROJECT_SPECIFICATION_PT-BR.txt`](docs/PROJECT_SPECIFICATION_PT-BR.txt) para a especificação original.

## Instalação em Desenvolvimento

```bash
# Clone o repositório
git clone <repo-url>
cd Translate_BooK

# Instalação editável
pip install -e .

# Execução de testes
pytest
```

## Diagnóstico do Sistema

Para verificar o ambiente e a versão atual instalada:

```bash
book-translator --diagnostics
# ou
python -m book_translator.cli --diagnostics
```
