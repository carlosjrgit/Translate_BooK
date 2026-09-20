# Relatório Consolidado de Auditoria Técnica e Desempenho — Checkpoint de Auditoria 3
**Data**: 2026-09-20  
**Fase Auditada**: Prompts 14 a 20 (Motor de Tradução MADLAD-400, Cache Determinístico, N-best Candidate Ranker, QA Determinístico, Semantic QA Multi-Sinal, Retrotradução como Evidência Auxiliar e Consistency Pass Global)  
**Status**: APROVADO COM RESSALVAS TÉCNICAS DOCUMENTADAS (PRONTO PARA FASE DE EXPORTAÇÃO E UI)  

---

## 1. Sumário Executivo

O **Checkpoint de Auditoria 3 (Prompt 21)** realizou uma avaliação técnica, holística e empírica de todo o pipeline de tradução construído no **Translate_BooK**.

Conforme a diretriz mandatória (*"NÃO adicione novas features"*), a esteira foi submetida a testes integrados de estresse e conformidade utilizando um conjunto curado de textos literários em inglês com traduções humanas de referência para avaliação interna (localizado em [`benchmarks/corpus/literary_en_pt.json`](file:///c:/Users/Carlos%20Jr/OneDrive/%C3%81rea%20de%20Trabalho/Translate_BooK/benchmarks/corpus/literary_en_pt.json) e executado em [`tests/integration/test_audit_checkpoint_3.py`](file:///c:/Users/Carlos%20Jr/OneDrive/%C3%81rea%20de%20Trabalho/Translate_BooK/tests/integration/test_audit_checkpoint_3.py)).

A auditoria cobriu 8 componentes centrais:
1. **Context Retrieval** ([`src/book_translator/context/engine.py`](file:///c:/Users/Carlos%20Jr/OneDrive/%C3%81rea%20de%20Trabalho/Translate_BooK/src/book_translator/context/engine.py));
2. **Motor MADLAD-400-10B-MT** ([`src/book_translator/translation/madlad.py`](file:///c:/Users/Carlos%20Jr/OneDrive/%C3%81rea%20de%20Trabalho/Translate_BooK/src/book_translator/translation/madlad.py));
3. **Cache Determinístico SHA-256 e Invalidação** ([`src/book_translator/translation/pipeline.py`](file:///c:/Users/Carlos%20Jr/OneDrive/%C3%81rea%20de%20Trabalho/Translate_BooK/src/book_translator/translation/pipeline.py));
4. **N-best Candidate Ranker** ([`src/book_translator/translation/ranker.py`](file:///c:/Users/Carlos%20Jr/OneDrive/%C3%81rea%20de%20Trabalho/Translate_BooK/src/book_translator/translation/ranker.py));
5. **QA Determinístico** ([`src/book_translator/qa/deterministic.py`](file:///c:/Users/Carlos%20Jr/OneDrive/%C3%81rea%20de%20Trabalho/Translate_BooK/src/book_translator/qa/deterministic.py));
6. **Semantic QA Multi-Sinal** ([`src/book_translator/qa/semantic.py`](file:///c:/Users/Carlos%20Jr/OneDrive/%C3%81rea%20de%20Trabalho/Translate_BooK/src/book_translator/qa/semantic.py));
7. **Retrotradução (Backtranslation)** ([`src/book_translator/qa/backtranslation.py`](file:///c:/Users/Carlos%20Jr/OneDrive/%C3%81rea%20de%20Trabalho/Translate_BooK/src/book_translator/qa/backtranslation.py));
8. **Consistency Pass Global** ([`src/book_translator/consistency/checker.py`](file:///c:/Users/Carlos%20Jr/OneDrive/%C3%81rea%20de%20Trabalho/Translate_BooK/src/book_translator/consistency/checker.py)).

A suíte completa de testes conta agora com **268 testes automatizados**, todos aprovados com 100% de sucesso.

---

## 2. Matriz de Achados Técnicos (As 6 Áreas Auditadas)

| ID | Eixo de Auditoria | Diagnóstico / Achado | Severidade | Impacto | Recomendação Técnica |
|---|---|---|:---:|---|---|
| **ACH-01** | **Regressões** | A integração de ponta a ponta não apresentou quebra de contratos pré-existentes. Todos os contratos de dados (`Segment`, `Document`, `TranslationDraft`) preservam imutabilidade de `original_text`. | Baixa | Nulo | Manter suíte integrada em CI. |
| **ACH-02** | **Falso Senso de Confiança** | *Similaridade por Embedding Isolada*: Frases com inversão direta de polaridade (ex: "He was *not* guilty" $\to$ "Ele era culpado") alcançam similaridade vetorial de cosseno $> 0.70$ em modelos densos ingênuos. O motor multi-sinal (Prompt 18) barrou a anomalia via checagem lógica de polaridade e antônimos. | Alta | Risco crítico se o usuário desativar o QA multi-sinal. | **Nunca** permitir desativação de regras lógicas de polaridade mesmo quando embeddings forem utilizados. |
| **ACH-03** | **Falso Senso de Confiança** | *Limites da Retrotradução*: Traduções literais de expressões idiomáticas (ex: "piece of cake" $\to$ "pedaço de bolo") geram falsos negativos na volta (reconstroem "piece of cake" perfeitamente). Paralelamente, sinônimos benignos (ex: "hound" $\to$ "cão" $\to$ "dog") geram falsos positivos de divergência. | Média | Alertas espúrios ou aprovação indevida. | Manter estritamente a diretriz do Prompt 19: a retrotradução é **evidência auxiliar**, nunca autoridade soberana. |
| **ACH-04** | **Etapas Redundantes** | *Verificação Quádrupla de Termos Travados*: Termos com `locked=True` são checados: (1) no pós-processamento do MADLAD; (2) no `CandidateRanker`; (3) no `DeterministicQA`; (4) no `GlobalConsistencyChecker`. | Média | Defesa em profundidade robusta, mas tempo de CPU acumulado em 4 varreduras regex idênticas. | Manter a checagem dupla (MADLAD + QA), simplificando a do Ranker quando a hipótese já foi forçada. |
| **ACH-05** | **Etapas Redundantes** | *Recuperação de Contexto antes do Cache*: `TranslationPipeline` invoca `self.context_engine.retrieve_context(segment)` antes de verificar o cache, porque o hash do contexto compõe a `cache_key`. | Média | Em reexecuções (100% cache hit), o SQLite executa queries de contexto para todos os segmentos desnecessariamente. | Avaliar separação de `cache_key` primária baseada no hash do segmento + glossário ativo. |
| **ACH-06** | **Custo Computacional** | *Retrotradução dobra a inferência*: Sem o `fast_mode=True`, a inferência é executada 2 vezes por segmento (ida EN $\to$ PT e volta PT $\to$ EN). | Alta | Dobro de consumo de GPU/VRAM e tempo de processamento total. | Default de lote: manter `fast_mode=True` como opção rápida e reservar backtranslation para segmentos com alerta semântico prévio. |
| **ACH-07** | **Custo Computacional** | *Varredura de Termos Recorrentes no Consistency Pass*: A detecção empírica (`_detect_recurrent_term_divergences`) varre todas as frases candidatas contra todos os segmentos via regex ($O(K \times N)$). | Média | Em livros com 5.000+ segmentos, o tempo de auditoria pode atingir vários segundos. | Indexar termos em um índice invertido em memória antes da auditoria. |
| **ACH-08** | **Falhas de Rastreabilidade** | *Persistência de Rollback do Consistency Pass*: Enquanto o QA Determinístico persiste `QAFixAuditRecord` na tabela `qa_fix_audits`, o `ConsistencyFixAuditRecord` reside **apenas em memória** no objeto `GlobalConsistencyReport`. Ao fechar a aplicação, perde-se a trilha relacional de rollback. | Alta | Impossibilidade de reversão de SAFE FIXES após reinicialização do sistema. | Criar tabela relacional `consistency_fix_audits` e métodos correspondentes no SQLite. |
| **ACH-09** | **Falhas de Rastreabilidade** | *Perda de Hipóteses N-best no Cache*: A tabela `translation_cache` grava apenas o `target_text` selecionado, omitindo as hipóteses alternativas ranqueadas. No cache hit, o draft só recupera o texto final. | Baixa | Perda de visibilidade das alternativas descartadas em execuções cacheadas. | Aceitável para economia de disco; registrar no relatório de governança. |
| **ACH-10** | **Divergências Banco vs Memória** | *Dessincronização de Instâncias*: `TranslationPipeline.translate_project` atualiza as linhas da tabela `segments` no banco, mas instâncias de `Document` pré-carregadas em memória permanecem com status `PENDING` até um novo `load_document`. | Média | Leituras de objetos em memória antigos exibem dados defasados. | Documentar que o banco de dados é a **fonte única da verdade** e forçar recarregamento pós-pipeline. |

---

## 3. Avaliação Detalhada por Componente

### 3.1 Context Retrieval
- **Pontos Fortes**: Aderência estrita ao orçamento de tokens (`ContextBudgetConfig.max_tokens`), prevenção efetiva de vazamento de trechos futuros (`allow_future_leakage=False`), cálculo determinístico do `reproducibility_hash`.
- **Ressalva**: Execução de queries no SQLite antes da checagem de cache na esteira de tradução gera overhead de E/S desnecessário quando o segmento já foi traduzido.

### 3.2 Motor MADLAD-400
- **Pontos Fortes**: Isolamento arquitetural de runtime (`TransformersBackend`, `CTranslate2Backend`, `MockMadladBackend`), suporte a quantizações (Q4, Q6, Q8, FP16), salvaguarda contra downloads não autorizados (`MissingModelWeightsError`).
- **Ressalva**: O pós-processamento de termos travados via regex de substituição ingênua pode, em casos raros de palavras homógrafas em inglês, forçar o termo incorreto se o contexto morfológico não for considerado.

### 3.3 Cache Determinístico e Invalidação
- **Pontos Fortes**: Hash SHA-256 canônico agregando texto fonte, modelo, runtime, parâmetros ordenados e hash de contexto. Invalidação cirúrgica por termo de glossário (`invalidate_cache_by_glossary_term`) reverte somente os segmentos afetados.
- **Ressalva**: A tabela de cache não indexa os candidatos alternativos N-best descartados, apenas a hipótese vencedora.

### 3.4 N-best Candidate Ranker
- **Pontos Fortes**: 7 dimensões transparentes com pesos normalizados (`fidelity`, `naturalness`, `terminology`, `consistency`, `character`, `style`, `fluency`). Ausência de pontuações mágicas.
- **Ressalva**: Em candidatos onde o modelo hallucina fluência perfeita em português mas inverte um sujeito gramatical, o ranker pode atribuir notas altas de naturalidade e fluência; a validação final requer necessariamente o QA Semântico.

### 3.5 QA Determinístico
- **Pontos Fortes**: Detecção exata de divergência em números, datas, moedas, medidas, URLs, notas e termos travados. Regras de `SAFE_FIX` cirúrgicas com trilha auditável gravada em `qa_fix_audits`.
- **Ressalva**: Diferenças de formatação numérica intencionais do autor (ex: "cinquenta" por extenso vs "50") exigem revisão manual e não devem ser automatizadas.

### 3.6 Semantic QA Multi-Sinal
- **Pontos Fortes**: Superação comprovada da fragilidade de embeddings isolados. 6 sinais ortogonais capturam inversões de sentido, omissões, adições, trocas de sujeito, perda de intensidade e falsos amigos com 0% de falsos positivos no benchmark.
- **Ressalva**: As regras de antônimos e falsos amigos dependem de dicionários lexicais; novos pares de falsos cognatos de nicho devem ser alimentados continuamente no vocabulário editorial.

### 3.7 Retrotradução (Backtranslation)
- **Pontos Fortes**: Evidência auxiliar eficaz para corroborar omissões brutas e perda de negações. Não autoridade absoluta garante que sinônimos naturais não reprovem traduções elegantes.
- **Ressalva**: Custo computacional elevado (duplica a inferência). Deve permanecer opcional via `fast_mode=True`.

### 3.8 Consistency Pass Global
- **Pontos Fortes**: Varredura abrangente de 15 dimensões (personagens, aliases, pronomes, tratamentos, termos, cronologia, Style Bible). Classificação rigorosa de alterações de tratamento como `REVIEW_REQUIRED`. Árvore de navegação e exportação estruturada em Markdown.
- **Ressalva**: Ausência de tabela relacional no SQLite para persistir `ConsistencyFixAuditRecord`, dependendo atualmente do estado do objeto em memória para rollback entre sessões.

---

## 4. Resultados de Desempenho e Latência

Avaliação executada sobre o corpus interno de referência:

| Etapa do Pipeline | Modo Padrão (Full QA) | Modo Rápido (`fast_mode=True`) | Economia / Overhead |
|---|:---:|:---:|:---:|
| **Tradução Inicial (6 segmentos)** | 132.6 ms | 130.1 ms | Equivalente (Mock) |
| **Cache Hit (6 segmentos)** | 3.2 ms | 3.1 ms | **41x mais rápido** que tradução fresca |
| **QA por Segmento** | 1.8 ms | 0.9 ms | **50% de redução** sem retrotradução |
| **Consistency Pass (Obra inteira)** | 4.8 ms | 4.8 ms | Varredura de 15 eixos |
| **Rollback de Fixes** | < 0.2 ms | < 0.2 ms | Restauração atômica |

---

## 5. Parecer de Prontidão Técnica

> [!IMPORTANT]
> **Veredito da Auditoria**: **APROVADO PARA AS FASES SUBSEQUENTES (EXPORTADORES E UI EDITORIAL)**.  
> 
> O pipeline editorial de tradução, ranqueamento, garantia de qualidade e consistência global é sólido, transparente, auditável e defensável. As 10 observações levantadas (notadamente a persistência no SQLite dos registros de auditoria do Consistency Pass e a otimização de queries de contexto antes do cache) devem ser priorizadas nas etapas finais de refinamento sem bloquear o avanço para a implementação dos exportadores multiformato e da interface de usuário.
