# Translate_BooK — Tradutor Editorial Inteligente de Livros (EN → PT-BR)

[![CI Pipeline](https://github.com/seu-usuario/Translate_BooK/actions/workflows/ci.yml/badge.svg)](https://github.com/seu-usuario/Translate_BooK/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Privacy: 100% Local](https://img.shields.io/badge/Privacy-100%25%20Local-success)](#privacidade-e-processamento-local)
[![Zero Telemetry](https://img.shields.io/badge/Telemetry-Zero-brightgreen)](#privacidade-e-processamento-local)

Sistema editorial de tradução automática assistida, contextualmente orientada e de alta fidelidade para livros e documentos literários/técnicos em língua inglesa para **Português Brasileiro (PT-BR)**.

---

## Filosofia do Projeto

> **"Modelo competente + Contexto correto + Memória persistente + Regras + Validação + Auditoria."**

O **Translate_BooK** rejeita a abordagem simplista de enviar parágrafos soltos para chatbots generativos em nuvem. A tradução editorial de um livro completo exige muito mais do que capacidade linguística pura: demanda **coerência intercapítulos**, **preservação de nomes próprios e termos travados**, **memória de relacionamentos entre personagens**, **verificação determinística de tags/estilos** e **auditoria contra alucinações**.

Todo o processamento é executado **100% localmente no computador do usuário** utilizando o modelo **MADLAD-400** otimizado com a biblioteca de alta velocidade **CTranslate2** em quantização INT8.

---

## Principais Funcionalidades

- **Formatos de Entrada Suportados**:
  - `TXT` (codificação UTF-8 pura);
  - `DOCX` (Word com preservação de estilos, itálico, negrito, títulos e notas);
  - `EPUB` (reconstrução determinística de estrutura XHTML, ordem de leitura e metadados);
  - `PDF Textual` (extração inteligente de fluxo de leitura sem quebras artificiais de linha);
  - `PDF Escaneado` (módulo opcional de OCR com integração Tesseract).
- **Formatos de Exportação com Integridade Estrutural**:
  - `TXT`, `DOCX` e `EPUB` reconstruídos com nomes seguros e sem nunca sobrescrever o original.
- **Pipeline Editorial Inteligente**:
  - **Style Bible & Memória de História**: Base SQLite persistente com nomes canônicos, apelidos, termos técnicos travados e diretrizes estilísticas (tom, registro formal/informal).
  - **Resolução de Contexto**: Janela contextual de 3 segmentos antes/depois injetada como auxílio sem poluir o texto traduzido.
  - **Inferência CTranslate2**: Quantização INT8 de alto desempenho para GPUs NVIDIA (CUDA) e CPUs modernas.
  - **Geração N-Best & Ranquemanento Ponderado**: Seleção do candidato ótimo combinando probabilidade neural, aderência ao glossário e métricas linguísticas.
  - **QA Determinístico & Semântico**: Verificação automática de números, pontuação, tags ausentes, similaridade semântica e backtranslation (retrotradução).
  - **Consistency Pass Intercapítulos**: Auditoria de lemas, terminologia repetida e consistência de gênero/número através dos capítulos da obra.
  - **Tolerância a Falhas**: Armazenamento transacional em SQLite (modo WAL); retomada instantânea de onde parou em caso de interrupção ou queda de energia.

---

## Requisitos de Hardware e Perfis

O aplicativo adapta-se automaticamente à capacidade do seu computador através de três perfis predefinidos:

| Perfil | Modelo de IA | RAM Mínima | VRAM Mínima (GPU) | Espaço em Disco | Velocidade Média |
|:-------|:-------------|:----------:|:-----------------:|:---------------:|:----------------:|
| **Economy** | `madlad400-3b-mt-ct2-int8` | 4 GB | 2 GB (ou CPU-only) | ~4 GB | 25 a 45 pal/s (GPU) |
| **Balanced** *(Padrão)* | `madlad400-7b-mt-ct2-int8` | 8 GB | 4 GB (ou CPU-only) | ~8 GB | 35 a 60 pal/s (GPU) |
| **Quality** | `madlad400-10b-mt-ct2-int8` | 16 GB | 8 GB | ~12 GB | 45 a 80 pal/s (GPU) |

> Para mais detalhes técnicos sobre GPU vs. CPU e benchmarks físicos, consulte o [Guia de Hardware](docs/HARDWARE_GUIDE.md).

---

## Instalação

### Opção 1: Instalador Oficial para Windows (Recomendado para Usuários)
1. Baixe o instalador `Translate_BooK_Setup_v1.0.0.exe` da aba [Releases](https://github.com/seu-usuario/Translate_BooK/releases).
2. Execute o instalador. Não são necessários privilégios de Administrador (instalação por usuário em `%LOCALAPPDATA%\Programs\Translate_BooK`).
3. O executável é standalone e **não requer Python pré-instalado**.
4. Inicie o Translate_BooK pelo atalho na Área de Trabalho ou Menu Iniciar.

### Opção 2: Instalação para Desenvolvedores
```bash
# 1. Clone o repositório
git clone https://github.com/seu-usuario/Translate_BooK.git
cd Translate_BooK

# 2. Crie e ative um ambiente virtual
python -m venv .venv
.venv\Scripts\Activate.ps1  # Windows PowerShell
# source .venv/bin/activate  # Linux/macOS

# 3. Instale a aplicação em modo editável com ferramentas de teste
pip install -e .
pip install pytest ruff pyinstaller
```

---

## Download dos Modelos de IA

Para manter o instalador leve (~60 MB) e respeitar o limite de banda dos usuários:
- **Nenhum peso de modelo de IA vem embutido no instalador ou repositório Git**.
- Na primeira execução do programa, abra **Configurações** > **Gerenciador de Modelos**.
- Escolha a versão desejada (ex: `madlad400-7b-mt-ct2-int8`) e clique em **Baixar**.
- O download é realizado via conexão criptografada HTTPS direta e a integridade de cada arquivo é auditada via hash **SHA-256** antes da ativação.

---

## Privacidade e Processamento Local

- **100% Offline**: Toda a tradução e armazenamento ocorrem no seu computador.
- **Zero Telemetria**: Sem rastreamento de uso, sem contadores ocultos, sem envio de logs.
- **Proteção de NDA**: O texto dos seus livros nunca trafega pela internet nem é compartilhado com terceiros.
- **Logs Sanitizados**: O sistema sanitiza automaticamente caminhos de sistema e nomes de usuário nos arquivos de log.
- Para instruções sobre como auditar o tráfego via firewall ou Wireshark, veja [Política de Privacidade](docs/PRIVACY.md).

---

## Como Utilizar

### Interface Gráfica (GUI)
Para iniciar a interface visual moderna (baseada em PySide6 / Qt):
```bash
python -m book_translator.ui.app
# ou, se instalado via instalador Windows, use o atalho da Área de Trabalho
```
1. **Novo Projeto**: Selecione o arquivo original (`.epub`, `.docx`, `.txt` ou `.pdf`) e o diretório de destino.
2. **Revisão de Entidades**: Verifique os personagens e termos identificados na análise preliminar.
3. **Tradução**: Acompanhe o progresso em tempo real com estatísticas de velocidade e parágrafos concluídos.
4. **Editor & Revisão**: Navegue pelos alertas de QA (números divergentes, consistência terminológica) e edite diretamente o texto.
5. **Exportação**: Exporte o livro final no formato de sua escolha.

### Linha de Comando (CLI) & Diagnóstico
```bash
# Relatório de diagnóstico do sistema (Hardware, CUDA, Modelos e Dependências)
book-translator --diagnostics

# Tradução direta via linha de comando
book-translator --input livro.epub --profile balanced --output ./saida/
```

---

## Limitações Conhecidas

- **Layouts Complexos em PDF**: Revistas de múltiplas colunas ou quadrinhos possuem fluxo de leitura não linear e podem exigir revisão visual adicional.
- **Pares de Idiomas**: O motor atual é estritamente calibrado e homologado para **Inglês (EN) → Português Brasileiro (PT-BR)**.
- **Consumo de Memória**: O modelo 10B requer no mínimo 16 GB de RAM ou 8 GB de VRAM dedicados para manter fluidez operacional.

---

## Solução de Problemas

Encontrou alguma dificuldade? Consulte o nosso guia completo de [Solução de Problemas e FAQ](docs/TROUBLESHOOTING.md), cobrindo:
- Como resolver erros de *CUDA Out of Memory*;
- Configuração do Tesseract OCR;
- Recuperação de projetos após desligamento repentino;
- Gestão de espaço em disco.

---

## Contribuição e Código de Conduta

Contribuições são muito bem-vindas! Consulte:
- [Guia de Contribuição](CONTRIBUTING.md) para instruções de desenvolvimento, padrões de testes e arquitetura.
- [Código de Conduta](CODE_OF_CONDUCT.md) para normas de convivência na comunidade.

---

## Segurança

Para reportar vulnerabilidades de forma responsável e confidencial, leia nossa [Política de Segurança](SECURITY.md).

---

## Créditos e Licenças de Terceiros

Este projeto faz uso e presta homenagem às seguintes tecnologias de código aberto:

- **MADLAD-400**: Modelo neural multilíngue de tradução desenvolvido pela Google Research sob licença [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0).
- **CTranslate2**: Motor de inferência acelerada em C++/CUDA desenvolvido pela SYSTRAN sob licença [MIT](https://github.com/OpenNMT/CTranslate2/blob/master/LICENSE).
- **PySide6**: Bindings oficiais do Qt para Python desenvolvidos pelo The Qt Company sob licença [LGPLv3](https://www.gnu.org/licenses/lgpl-3.0.html).
- **pypdf**: Biblioteca pura de extração e manipulação de PDF sob licença [BSD 3-Clause](https://github.com/py-pdf/pypdf/blob/main/LICENSE).
- **SQLite**: Motor de banco de dados relacional embarcado em [Domínio Público](https://www.sqlite.org/copyright.html).
- **Tesseract OCR**: Motor de reconhecimento óptico de caracteres mantido pelo Google sob licença [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0).

---

## Licença

Este projeto é distribuído sob os termos da licença **MIT**. Consulte o arquivo [LICENSE](LICENSE) para mais detalhes.
