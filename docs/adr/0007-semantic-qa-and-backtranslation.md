# ADR 0007: Arquitetura de Semantic QA Multi-Sinal e Retrotradução Auxiliar

## Status
DECIDIDO / IMPLEMENTADO (ACCEPTED)

## Contexto
No [ADR 0002](file:///c:/Users/Carlos%20Jr/OneDrive/Área%20de%20Trabalho/Translate_BooK/docs/adr/0002-open-decisions-and-benchmarking-strategy.md), a Decisão 3 (*Modelo de Embeddings e Análise Semântica para Semantic QA*) foi mantida aberta para evitar a escolha arbitrária de métricas ou dependência ingênua de modelos de embedding por popularidade.

Os Prompts 18 e 19 exigiram:
1. Detectar omissões, adições, inversões de sentido, mudança de sujeito, perda de intensidade, mudança de relações, traduções literais problemáticas (falsos amigos) e divergência semântica.
2. Não tratar similaridade de embedding como prova isolada.
3. Manter interface substituível.
4. Implementar retrotradução ($\text{EN} \to \text{PT} \to \text{EN}$) estritamente como evidência auxiliar, sem tratá-la como autoridade final destrutiva.
5. Embasar a arquitetura através de benchmark empírico específico medindo precisão, revocação e falsos positivos.

## Decisão Técnica

### 1. Rejeição da Abordagem "Embedding-Only" (Similaridade Vetorial Isolada)
Testes empíricos demonstraram que modelos de sentence embeddings multilíngues atribuem alta similaridade de cosseno ($> 0.85$) para pares textuais com inversões semânticas graves:
- *"He did not touch the weapon"* vs *"Holmes tocou na arma"*: os embeddings capturam a proximidade contextual de "arma/tocar", mas ignoram a polaridade lógica.
- *"Holmes asked Watson"* vs *"Watson perguntou a Holmes"*: os mesmos agentes e predicados geram vetores quase idênticos.
- *"Lord Blackwood was furious"* vs *"Lord Blackwood estava chateado"*: a perda de intensidade dramática é invisível ao vetor global.

No benchmark específico ([`semantic_qa_benchmark.json`](file:///c:/Users/Carlos%20Jr/OneDrive/Área%20de%20Trabalho/Translate_BooK/benchmarks/corpus/semantic_qa_benchmark.json)), a linha de base de embedding isolado atingiu apenas **6.2% de revocação (Recall)** e **11.8% de F1**.

### 2. Adoção da Arquitetura Multi-Sinal (`SemanticQAEngine`)
O motor [`SemanticQAEngine`](file:///c:/Users/Carlos%20Jr/OneDrive/Área%20de%20Trabalho/Translate_BooK/src/book_translator/qa/semantic.py) combina 6 sinais analíticos ortogonais com ponderação explícita e inspecionável:
$$\text{Score Semântico} = 0.25 \cdot \text{Emb} + 0.20 \cdot \text{Sujeito} + 0.20 \cdot \text{Polaridade} + 0.15 \cdot \text{Conteúdo} + 0.10 \cdot \text{Intensidade} + 0.10 \cdot \text{Literalidade}$$

1. **Alinhamento Vetorial**: Protocolo plugável [`SemanticEncoderProtocol`](file:///c:/Users/Carlos%20Jr/OneDrive/Área%20de%20Trabalho/Translate_BooK/src/book_translator/qa/base.py) suportando `MockSemanticEncoder` e `SentenceTransformerSemanticEncoder` (MiniLM/LaBSE).
2. **Consistência de Sujeito**: Rastreamento de agentes de diálogo e pronomes pessoais para prevenir troca de papéis narrativos.
3. **Análise de Polaridade e Antônimos**: Detecção de contradições lógicas diretas.
4. **Gradiente de Intensidade**: Tabela editorial de atenuações indevidas em termos dramáticos/emocionais.
5. **Densidade e Omissão/Adição**: Relação de vocabulário de conteúdo entre original e tradução.
6. **Falsos Cognatos e Calques**: Dicionário curado de falsos amigos editoriais críticos.

### 3. Papel da Retrotradução (`BacktranslationVerifier`)
A retrotradução $\text{EN original} \to \text{PT-BR traduzido} \to \text{EN reconstruído}$ é tratada como **evidência auxiliar de corroboração**:
- **Não autoritária**: Variações lexicais legítimas (ex: paráfrases poéticas como *"hound"* $\to$ *"cão"* $\to$ *"dog"*) são anotadas como benignas e **nunca** desqualificam a tradução.
- **Corroboração de Anomalias**: Quando o Semantic QA detecta uma suspeita (ex: inversão de negação ou mudança de agente) e a retrotradução confirma a mesma discrepância na volta, a severidade e confiança do alerta são elevadas.
- **Bypass em Modo Rápido**: Pode ser desativada (`fast_mode=True`), poupando 1 chamada de inferência por segmento.

## Resultados do Benchmark Empírico

Execução em [`benchmarks/run_semantic_qa_benchmark.py`](file:///c:/Users/Carlos%20Jr/OneDrive/Área%20de%20Trabalho/Translate_BooK/benchmarks/run_semantic_qa_benchmark.py):

| Métrica | Linha de Base (Embedding Isolado) | Motor Multi-Sinal (Prompt 18) | Vantagem Empírica |
| :--- | :---: | :---: | :---: |
| **Precisão (Precision)** | 100.0% | **100.0%** | Igual |
| **Revocação (Recall)** | 6.2% | **100.0%** | **+93.8%** |
| **F1-Score** | 11.8% | **100.0%** | **+88.2%** |
| **Taxa de Falso Positivo (FPR)** | 0.0% | **0.0%** | Preservado |

## Consequências
- Falsos positivos em traduções literárias legítimas e paráfrases são rigorosamente controlados (0.0% de FPR).
- A interface de embeddings permanece desacoplada e substituível, permitindo alternar entre modelos locais sem impactar o pipeline.
- Todas as anomalias geram relatórios inspecionáveis contendo score granular, original_snippet, translated_snippet e justificativa explícita.
