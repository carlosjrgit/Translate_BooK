# ADR 0004: Book Analyzer e Interface de NER Plugável com Separação Fato-Inferência

## Status
APROVADO (Arquitetura e Contrato) / MOTOR DE NER DEFINITIVO ABERTO PARA BENCHMARK

## Contexto
O Book Analyzer realiza a análise prévia da obra antes da tradução, detectando personagens, aliases, locais, organizações, formas de tratamento, relações e registros de estilo.
A especificação técnica e as regras do Prompt 09 estabelecem requisitos estritos:
1. Não inventar informação ausente (zero alucinação).
2. Diferenciar rigorosamente fato extraído (ocorrência textual explícita) de inferência analítica.
3. Toda inferência deve registrar nível de confiança (0.0 a 1.0) e citação da evidência de origem.
4. Não fechar definitivamente a escolha de modelo de NER sem benchmark prévio.
5. Criar uma interface de NER substituível (`NERInterface`) e fornecer uma implementação funcional inicial leve.

## Decisão

### 1. Interface de NER Plugável (`NERInterface`)
Definiu-se uma interface estrita baseada em `typing.Protocol`:
```python
class NERInterface(Protocol):
    @property
    def engine_name(self) -> str: ...
    def extract_entities(
        self, text: str, context: dict[str, Any] | None = None
    ) -> list[RawEntityMention]: ...
```
Isso permite plugar no futuro motores baseados em spaCy, HuggingFace transformers, Flair ou LLMs locais sem alterar nenhuma linha do `BookAnalyzer`.

### 2. Implementação Heurística Inicial (`HeuristicNER`)
Como primeira implementação de referência, foi construído o `HeuristicNER`, determinístico e livre de dependências pesadas de modelos pré-treinados:
- Padrão de títulos e honoríficos (`Dr.`, `Mrs.`, `Lord`, `Inspector`, etc.) para identificação de personagens.
- Diferenciação de organizações (`Scotland Yard`, `Royal Guard`) e locais (`Baker Street`, `London Bridge`) com priorização de termos institucionais.
- Detecção de menções possessivas de nomes próprios (`Arthur's mother`).
- Ponderação de confiança por verbos de elocução (`said`, `whispered`, `perguntou`).

### 3. Modelo Canônico Fato vs. Inferência
- **`EntityOccurrence` (Fato Extraído)**: Representa o dado empírico observável no texto — `chapter_id`, `unit_id`, `char_offset` e `surrounding_snippet`.
- **`EntityInference` (Inferência)**: Representa deduções do sistema — `inference_type` (ex: `gender`, `alias_resolution`, `relation`), `value`, `confidence` e `evidence` textual.

### 4. Resolução de Aliases e Homônimos (`AliasResolver`)
- Menções unívocas a partes de nomes (ex: "Watson" referindo-se a "Dr. John Watson") são consolidadas como `aliases` com uma `EntityInference` correspondente.
- Homônimos com múltiplos candidatos (ex: "Henderson" quando existem "Robert Henderson" e "Jack Henderson") **não são fundidos cegamente**. Uma entidade ambígua é criada com `is_ambiguous = True`, `candidate_entity_ids` e nota de auditoria.

### 5. Extração de Relações (`RelationExtractor`)
- Identifica laços possessivos ("Arthur's mother Margaret") e inversos ("Watson, the faithful friend of Holmes").
- Todo vínculo de parentesco ou amizade é gerado com tipo (`mother_of`, `friend_of`), nível de confiança e snippet de evidência.

## Consequências
- **Positivas**:
  - Código desacoplado, auditável e extensível.
  - Ausência de dados fabricados ou inferências opacas.
  - Zero sobrecarga de memória na inicialização (sem modelos de GBs no Git ou RAM nesta etapa).
  - Persistência direta nas tabelas e estruturas de `CharacterMemory`, `Glossary`, `Entities` e `StyleBible`.
- **Em Avaliação (Open)**:
  - Benchmark comparativo futuro entre `HeuristicNER`, modelos compactos locais (`spacy-en-core-web-sm/md`) e abordagens híbridas assistidas por LLM.
