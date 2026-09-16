# ADR 0002: Catálogo de Decisões Abertas e Estratégia de Benchmark

## Status
ABERTO / EM AVALIAÇÃO (OPEN)

## Contexto
A especificação conceitual do projeto estabelece explicitamente que certas escolhas de engenharia não devem ser tomadas arbitrariamente por preferência ou popularidade, mas sim fundamentadas em prototipagem, medições reais de consumo e testes empíricos de qualidade de tradução (EN → PT-BR).

## Decisões Mantidas Explicitamente como ABERTAS (OPEN)

### 1. Runtime de Inferência Local
- **Opções em estudo**: `CTranslate2` vs `runtime GGUF/llama.cpp`.
- **Critérios de decisão**: Qualidade de saída, velocidade de geração (tokens/s), uso de RAM e VRAM, suporte a aceleração por hardware no Windows (NVIDIA CUDA, AMD ROCm/DirectML e CPU-only), estabilidade e facilidade de empacotamento em instalador standalone.
- **Status**: **OPEN**

### 2. Nível de Quantização Padrão
- **Opções em estudo**: Q4 (~6 GB), Q6 (~8-9 GB) e Q8 (~11 GB).
- **Critérios de decisão**: Benchmark comparativo real medindo degradação sintática e semântica vs consumo de memória em hardware intermediário.
- **Status**: **OPEN**

### 3. Modelo de Embeddings e Análise Semântica para Semantic QA
- **Opções em estudo**: Modelos de embeddings multilíngues compactos (ex: MiniLM, BGE, LaBSE) ou métricas léxico-semânticas especializadas.
- **Critérios de decisão**: Capacidade de detecção de omissões e alucinações sem incorrer em overhead computacional proibitivo para execução local conjunta com o modelo de 10B.
- **Status**: **OPEN**

### 4. Estratégia de Detecção de Personagens e NER
- **Opções em estudo**: Bibliotecas tradicionais de NLP baseadas em regras e modelos estatísticos leves (ex: spaCy) vs abordagens híbridas assistidas por dicionários e análise contextual prévia.
- **Status**: **OPEN**

### 5. Algoritmo de Context Retrieval e Granularidade de Segmentos
- **Critérios de decisão**: Dimensionamento ideal de segmentos (sentença, parágrafo, bloco de diálogo, cena) e janela de contexto útil que maximize a coerência sem exceder a janela de contexto eficiente do modelo de tradução.
- **Status**: **OPEN**

### 6. Framework de Interface Gráfica (GUI)
- **Opções em estudo**: `PySide6` / `PyQt6` vs outras alternativas para desktop nativo no Windows.
- **Critérios de decisão**: Facilidade de empacotamento (PyInstaller), visual moderno, responsividade durante processamento assíncrono longo e consumo de recursos.
- **Status**: **OPEN**

### 7. Mecanismo de OCR para PDFs Escaneados
- **Opções em estudo**: Tesseract / EasyOCR / PDF-Extractors especializados.
- **Critérios de decisão**: Taxa de erro em caracteres acentuados, preservação da ordem de leitura e impacto no tamanho do instalador final.
- **Status**: **OPEN**

## Próximos Passos
Cada uma dessas decisões será formalmente fechada em sua respectiva etapa de desenvolvimento, acompanhada de relatórios de benchmark técnicos e reprodutíveis.
