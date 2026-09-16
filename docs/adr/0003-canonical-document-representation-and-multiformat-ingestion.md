# ADR 0003: Representação Canônica de Documentos e Ingestão Multiformato

## Status
APROVADO (ACCEPTED) — Implementado nos Prompts 03 a 06 e auditado no Prompt 07.

## Contexto
A esteira editorial de tradução de livros (EN → PT-BR) precisa suportar uma variedade heterogênea de formatos de origem: arquivos planos (`.txt`, `.md`), hipertexto estruturado (`.html`), documentos de processamento de texto (`.docx`), livros digitais empacotados (`.epub`) e documentos de paginação fixa (`.pdf`).

Permitir que etapas posteriores (análise global, extração de entidades, memórias de tradução, segmentação, inferência e validação de QA) manipulassem diretamente bibliotecas e árvores de nós específicas de cada formato geraria acoplamento extremo, fragilidade a mudanças e duplicação de regras editoriais.

## Decisão

### 1. Representação Canônica Intermediária Unificada
Foi estabelecido um modelo intermediário agnóstico ao formato de origem (`book_translator.core.document` e `models`), composto por:
- `Document`: Contêiner raiz com metadados bibliográficos completos (`DocumentMetadata`), lista de capítulos ordenados, notas globais, referências e imagens globais.
- `Chapter`: Unidade macro de organização textual dotada de sequência determinística de leitura (`get_reading_sequence()`).
- Unidades de Conteúdo com ID Estável e `reading_order`:
  - `Heading`: Nível hierárquico (1 a 6) e spans de formatação.
  - `Paragraph`: Parágrafo de prosa com texto bruto, texto normalizado, spans e rastreabilidade de origem (`SourceLocation`).
  - `DialogueBlock`: Identificação explícita de falas com marcador de diálogo (travessões/aspas) e indicação de interlocutor (`speaker_hint`).
  - `Footnote`: Notas de rodapé ou de fim de capítulo com vínculo referencial (`referencing_unit_id`).
  - `Reference`: Citações e bibliografia com chaves de citação e URLs.
  - `ImagePlaceholder`: Posição na ordem de leitura, caminho relativo, alt text e legenda.
  - `FormattingSpan`: Intervalos com estilo tipográfico (`bold`, `italic`, `underline`, `code`, `link`, `strikethrough`).

### 2. Normalização Textual e Des-hifenização
Todos os parsers herdam de `BaseParser` e aplicam:
- Normalização Unicode canônica (NFKC).
- Limpeza de quebras de linha desnecessárias preservando parágrafos.
- Classificação automatizada de diálogos via pontuação editorial (`—`, `–`, `"`, `«`).
- Correção de hifenização de quebra de linha (ex: `trans-` + `lation` -> `translation`).

### 3. Ingestão Defensiva e Imutabilidade
- Os arquivos originais fornecidos pelo usuário são abertos estritamente em modo de leitura binária (`rb`) e nunca são modificados ou sobrescritos.
- `IngestionInspector` valida o tipo MIME / magic bytes antes do parse, prevenindo falhas silenciosas com extensões renomeadas ou incorretas.
- PDFs são triados com classificação de qualidade textual: `TEXTUAL`, `MIXED` ou `SCANNED_NEEDS_OCR`. Documentos escaneados sem camada textual legível são rejeitados precocemente com `NeedsOcrError`, impedindo que ruído seja propagado às fases de tradução.

### 4. Persistência Relacional Integrada
A estrutura canônica é serializável e persistida no SQLite do projeto (`project.db`) via migrations versionadas (v0001 a v0003), permitindo roundtrip integral de ida e volta sem perda de hierarquia ou formatação.

## Consequências

### Positivas
- **Desacoplamento Completo**: Os módulos de Análise, Memória, Tradução e QA interagem exclusivamente com a representação canônica.
- **Equivalência Estrutural**: Documentos semanticamente idênticos em formatos distintos geram árvores canônicas com a mesma sequência de leitura e tipos de unidades.
- **Segurança**: Salvaguardas de tamanho máximo (`max_file_size_bytes`) e verificação de integridade protegem contra travamentos e arquivos corrompidos.

### Trade-offs / Limitações
- Elementos visuais não textuais hiper-específicos (tabelas complexas com células mescladas, fórmulas matemáticas em MathML) requerem simplificação ou representação textual auxiliar na fase atual.
- Documentos PDF dependem de heurísticas estatísticas para supressão de cabeçalhos e rodapés repetidos, podendo necessitar de parametrização manual em edições atípicas.
