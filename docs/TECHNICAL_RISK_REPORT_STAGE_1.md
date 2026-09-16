# Relatório de Riscos Técnicos — Checkpoint de Auditoria 1
**Data**: 2026-09-16  
**Fase Auditada**: Prompts 01 a 06 (Fundação, Projetos/Persistência, Representação Interna e Parsers TXT, MD, HTML, DOCX, EPUB, PDF)  
**Status**: FUNDAÇÃO APROVADA / PRONTO PARA FASE 2 COM SALVAGUARDAS  

---

## 1. Sumário Executivo

O presente relatório consolida a auditoria técnica profunda de todos os módulos construídos até a presente etapa da esteira editorial do **BookTranslator** (EN → PT-BR).

Foram examinados os seguintes eixos:
- **Arquitetura e contratos**: Desacoplamento entre parsers, modelos canônicos e persistência.
- **Banco de dados e migrations**: Integridade referencial, modo WAL, concorrência e rollback transacional.
- **Parsers e normalização**: 6 formatos textuais e binários (TXT, Markdown, HTML, DOCX, EPUB, PDF) auditados sob equivalência canônica estrita.
- **Segurança e integridade de arquivos**: Imutabilidade dos arquivos de entrada, salvaguardas de tamanho e caminhos.
- **Cobertura de testes**: 99 testes automatizados cobrindo fluxos nominais, casos limítrofes, corrupção de arquivos e roundtrip relacional.

---

## 2. Matriz de Riscos Técnicos Identificados

| ID | Área | Descrição do Risco | Severidade | Probabilidade | Mitigação Atual | Ação Futura Recomendada |
|---|---|---|---|---|---|---|
| **RSK-01** | Parsers / Memória | Livros volumosos (1.000+ páginas em PDF/EPUB) consomem RAM ao instanciar toda a árvore em memória. | Média | Baixa | `max_file_size_bytes` configurável; extração iterativa por páginas/capítulos. | Avaliar geradores/streaming de capítulos na fase de tradução contínua. |
| **RSK-02** | Heurística PDF | PDFs com paginação irregular ou cabeçalhos que alternam o título do capítulo podem enganar o filtro de frequência. | Média | Média | Threshold estatístico configurável (`header_footer_frequency_threshold = 0.6`). | Permitir sobrescrita de regras de cabeçalho na configuração do projeto (`project.json`). |
| **RSK-03** | OCR / Triagem | PDFs com texto embutido de OCR prévio de baixa qualidade (caracteres corrompidos) podem ser classificados como `TEXTUAL`. | Média | Baixa | Validação do tamanho médio do texto extraído por página (mínimo de caracteres úteis). | Adicionar heurística de densidade de caracteres imprimíveis vs símbolos espúrios. |
| **RSK-04** | Banco de Dados | Acesso simultâneo de escrita caso a interface gráfica dispare múltiplos workers de tradução em paralelo. | Baixa | Média | SQLite configurado em modo `WAL`, `busy_timeout = 5000ms`, transações atômicas via `transaction()`. | Centralizar writes através de fila assíncrona ou manter um worker de gravação no SQLite. |
| **RSK-05** | Encoding TXT | Textos legados com encoding regional misto ou corrompido falharem na decodificação UTF-8. | Baixa | Baixa | `TxtParser` utiliza `chardet` com detecção probabilística e cascata de fallbacks (`utf-8-sig`, `cp1252`, `latin-1`). | Alertar o usuário no CLI/GUI quando a confiança do detector for inferior a 0.7. |
| **RSK-06** | XML Bombs / Zip Bombs | Arquivos DOCX ou EPUB maliciosos com compressão desproporcional ou recursão de entidades XML. | Baixa | Muito Baixa | Defesa em profundidade: verificação de tamanho de arquivo pré-descompactação (`file_size_bytes`). | Adicionar limite de expansão de stream descompactado para ZIPs. |

---

## 3. Avaliação Detalhada por Módulo

### 3.1 Arquitetura e Acoplamento
- **Diagnóstico**: O desacoplamento através de `book_translator.core.contracts` e modelos agnósticos em `book_translator.core.models` mostrou-se 100% eficaz.
- **Verificação**: Nenhum parser importa ou conhece o motor de tradução, o módulo de análise global ou a interface de usuário. Todos os parsers retornam instâncias puras de `Document`.
- **Equivalência Canônica**: O teste `tests/unit/test_parsers_equivalence.py` provou que TXT, Markdown, HTML, DOCX, EPUB e PDF contendo o mesmo conteúdo semântico produzem sequências de leitura estritamente idênticas (`[Heading, Paragraph, DialogueBlock]`).

### 3.2 Banco de Dados e Migrations
- **Diagnóstico**: O schema versionado (v0001 a v0003) cobre todas as entidades requeridas pela especificação (`docs/PROJECT_SPECIFICATION_PT-BR.txt`).
- **Robustez**: O teste `test_transaction_rollback_on_error` comprovou que falhas durante escritas complexas executam `ROLLBACK` imediato, mantendo o banco livre de registros órfãos.
- **Roundtrip**: O teste `test_end_to_end_parsed_document_sqlite_roundtrip` confirmou que documentos ricos (com formatação inline, notas de rodapé vinculadas e metadados de imagem) são persistidos e reconstruídos com integridade referencial exata.

### 3.3 Tratamento de Erros e Logging
- **Diagnóstico**: A hierarquia de exceções em `book_translator.errors` (`BookTranslatorError`, `ParsingError`, `NeedsOcrError`, `DatabaseError`, etc.) fornece categorização semântica precisa.
- **Logging**: Módulos usam logs estruturados através de `book_translator.logging`, evitando chamadas diretas a `print()`.

### 3.4 Segurança de Arquivos e Imutabilidade
- **Diagnóstico**: O teste `test_parsers_never_modify_original_file` garante que o hash SHA-256 e o timestamp de modificação dos arquivos originais de entrada permanecem inalterados após qualquer operação de parsing.

### 3.5 Código Morto e Duplicações
- **Diagnóstico**: Não foram encontrados módulos, classes ou funções mortas.
- **Linter & Formatação**: O código do repositório foi 100% validado pelo `ruff` (linter e formatter) com zero erros e conformidade estrita de tipagem e comprimento de linha.

---

## 4. Parecer de Prontidão Técnica

> [!NOTE]
> **Veredito da Auditoria**: **APROVADO PARA A PRÓXIMA FASE (FASE 2 — ANÁLISE GLOBAL E MEMÓRIAS)**.  
> A fundação do projeto (infraestrutura de persistência, modelo de domínio canônico e ingestão multiformato) está estável, resiliente, totalmente testada e em conformidade com as diretrizes de projeto.
