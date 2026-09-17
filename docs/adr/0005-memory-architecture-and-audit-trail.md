# ADR 0005: Arquitetura de Memórias, Termos Travados (Locked) e Trilha de Auditoria

## Status
APROVADO

## Contexto
O Prompt 10 especifica a implementação das três memórias principais da esteira editorial:
1. **Character Memory**: Armazena nome canônico, aliases, ocorrências, relações, tratamento, atributos linguisticamente relevantes, evidências e confiança.
2. **Glossary**: Armazena `source_term`, `target_term`, `type`, `aliases`, `locked`, `case_sensitive`, `contexto`, `primeira ocorrência`, `ocorrências` e `notas`.
3. **Translation Memory (TM)**: Armazena `source`, `target`, `contexto`, `origem`, `status`, `locked`, `histórico de alterações` e `confiança`.

Além dos campos específicos de armazenamento, foram impostas três regras fundamentais de qualidade e governança:
- **Não usar substituições cegas no texto**: Substrings não devem ser substituídas inadvertidamente dentro de outras palavras (ex: "art" dentro de "part").
- **Termos locked devem ser verificáveis**: Um mecanismo formal de compliance deve validar se os termos travados presentes no original constam fielmente no texto traduzido, e tentativas de sobrescrita devem ser bloqueadas a menos que explicitamente forçadas.
- **O histórico deve permitir auditoria**: Todas as alterações estruturais e de tradução nas memórias devem registrar autor, data/hora ISO-8601, valores anteriores e novos, campo alterado e motivo.

## Decisão

### 1. Modelos Canônicos de Memória e Versionamento
- **`MemoryRevision`**: Entidade imutável que registra cada evento de mutação com `revision_id` (UUID curto), `timestamp` em UTC, `changed_by` (identificador do operador/sistema), `field_name`, `old_value`, `new_value` e `reason`.
- **`CharacterEntry`**: Entidade com `name`, `canonical_name`, `aliases`, `gender`, `treatment`, `speech_style`, `linguistic_traits`, `relations`, `evidences`, `confidence`, `occurrences` e lista de `history`.
- **`GlossaryEntry`**: Entidade com `source_term`, `target_term`, `entry_type`, `description`, `aliases`, `case_sensitive`, `locked`, `gender`, `plural`, `context`, `first_occurrence`, `occurrences`, `notes` e `history`.
- **`TranslationMemoryEntry`**: Entidade com `source_term` (alias `.source`), `target_term` (alias `.target`), `entry_type`, `locked`, `occurrences`, `context`, `origin`, `status`, `confidence` e `history`.

### 2. Persistência Relacional com Migration 0004
- Implementou-se a migration `0004_memory_audit_and_enrichment.sql` que adiciona as colunas necessárias em `characters`, `glossary` e `translation_memory`, mantendo integridade com SQLite e serialização JSON nos campos ricos.
- Criou-se a tabela relacional indexada `memory_audit_log`:
  ```sql
  CREATE TABLE IF NOT EXISTS memory_audit_log (
      id TEXT PRIMARY KEY,
      project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      memory_type TEXT NOT NULL,
      entry_id TEXT NOT NULL,
      term_or_name TEXT NOT NULL,
      field_changed TEXT NOT NULL,
      old_value TEXT DEFAULT '',
      new_value TEXT DEFAULT '',
      changed_by TEXT DEFAULT 'user',
      reason TEXT DEFAULT '',
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  ```

### 3. Eliminação Absoluta de Substituições Cegas
- Desenvolveu-se o mecanismo `build_word_boundary_pattern(term: str) -> str`:
  - Se o termo inicia ou termina com caracteres alfanuméricos, fronteiras léxicas estritas (`\b`) são empregadas.
  - Para termos contendo caracteres especiais ou pontuação terminal (ex: "The end."), empregam-se asserções lookaround negativas (`(?<!\w)` e `(?!\w)`), evitando correspondências falsas no interior de palavras e ao mesmo tempo casando frases pontuadas no fluxo editorial.
  - `case_sensitive` é estritamente honrado conforme configurado por entrada no glossário.

### 4. Proteção e Verificação de Termos Travados (`locked`)
- **Proteção contra sobrescrita**: Ao invocar `add_entry` ou `update_entry` em termos com `locked=True`, caso uma nova tradução divergente seja fornecida, uma exceção `LockedTermError` é imediatamente disparada, a menos que o parâmetro `force=True` seja expressamente fornecido.
- **Verificação de conformidade (`verify_locked_terms`)**: Varre o texto de origem em busca de termos travados e valida se a tradução correspondente está presente no texto traduzido, retornando um relatório estruturado `LockedVerificationResult` (`is_compliant`, `total_checked`, `violations`).

### 5. Fachada Unificada e Detecção Cruzada de Conflitos (`MemoryManager`)
- O `MemoryManager` implementa `MemoryManagerInterface` e orquestra as três memórias, a `StyleBible` e a camada relacional SQLite.
- **Detecção de Conflitos Internos**:
  - Homônimos ambíguos na Character Memory (ex: aliases conflitantes entre múltiplos personagens).
  - Entradas de TM em status rejeitado com `locked=True`.
- **Detecção de Conflitos Cruzados**:
  - Identifica discrepâncias quando um termo possui uma tradução no Glossário (ex: "Elder Wand" -> "Varinha das Varinhas") e uma tradução diferente na Translation Memory (ex: "Elder Wand" -> "Varinha Anciã").

## Consequências
- **Positivas**:
  - Total rastreabilidade e governança editorial para auditoria humana.
  - Segurança contra regressões de tradução ao longo de capítulos longos de um livro.
  - 100% dos testes unitários (168 testes) passando com validação estrita no SQLite e conformidade com Ruff.
- **Próximos Passos**:
  - Integração do `MemoryManager` com o motor de inferência (MADLAD) e recuperação de contexto (`ContextRetrieval`) nas próximas etapas.
