# Changelog — Translate_BooK

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/lang/pt-BR/).

---

## [1.0.0] — 2026-09-20

### Lançamento Inicial Estável (Release v1.0.0)

Primeira versão oficial de produção do **Translate_BooK**, um sistema editorial completo de tradução automática assistida e contextualmente orientada de livros e documentos do inglês para o Português Brasileiro (PT-BR).

#### Destaques
- **Processamento 100% Local**: Nenhuma dependência de nuvem, APIs pagas ou envio de dados a terceiros.
- **Zero Telemetria**: Privacidade absoluta sob acordos de confidencialidade (NDAs).
- **Filosofia Editorial**: "Modelo competente + Contexto correto + Memória persistente + Regras + Validação + Auditoria."

#### Funcionalidades Adicionadas
- **Ingestão Multi-Formato**:
  - Suporte completo a `TXT` (UTF-8).
  - Suporte a `DOCX` com preservação nativa de itálicos, negritos, notas e estilos.
  - Suporte a `EPUB` (EPUB 2/3) com descompressão segura e ordem de leitura canônica.
  - Suporte a `PDF Textual` com reconstrução de fluxo e heurísticas de eliminação de quebras artificiais.
  - Módulo de `OCR` integrado e opcional para PDFs escaneados via Tesseract.
- **Memória Editorial Persistente (SQLite em Modo WAL)**:
  - *Style Bible*: Controle de tom, registro linguístico (formal/informal) e diretrizes por obra.
  - *Memória de Personagens & Entidades*: Resolução de aliases, gênero gramatical e apelidos.
  - *Glossário de Termos Travados*: Preservação 100% garantida de termos canônicos.
  - *Histórico de Revisão e Auditoria*: Registro reversível de todas as alterações.
- **Resolução de Contexto**:
  - Injeção inteligente de janela contextual (3 segmentos antes e depois) para desambiguação sem contaminação do texto final.
- **Motor de Tradução e Inferência**:
  - Integração com **MADLAD-400** em quantização **INT8** acelerada por **CTranslate2**.
  - Perfis de hardware pré-calibrados: *Economy* (3B), *Balanced* (7B) e *Quality* (10B).
  - Suporte automático a aceleração por GPU NVIDIA (CUDA) com fallback robusto para CPU.
  - Geração N-Best e rankeamento ponderado por aderência estilística e terminológica.
  - Cache persistente por hash de segmento, evitando retradução de parágrafos inalterados.
- **Controle de Qualidade (QA)**:
  - *QA Determinístico*: Verificação de paridade numérica, pontuação, tags XML e termos travados.
  - *QA Semântico*: Avaliação de similaridade vetorial e desvios de significado.
  - *Retrotradução (Backtranslation)*: Validação cruzada PT-BR → EN.
- **Consistency Pass Intercapítulos**:
  - Auditoria global através de todos os capítulos para detecção de termos traduzidos de formas divergentes, inconsistências de pronomes e títulos de nobreza.
  - Correções automáticas restritas a *Safe Fixes* com suporte total a *rollback*.
- **Exportação Determinística**:
  - Exportação para `TXT`, `DOCX` e `EPUB 3` sem nunca sobrescrever o original.
  - Nomenclatura higienizada e segura.
- **Interface Gráfica Moderna (PySide6 / Qt)**:
  - Assistente de Novo Projeto com análise preliminar de entidades.
  - Visualizador de progresso em tempo real (palavras/segundo, parágrafos concluídos, ETA).
  - Painel de revisão interativo com alertas de QA e edição cirúrgica de segmentos.
- **Segurança e Hardening**:
  - Proteção contra *Path Traversal* (`path_guard.py`).
  - Proteção contra *Zip Slip* e *Zip Bombs* (`zip_guard.py`).
  - Prevenção contra *XXE* e *Billion Laughs* (`xml_guard.py`).
  - Filtro sanitizador de logs com redação de caminhos e dados sensíveis (`PrivacySanitizingFilter`).
  - Validação estrita de integridade via checksum **SHA-256** em todos os downloads.
- **Empacotamento e Distribuição Windows**:
  - Executável standalone gerado via PyInstaller (sem console, runtime Python embutido).
  - Instalador oficial via Inno Setup (`Translate_BooK_Setup_v1.0.0.exe`) com instalação por usuário (`PrivilegesRequired=lowest`).
  - Preservação estrita dos projetos do usuário em `%APPDATA%\Translate_BooK\projects` durante desinstalações e atualizações.
  - Pacote portátil `.zip` para execução direta.
