# ADR 0006: Style Bible, Story/Context Memory e Seleção Seletiva de Contexto

## Status
APROVADO

## Contexto
O Prompt 11 especifica a implementação da **Style Bible** e da **Story/Context Memory** com governança editorial estrita:
1. **Style Bible**:
   - Registro estruturado de 10 dimensões editoriais: `narrador` (`narrator`), `pessoa narrativa` (`narrative_person`), `tempo predominante` (`predominant_tense`), `nível de formalidade` (`formality_level`), `padrão de diálogo` (`dialogue_style`), `tratamento de palavrões` (`profanity_handling`), `formas de tratamento` (`treatment_forms`), `pontuação editorial` (`editorial_punctuation`), `tratamento de títulos` (`title_treatment`) e `convenções internas` (`internal_conventions`).
   - Todo dado deve conter citação textual de evidência (`StyleEvidence`) e nível de confiança.
   - Suporte a regras travadas (`locked=True`) imutáveis sem consentimento forçado (`force=True`).
   - Validação automatizada para QA de pós-edição (`validate_text`).
2. **Story/Context Memory**:
   - Registro de `resumo por capítulo/seção` (`ChapterSummary`), `estado atual de personagens` (`CharacterState`), `relações` (`StoryRelationship`), `eventos relevantes` (`StoryEvent`), `cronologia` (`timeline_order`), `fatos persistentes` (`PersistentFact`) e `referências cruzadas` (`StoryCrossReference`).
   - Diferenciação inequívoca entre fatos explícitos e inferências (`is_inferred: bool`, `source_type: 'explicit' | 'inference'`).
   - Detecção e sinalização programática de contradições (`detect_contradictions`).
3. **Restrição Arquitetural Central**:
   - *MADLAD-400 não é um LLM conversacional com janelas massivas de 128k/1M tokens*. Estas estruturas não devem ser despejadas como um mega-prompt caótico, mas sim servir como base indexada para seleção seletiva, contexto focado de cena (`StoryContextSnapshot`) e QA automatizado de continuidade.

## Decisões

### 1. Modelagem da Style Bible e Governança de Regras
- Criou-se a classe `StyleBible` (e entidades auxiliares `StyleRule`, `StyleEvidence`, `StyleViolation`):
  - 10 dimensões fortemente tipadas com valores canônicos e evidências (`StyleEvidence(text_snippet, chapter_id, segment_id, line_number)`).
  - Capacidade de definir regras com bloqueio (`locked=True`), impedindo sobrescrita acidental em novos ciclos de análise sem `force=True`.
  - Mecanismos analíticos de QA: `validate_dialogue_style`, `validate_punctuation`, `validate_profanity`, `validate_treatment`, `validate_title_treatment` e agregador `validate_text`.
  - Método `detect_contradictions()`: detecta conflitos entre regras travadas e novos achados analíticos.

### 2. Modelagem da Story/Context Memory
- Criou-se a classe `StoryMemory` com suporte a 6 coleções estruturadas:
  - `ChapterSummary`: resumos por capítulo com eventos-chave e personagens presentes.
  - `CharacterState`: status vital (`alive`, `deceased`, `injured`, `missing`, etc.), localização e papel dinâmico na cena.
  - `StoryRelationship`: laços entre personagens (`source_char`, `target_char`, `relation_type`), evidências e confiança.
  - `StoryEvent`: linha do tempo com `chronological_order`, capítulo/segmento e descrição.
  - `PersistentFact`: fatos invariantes do universo narrativo (ex: "The ring makes the bearer invisible").
  - `StoryCrossReference`: vínculos de foreshadowing, callbacks ou referências cruzadas entre capítulos.
- Cada registro armazena `is_inferred: bool`, `source_type` (`explicit` ou `inference`), nível de confiança (0.0 a 1.0) e lista de evidências com offset/segmento.

### 3. Seleção Seletiva de Contexto (`StoryContextSnapshot`)
- Para evitar a ilusão de um LLM conversacional e respeitar a janela e arquitetura seq2seq do MADLAD-400:
  - Criou-se o método `StoryMemory.get_scene_context_snapshot(chapter_id, character_names, max_facts=5, max_events=3)` que sintetiza um contêiner ultracompacto `StoryContextSnapshot`.
  - **Prioridade a Fatos Explícitos**: Fatos marcados como `is_inferred=False` possuem prioridade sobre inferências heurísticas.
  - Apenas estados vitais dos personagens presentes na cena atual são incluídos, evitando poluição de contexto com personagens ausentes.

### 4. Detecção e Sinalização de Contradições
- O método `StoryMemory.detect_contradictions()` audita inconsistências da narrativa:
  - **Fatos Conflitantes**: Quando dois fatos ativos tratam do mesmo tópico mas um nega o outro ou divergem em dados essenciais.
  - **Quebra de Continuidade de Personagem**: Quando um personagem marcado com status terminal (ex: `deceased` no capítulo 3) reaparece em ação normal em capítulos posteriores sem justificativa ou flashback.
  - **Conflitos de Inferência vs. Fato Explícito**: Quando uma inferência diverge frontalmente de uma constatação explícita documentada.
- Os conflitos detectados são integrados ao `MemoryManager.detect_all_conflicts()` sob as categorias `story_contradiction` e `style_contradiction`.

### 5. Persistência Relacional com Migration 0005
- Implementou-se a migration `0005_style_bible_and_story_memory.sql` criando as tabelas indexadas:
  - `story_summaries`: resumos estruturados de capítulos.
  - `character_states`: estados dinâmicos de personagens por capítulo/segmento.
  - `story_relationships`: relações interpessoais e laços narrativos.
  - `story_events`: eventos cronológicos.
  - `story_facts`: fatos persistentes do universo com filtros de inferência.
  - `story_cross_references`: referências cruzadas entre partes da obra.
  - Atualização da tabela `style_bible` com as novas 10 colunas e `internal_conventions_json`.

## Consequências
- **Positivas**:
  - Toda informação de estilo e história é ancorada em evidências textuais verificáveis.
  - Zero risco de sobrecarregar o modelo de tradução (MADLAD-400) com prompts inflados, mantendo o consumo de tokens sob controle estrito.
  - QA automatizado de pós-tradução ganha checagem de estilo (travessões vs. aspas, pontuação, formalidade) e continuidade de narrativa (morte/vida de personagens).
  - Manutenção de trilha de auditoria e respeito a regras travadas.
- **Negativas / Mitigações**:
  - Maior complexidade no esquema relacional SQLite: mitigada com índices específicos criados na migration 0005 e operações em lote (`executemany`) nos métodos de persistência do `sqlite.py`.
