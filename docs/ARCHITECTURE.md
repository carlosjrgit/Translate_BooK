# Arquitetura Técnica — Tradutor Inteligente de Livros (EN → PT-BR)

## 1. Visão Geral do Sistema

O objetivo deste projeto é fornecer uma esteira editorial automatizada que recebe obras completas em inglês (PDF, EPUB, DOCX, TXT, MD, HTML) e produz um documento traduzido e revisado em Português Brasileiro (PT-BR) preservando estrutura, tom, voz autoral e consistência global.

### Princípio de Separação
- **Motor de Tradução (`TranslationEngine`)**: Responsável estritamente pela tradução textual direta de segmentos (ex: adaptador para MADLAD-400-10B-MT).
- **Cérebro Editorial (`Core & Modules`)**: Responsável por todo o restante — ingestão, normalização, análise da obra, memórias de longo prazo, injeção seletiva de contexto, validação em múltiplas camadas (QA determinístico e semântico), auditoria global e exportação.

---

## 2. Diagrama de Fluxo e Relacionamento entre Módulos

```
                                [ARQUIVO ORIGINAL]
                                        │
                                        ▼
                               ┌─────────────────┐
                               │    Ingestion    │
                               │ (Detecta Formato│
                               │  e Camada Texto)│
                               └────────┬────────┘
                                        │
                                        ▼
                               ┌─────────────────┐
                               │     Parsers     │ ◄─── (PDF, EPUB, DOCX, TXT, MD)
                               └────────┬────────┘
                                        │
                                        ▼
                         ┌─────────────────────────────┐
                         │      Document (Model)       │
                         │ (Estrutura Canônica:        │
                         │  Capítulos, Parágrafos,     │
                         │  Notas, Metadados)          │
                         └──────────────┬──────────────┘
                                        │
                                        ▼
                               ┌─────────────────┐
                               │    Analysis     │
                               │ (Varredura prévia│
                               │  de Entidades,  │
                               │  Tom e Relações)│
                               └────────┬────────┘
                                        │
                                        ▼
                      ┌────────────────────────────────────┐
                      │          Project Memory            │
                      │  ┌──────────────────────────────┐  │
                      │  │ Character Memory             │  │
                      │  │ Translation Memory           │  │
                      │  │ Glossary                     │  │
                      │  │ Style Bible                  │  │
                      │  │ Story Memory                 │  │
                      │  └──────────────────────────────┘  │
                      │  Armazenamento: SQLite + JSON      │
                      └─────────────────┬──────────────────┘
                                        │
                                        ▼
                               ┌─────────────────┐
                               │Context Retrieval│ ◄─── (Recupera contexto estritamente
                               └────────┬────────┘      relevante para o segmento atual)
                                        │
                                        ▼
                               ┌─────────────────┐
                               │TranslationEngine│ ◄─── (MADLADAdapter / CTranslate2 / llama.cpp)
                               └────────┬────────┘      (N-Best Candidates opcional)
                                        │
                                        ▼
                               ┌─────────────────┐
                               │ Quality Assur.  │
                               │  ┌───────────┐  │
                               │  │Determinis.│  │ ◄─── (Datas, números, URLs, medidas)
                               │  │Semantic QA│  │ ◄─── (Omissões, acréscimos, distorções)
                               │  │Backtrans. │  │ ◄─── (Evidência auxiliar)
                               │  └───────────┘  │
                               └────────┬────────┘
                                        │ (Classifica: SAFE FIX / SUGGESTED FIX / REVIEW REQUIRED)
                                        ▼
                               ┌─────────────────┐
                               │  Consistency    │
                               │ (Auditoria global│
                               │  pós-tradução da │
                               │  obra completa)  │
                               └────────┬────────┘
                                        │
                                        ▼
                               ┌─────────────────┐
                               │     Export      │ ◄─── (EPUB, DOCX, TXT com estrutura preservada)
                               └─────────────────┘
```

---

## 3. Descrição dos Módulos e Responsabilidades

### 3.1 `core`
- **`models.py`**: Modelos de domínio fundamentais:
  - `Document`: Contêiner intermediário agnóstico ao formato original.
  - `Chapter`: Unidade macro de organização textual.
  - `Segment`: Menor unidade tradutível atômica, dotada de identificador permanente (`chapter_001_segment_0042`), hash de cache, estado de ciclo de vida (`PENDING`, `TRANSLATED`, `VALIDATED`, `FLAGGED`) e histórico de revisões.
  - `Project`: Entidade que ancora o livro, seu diretório em `projects/<book_name>/`, banco SQLite `project.db`, cache e metadados.
- **`contracts.py`**: Definição dos protocolos formais tipados (`Protocol`) que desacoplam os módulos.

### 3.2 `ingestion` & `parsers`
- **`IngestionInspector`**: Realiza triagem e inspeção prévia sem carregar o arquivo inteiro na memória:
  - Detecção de formato por combinação de extensão insensível a maiúsculas/minúsculas e inspeção de magic bytes (`PK` para DOCX/EPUB, `%PDF-` para PDF, tags para HTML).
  - Triagem de qualidade em PDFs: classifica o documento como `TEXTUAL` (100% de páginas com texto útil), `MIXED` (páginas mistas texto/imagem) ou `SCANNED_NEEDS_OCR` (rejeitado precocemente com `NeedsOcrError`).
  - Salvaguarda de segurança: verificação de caminhos (`Path.resolve`), rejeição de diretórios como arquivos e limite configurável de tamanho de arquivo (`max_file_size_bytes`).
  - **Imutabilidade Absoluta**: Leitura estritamente em modo `rb`; o arquivo de entrada original nunca é modificado ou sobrescrito.
- **Parsers Implementados**:
  - `TxtParser`: Suporte a UTF-8, detecção automática de encoding via `chardet` (com fallbacks para latin-1/windows-1252), remoção de UTF-8 BOM, segmentação de capítulos baseada em regex e classificação de diálogos.
  - `MarkdownParser`: Tokenização estrutural em AST via `markdown-it-py`, mapeamento de níveis de heading, spans inline (negrito, itálico, código, links) e notas de rodapé (`[^1]`).
  - `HtmlParser`: Parsing semântico via `BeautifulSoup` (parser `lxml`), extração de headings (`h1` a `h6`), parágrafos, spans de formatação (`b`, `i`, `em`, `strong`, `code`, `a`), tratamento de ruby/sup/sub e extração de imagens.
  - `DocxParser`: Processamento XML nativo de `word/document.xml` e `word/footnotes.xml`, mapeamento de estilos de parágrafo, extração de runs tipográficos e extração de notas de rodapé com IDs de referência.
  - `EpubParser`: Leitura de arquivos `.epub` (EPUB2 e EPUB3), navegação pelo manifesto OPF e `spine` para ordem estrita de leitura, descarte de itens de navegação repetidos (TOC/nav) para evitar duplicação textual e retenção de metadados de empacotamento para reconstrução futura.
  - `PdfParser`: Extração textual via `pypdf`, recomposição de palavras quebradas por hifenização de fim de linha (`extraor-` + `dinary`), eliminação estatística de cabeçalhos e rodapés recorrentes por limite de frequência e supressão de numeração de páginas isolada.
- **`normalization`**: Executa normalização Unicode canônica (NFKC), normalização de espaços em branco, padronização de aspas/hífens editoriais e classificação de blocos de diálogo via marcadores canônicos (`—`, `–`, `"`, `«`).

### 3.3 `analysis`
- Varre a obra integralmente antes do início da tradução para caracterizar o universo e o estilo da obra:
  - **`BookAnalyzer`**: Orquestrador central de análise que realiza a leitura integral da hierarquia documental sem inventar informações ausentes.
  - **NER Abstrato e Plugável (`NERInterface`)**: Interface desacoplada que permite plugar diferentes motores de reconhecimento de entidades (heurísticos, modelos locais spaCy/transformers ou LLMs) sem reescrever a lógica de domínio. Implementação inicial funcional e leve via `HeuristicNER`.
  - **Diferenciação Fato vs. Inferência**: Fatos observados (menções, contagem de ocorrências, offsets, snippets) são registrados em `EntityOccurrence`. Inferências (gênero gramatical, resoluções de alias) são explicitamente registradas em `EntityInference` com nível de confiança (0.0 a 1.0) e snippet de evidência textual de origem.
  - **Consolidação de Aliases e Tratamento de Homônimos (`AliasResolver`)**: Consolida menções unívocas (ex: "Dr. John Watson" e "Watson") em entidades canônicas únicas; marca homônimos ambíguos (ex: múltiplos personagens compartilhando o mesmo sobrenome "Henderson") com a flag `is_ambiguous = True` sem fusão forçada.
  - **Extração de Relações (`RelationExtractor`)**: Extrai laços familiares e interpessoais (ex: "Arthur's mother Margaret" -> `mother_of`) com vínculos explícitos entre entidades, tipo de relação, confiança e citação textual de evidência.
  - **Persistência em Memórias**: Popula automaticamente o banco do projeto (`CharacterEntry`, `Entity`, `GlossaryEntry` e estimativa de narrador na `StyleBible`).

### 3.4 `memory`
- **`CharacterMemory`**: Mapeia personagens, aliases, relações familiares/hierárquicas, sexo/gênero gramatical (para concordância de pronomes) e registro de fala.
- **`TranslationMemory`**: Armazena termos e construções frasais recorrentes com status `locked` para impedir oscilações entre capítulos distantes.
- **`Glossary`**: Conceitos técnicos, organizações e vocabulário com case-sensitivity e notas de contexto.
- **`StyleBible`**: Diretrizes editoriais da obra (narrador, formalidade, uso de você/tu/senhor, profanidades, convenção de pontuação).

### 3.5 `context`
- **`ContextRetrieval`**: Seleciona e empacota o contexto ótimo para o segmento atual (parágrafos limítrofes, resumo local, personagens presentes na cena e termos aplicáveis do glossário), evitando tanto subcontexto quanto sobrecarga do modelo.

### 3.6 `translation`
- **`TranslationEngine`**: Interface abstrata de tradução.
- **`MADLADAdapter`**: Adaptador desacoplado para a família MADLAD-400 (ex: 10B-MT).
- **`CandidateRanker`**: Mecanismo opcional para ranqueamento de hipóteses *N-best*.

### 3.7 `qa` (Controle de Qualidade)
- **`DeterministicQA`**: Regras estritas por código determinístico para validação de integridade factual (números, datas, anos, valores monetários, medidas, negações lógicas, pontuação crítica).
- **`SemanticQA`**: Análise semântica para identificação de alucinações, omissões severas de cláusulas ou alterações bruscas de polaridade/tom.
- **`Backtranslation`**: Tradução de retorno avaliada como evidência auxiliar indicativa de desvios.
- Classificação de anomalias:
  - `SAFE_FIX`: Correção automática segura.
  - `SUGGESTED_FIX`: Sugestão provável de ajuste.
  - `REVIEW_REQUIRED`: Sinalização para decisão editorial manual.

### 3.8 `consistency`
- Realiza um *Consistency Pass* após a conclusão da tradução da obra inteira.
- Identifica divergências acumuladas ao longo dos capítulos (ex: "The Iron Guard" traduzido de formas diferentes em capítulos espaçados).

### 3.9 `database`
- Gerencia o banco relacional SQLite local por obra (`projects/<livro>/project.db`).
- **Características e Robustez**:
  - Modo WAL (`PRAGMA journal_mode=WAL`) para concorrência de leitura e escrita.
  - Integridade referencial ativada (`PRAGMA foreign_keys = ON`).
  - Timeout de concorrência (`busy_timeout = 5000ms`) e gerenciador de contexto transacional seguro (`transaction()`) com rollback automático em caso de exceção.
- **Sistema de Migrations Versionadas**:
  - `v0001_initial_schema.sql`: Tabelas fundamentais de projetos, documentos, capítulos, seções, parágrafos, segmentos, entidades, personagens, glossário, memórias de tradução, bíblia de estilo, traduções, revisões, QA, eventos e checkpoints.
  - `v0002_add_indices.sql`: Índices de performance para busca por `project_id`, `chapter_id`, `reading_order` e termos de busca.
  - `v0003_rich_document_units.sql`: Tabelas e colunas para unidades editoriais ricas (`headings`, `dialogues`, `footnotes`, `images`, `references_bibliography`, `spans_json` e `source_location_json`).
- Suporta tradução incremental com checkpointing a cada segmento (pausa, retomada e recuperação contra falhas).

### 3.10 `export`
- Reconstrói o documento no formato de destino desejado (EPUB, DOCX, TXT), preservando formatação (itálicos, títulos, quebras, notas de rodapé).
- **Regra de ouro**: O arquivo de entrada original nunca é sobrescrito (`book.epub` gera `book_pt-BR.epub`).

### 3.11 `ui`
- Interface de interação com o usuário (desktop/gráfica e CLI de diagnóstico/controle).
- Projetada para simplificar ao máximo a experiência de usuários leigos, expondo detalhes técnicos apenas sob demanda em modo avançado.

---

## 4. Estado das Decisões de Arquitetura

Conforme registrado nos ADRs:
- **Decisões Aprovadas**:
  - Arquitetura de pipeline editorial modular.
  - MADLAD-400-10B-MT como motor linguístico desacoplado.
  - Execução 100% local com modelos fora do Git/executável.
  - Memória persistente por obra com tradução incremental por segmento.
- **Decisões Abertas (OPEN)**:
  - Runtime de inferência definitivo (CTranslate2 vs llama.cpp/GGUF).
  - Nível de quantização padrão (Q4, Q6 ou Q8).
  - Framework e modelo para extração de entidades (NER) e embeddings de Semantic QA.
  - Framework de interface gráfica (PyQt6 / PySide6 / etc.).
  - Motor de OCR para PDFs escaneados.
