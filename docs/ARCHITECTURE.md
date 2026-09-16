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
- **`ingestion`**: Roteia o arquivo para o analisador correto. No caso de PDFs, avalia se existe camada de texto utilizável ou se há necessidade de OCR (*fallback*).
- **`parsers`**: Converte formatos heterogêneos (PDF, EPUB, DOCX, TXT, MD, HTML) para a árvore canônica `Document`.
- **`normalization`**: Executa des-hifenização de quebra de linha, normalização Unicode, detecção de cabeçalhos/rodapés repetidos e recomposição de parágrafos e diálogos.

### 3.3 `analysis`
- Varre a obra integralmente antes do início da tradução.
- Identifica personagens, locais, organizações, termos recorrentes, cronologia, formas de tratamento e registro estilístico predominante para inicializar as memórias do projeto.

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
- Gerencia o banco persistente por obra (`projects/<livro>/project.db`), suportando tradução incremental com checkpointing a cada segmento (pausa, retomada e recuperação contra falhas).

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
